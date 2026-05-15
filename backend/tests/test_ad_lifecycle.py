"""
Reklam yaşam döngüsü testleri (FAZ 1).

scheduled → deliver_scheduled_ads → sent → delete_expired_ads (dispatch)
  → _settle_placement → billed + deleted (TG silme başarılıysa)
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from freezegun import freeze_time
from django.utils import timezone

from ads.models import AdPlacement, Campaign
from ads.tasks import delete_expired_ads, deliver_scheduled_ads


pytestmark = pytest.mark.django_db(transaction=True)


def test_full_scheduled_to_billed_flow(
    placement_factory, telegram_sender_mock, money
):
    """Bir placement'ın tüm yaşam döngüsü: scheduled → sent → billed → deleted."""
    start = timezone.now().replace(microsecond=0)

    with freeze_time(start):
        placement = placement_factory(
            status=AdPlacement.Status.SCHEDULED,
            scheduled_at=start - timezone.timedelta(minutes=1),
            delete_after_hours=1,
            impressions=1000,
            ad__campaign__billing_type=Campaign.BillingType.CPM,
            ad__campaign__bid_amount=money("5000.00"),
            ad__campaign__status=Campaign.Status.ACTIVE,
        )
        telegram_sender_mock.send_ad.return_value = 42

        # Aşama 1: deliver → status=sent
        deliver_scheduled_ads()

        placement.refresh_from_db()
        assert placement.status == AdPlacement.Status.SENT
        assert placement.telegram_message_id == 42
        assert placement.sent_at is not None
        assert placement.billed_at is None  # henüz faturalanmadı

    # Aşama 2: 2 saat sonra delete_expired_ads çalışır
    with freeze_time(start + timezone.timedelta(hours=2)):
        delete_expired_ads()

        placement.refresh_from_db()
        # Billing + deletion tamamlanmış olmalı
        assert placement.billed_at is not None
        assert placement.billing_status == AdPlacement.BillingStatus.BILLED
        assert placement.status == AdPlacement.Status.DELETED
        assert placement.cost == money("5000.00")
        assert placement.publisher_revenue == money("3500.00")

        placement.ad.campaign.refresh_from_db()
        assert placement.ad.campaign.spent == money("5000.00")

        placement.channel.refresh_from_db()
        assert placement.channel.total_earnings == money("3500.00")
        assert placement.channel.pending_earnings == money("3500.00")

        # Telegram sender çağrıldı
        telegram_sender_mock.delete_message.assert_called_once()


def test_failed_delivery_does_not_bill(
    placement_factory, telegram_sender_mock, money
):
    """send_ad exception atarsa status=failed, billing yok."""
    telegram_sender_mock.send_ad.side_effect = RuntimeError("telegram boom")

    placement = placement_factory(
        status=AdPlacement.Status.SCHEDULED,
        scheduled_at=timezone.now() - timezone.timedelta(minutes=1),
        ad__campaign__status=Campaign.Status.ACTIVE,
    )

    deliver_scheduled_ads()

    placement.refresh_from_db()
    assert placement.status == AdPlacement.Status.FAILED
    assert placement.billed_at is None
    assert placement.billing_status == AdPlacement.BillingStatus.PENDING


def test_expired_ads_dispatcher_only_picks_due_placements(
    placement_factory, money
):
    """delete_expired_ads sadece süresi dolmuş, henüz faturalanmamış kayıtları işler."""
    now = timezone.now()

    # Süresi dolmuş + faturalanmamış → işlenmeli
    due = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=now - timezone.timedelta(hours=25),
        delete_after_hours=24,
        impressions=1000,
        ad__campaign__bid_amount=money("5000.00"),
    )

    # Henüz süresi dolmamış → atlanmalı
    not_due = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=now - timezone.timedelta(minutes=5),
        delete_after_hours=24,
    )

    # Zaten faturalanmış → atlanmalı
    already_billed = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=now - timezone.timedelta(hours=25),
        delete_after_hours=24,
        billed_at=now - timezone.timedelta(hours=1),
        billing_status=AdPlacement.BillingStatus.BILLED,
    )

    delete_expired_ads()

    due.refresh_from_db()
    not_due.refresh_from_db()
    already_billed.refresh_from_db()

    assert due.billed_at is not None
    assert not_due.billed_at is None
    # already_billed'ın billed_at'ı değişmemeli
    assert already_billed.billing_status == AdPlacement.BillingStatus.BILLED


def test_concurrent_dispatch_only_bills_once(placement_factory, money):
    """delete_expired_ads iki kez üst üste çağrılsa bile çift faturalama olmaz."""
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now() - timezone.timedelta(hours=25),
        delete_after_hours=24,
        telegram_message_id=555,
        impressions=1000,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
    )

    # İki ardışık çağrı — ikincisinin dispatch ettiği sub-task idempotent guard'a takılmalı
    delete_expired_ads()
    delete_expired_ads()

    placement.ad.campaign.refresh_from_db()
    # spent sadece bir kez artmalı
    assert placement.ad.campaign.spent == money("5000.00")
