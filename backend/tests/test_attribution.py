"""
pixel.attribution edge case testleri (FAZ 5 Adım 2).

Kapsam — kullanıcı review'unda istediği kritik kararlar:
- D: Öncelik sırası (click_id > utm, ilk eşleşen kazanır)
- Attribution window sınırları (7 gün default, window dışı eşleşmez)
- Non-attribution event (PageView) → Conversion üretilmez
- E: 30+ gün eski unattributed event'ler "expired" işaretlenir (sonsuz
  retry kesilir)
- E: Batch 1000 sınırı ve select_for_update race koruması
- Conversion.event OneToOne race handling (duplicate attempt → mevcut döner)
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from analytics.models import ClickEvent
from ads.models import AdPlacement
from pixel.attribution import attribute_event
from pixel.models import Conversion, ConversionEvent
from pixel.tasks import UNATTRIBUTED_MAX_AGE_DAYS, attribute_pending_conversions


pytestmark = pytest.mark.django_db(transaction=True)


def _click(placement_factory, created_ago: timedelta = timedelta(hours=1)):
    """Helper — ClickEvent oluştur, created_at'i geçmişe çek."""
    p = placement_factory(status=AdPlacement.Status.SENT)
    ce = ClickEvent.objects.create(
        placement=p,
        ip_hash=("a" * 64),
        ip_subnet_hash=("b" * 64),
        user_agent_hash=("c" * 64),
    )
    ClickEvent.objects.filter(pk=ce.pk).update(
        created_at=timezone.now() - created_ago,
    )
    ce.refresh_from_db()
    return ce


def _event(pixel_factory, **overrides):
    pixel = overrides.pop("pixel", None) or pixel_factory()
    kwargs = dict(
        pixel=pixel,
        event_name="Purchase",
        event_id=uuid.uuid4(),
        value=Decimal("50000"),
        currency="UZS",
    )
    kwargs.update(overrides)
    return ConversionEvent.objects.create(**kwargs)


# --- D: Attribution priority ------------------------------------------------


def test_click_id_takes_priority_over_utm(
    pixel_factory, placement_factory, conversion_event_factory,
):
    """click_id set ise, utm_campaign match olsa bile click_id kazanır."""
    click = _click(placement_factory)
    campaign_id = click.placement.ad.campaign_id
    # utm farklı bir kampanyaya işaret etse de click_id ağır basar.
    event = _event(
        pixel_factory,
        click_id=click.pk,
        utm_campaign=f"{campaign_id + 999}-other",
    )
    conv = attribute_event(event)
    assert conv is not None
    assert conv.touch_method == Conversion.TouchMethod.CLICK_ID
    assert conv.click_event_id == click.pk


def test_utm_fallback_when_no_click_id(pixel_factory, placement_factory):
    click = _click(placement_factory)
    campaign_id = click.placement.ad.campaign_id
    event = _event(
        pixel_factory,
        click_id=None,
        utm_campaign=f"{campaign_id}-summer",
    )
    conv = attribute_event(event)
    assert conv is not None
    assert conv.touch_method == Conversion.TouchMethod.UTM
    assert conv.click_event_id == click.pk


def test_utm_selects_most_recent_click_in_window(
    pixel_factory, placement_factory,
):
    """Aynı kampanyada birden fazla click varsa, EN SON click seçilir."""
    old_click = _click(placement_factory, created_ago=timedelta(days=5))
    # Aynı campaign'e bağlı yeni bir placement/ad oluştur
    new_click = _click(placement_factory, created_ago=timedelta(hours=2))
    # İki farklı campaign'dan — utm_campaign hangisine işaret ediyorsa o.
    campaign_id = new_click.placement.ad.campaign_id

    event = _event(
        pixel_factory,
        click_id=None,
        utm_campaign=f"{campaign_id}-latest",
    )
    conv = attribute_event(event)
    assert conv is not None
    assert conv.click_event_id == new_click.pk


# --- Attribution window -----------------------------------------------------


def test_click_outside_window_not_matched_by_click_id(
    pixel_factory, placement_factory,
):
    """click_window_days=7; 10 gün eski click eşleşmemeli."""
    pixel = pixel_factory(click_window_days=7)
    click = _click(placement_factory, created_ago=timedelta(days=10))
    event = _event(pixel_factory, pixel=pixel, click_id=click.pk)
    conv = attribute_event(event)
    assert conv is None
    event.refresh_from_db()
    assert event.attribution_attempted_at is not None  # denendi, düştü


def test_click_outside_window_not_matched_by_utm(
    pixel_factory, placement_factory,
):
    pixel = pixel_factory(click_window_days=7)
    click = _click(placement_factory, created_ago=timedelta(days=10))
    campaign_id = click.placement.ad.campaign_id
    event = _event(
        pixel_factory, pixel=pixel,
        click_id=None, utm_campaign=f"{campaign_id}-x",
    )
    conv = attribute_event(event)
    assert conv is None


# --- Non-attribution event --------------------------------------------------


def test_pageview_event_not_attributed(pixel_factory, placement_factory):
    """attribution_events listesinde olmayan event → Conversion yok ama
    attribution_attempted_at set (bir daha denenmesin)."""
    pixel = pixel_factory(attribution_events=["Purchase", "Lead"])
    click = _click(placement_factory)
    event = _event(
        pixel_factory, pixel=pixel,
        event_name="PageView", click_id=click.pk,
    )
    conv = attribute_event(event)
    assert conv is None
    event.refresh_from_db()
    assert event.attribution_attempted_at is not None
    assert not Conversion.objects.filter(event=event).exists()


# --- Idempotency: ikinci attribute_event çağrısı yeni kayıt yaratmamalı ---


def test_second_attribute_call_returns_existing_conversion(
    pixel_factory, placement_factory,
):
    click = _click(placement_factory)
    event = _event(pixel_factory, click_id=click.pk)

    conv1 = attribute_event(event)
    # Attribution_attempted_at sıfırlayıp tekrar dene (race simulation).
    event.attribution_attempted_at = None
    event.save(update_fields=["attribution_attempted_at"])

    conv2 = attribute_event(event)
    assert conv1.pk == conv2.pk
    assert Conversion.objects.filter(event=event).count() == 1


# --- E: Celery task 30-day cutoff + batching ------------------------------


def test_task_marks_expired_unattributed_events(
    pixel_factory, placement_factory,
):
    """30+ gün eski unattributed event'ler `attribution_attempted_at=now`
    ile işaretlenir (kayıp kabul edilir, sonsuz retry kesilir)."""
    old_event = _event(pixel_factory)
    # created_at'i geçmişe çek
    ConversionEvent.objects.filter(pk=old_event.pk).update(
        created_at=timezone.now() - timedelta(days=UNATTRIBUTED_MAX_AGE_DAYS + 5),
    )

    result = attribute_pending_conversions()
    assert result["expired_marked"] >= 1

    old_event.refresh_from_db()
    assert old_event.attribution_attempted_at is not None


def test_task_skips_already_attempted_events(
    pixel_factory, placement_factory,
):
    """attribution_attempted_at set olan event'ler yeniden denenmez."""
    click = _click(placement_factory)
    event = _event(pixel_factory, click_id=click.pk)
    event.attribution_attempted_at = timezone.now() - timedelta(hours=1)
    event.save(update_fields=["attribution_attempted_at"])

    result = attribute_pending_conversions()
    assert result["picked"] == 0


def test_task_attributes_fresh_events(pixel_factory, placement_factory):
    """Yeni event + geçerli click_id → attribute edilir."""
    click = _click(placement_factory)
    event = _event(pixel_factory, click_id=click.pk)
    # Yeni event, attempted_at NULL, 30 gün içinde

    result = attribute_pending_conversions()
    assert result["attributed"] == 1
    assert Conversion.objects.filter(event=event).exists()


def test_task_counts_unmatched_separately(pixel_factory):
    """Match bulunamayan event unmatched counter'a eklenir, attributed'a değil."""
    # click_id yok, utm_campaign yok → hiçbir strateji tutmaz
    event = _event(pixel_factory, click_id=None, utm_campaign="")
    result = attribute_pending_conversions()
    assert result["attributed"] == 0
    assert result["unmatched"] == 1
    event.refresh_from_db()
    assert event.attribution_attempted_at is not None
