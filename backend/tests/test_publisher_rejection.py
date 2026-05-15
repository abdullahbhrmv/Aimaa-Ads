"""
Yayıncı red akışı testleri (FAZ 2).

Kapsam:
- Reject → `publisher_action=rejected`, reason kaydedilir
- Reject sonrası yeniden atama — yeni placement, farklı kanal
- Dispatch rejected placement'ı atlar
- Max reassignment cap (3)
- Başka yayıncının placement'ını reddedemez (403)
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ads.models import AdPlacement, Campaign
from ads.tasks import (
    MAX_REASSIGNMENT_ATTEMPTS,
    deliver_scheduled_ads,
    reassign_rejected_placement,
)


pytestmark = pytest.mark.django_db(transaction=True)


# --- Dispatch davranışı ------------------------------------------------------


def test_rejected_placement_not_picked_by_dispatcher(
    placement_factory, telegram_sender_mock
):
    """publisher_action=rejected olan placement deliver_scheduled_ads tarafından atlanmalı."""
    placement = placement_factory(
        status=AdPlacement.Status.SCHEDULED,
        scheduled_at=timezone.now() - timezone.timedelta(minutes=1),
        publisher_action=AdPlacement.PublisherAction.REJECTED,
        publisher_rejection_reason="Markamıza uygun değil",
        ad__campaign__status=Campaign.Status.ACTIVE,
    )

    deliver_scheduled_ads()

    placement.refresh_from_db()
    assert placement.status == AdPlacement.Status.SCHEDULED  # dokunulmamış
    telegram_sender_mock.send_ad.assert_not_called()


def test_auto_placement_is_picked_by_dispatcher(
    placement_factory, telegram_sender_mock
):
    """Default publisher_action=auto normalde gönderilmeli."""
    placement = placement_factory(
        status=AdPlacement.Status.SCHEDULED,
        scheduled_at=timezone.now() - timezone.timedelta(minutes=1),
        ad__campaign__status=Campaign.Status.ACTIVE,
    )
    telegram_sender_mock.send_ad.return_value = 999

    deliver_scheduled_ads()

    placement.refresh_from_db()
    assert placement.status == AdPlacement.Status.SENT


# --- reassign_rejected_placement task ----------------------------------------


def test_reject_triggers_reassignment_to_different_channel(
    placement_factory, channel_factory, money, ad_factory, campaign_factory
):
    """Reddedilen placement için başka uygun kanala atama yapılır."""
    # Campaign + iki kanal hazırla — aynı kategoride
    campaign = campaign_factory(status=Campaign.Status.ACTIVE)
    ad = ad_factory(campaign=campaign)
    channel_a = channel_factory(telegram_chat_id=-100_501)
    channel_b = channel_factory(
        telegram_chat_id=-100_502,
        category=channel_a.category,
    )

    placement = placement_factory(
        ad=ad,
        channel=channel_a,
        status=AdPlacement.Status.SCHEDULED,
        publisher_action=AdPlacement.PublisherAction.REJECTED,
        publisher_rejection_reason="Uygun değil",
    )

    reassign_rejected_placement(placement.id)

    # Yeni placement channel_b'ye oluşturulmalı
    new_placements = AdPlacement.objects.filter(ad=ad).exclude(id=placement.id)
    assert new_placements.count() == 1
    new_placement = new_placements.first()
    assert new_placement.channel_id == channel_b.id
    assert new_placement.reassignment_count == 1


def test_reassignment_excludes_previously_rejected_channels(
    placement_factory, channel_factory, ad_factory, campaign_factory
):
    """Aynı ad'ın daha önce reddedildiği kanallar seçilmemeli."""
    campaign = campaign_factory(status=Campaign.Status.ACTIVE)
    ad = ad_factory(campaign=campaign)
    channel_a = channel_factory(telegram_chat_id=-100_601)
    channel_b = channel_factory(telegram_chat_id=-100_602, category=channel_a.category)
    channel_c = channel_factory(telegram_chat_id=-100_603, category=channel_a.category)

    # Placement A reddedildi
    pa = placement_factory(
        ad=ad,
        channel=channel_a,
        status=AdPlacement.Status.SCHEDULED,
        publisher_action=AdPlacement.PublisherAction.REJECTED,
        publisher_rejection_reason="No",
    )
    # Placement B de daha önce reddedildi
    placement_factory(
        ad=ad,
        channel=channel_b,
        scheduled_at=timezone.now() + timezone.timedelta(minutes=1),
        status=AdPlacement.Status.SCHEDULED,
        publisher_action=AdPlacement.PublisherAction.REJECTED,
        publisher_rejection_reason="No",
    )

    reassign_rejected_placement(pa.id)

    new_placements = AdPlacement.objects.filter(
        ad=ad, publisher_action=AdPlacement.PublisherAction.AUTO
    )
    assert new_placements.count() == 1
    assert new_placements.first().channel_id == channel_c.id


def test_reassignment_max_attempts_respected(
    placement_factory, channel_factory, ad_factory, campaign_factory
):
    """reassignment_count MAX'a ulaştıysa yeni placement oluşmaz."""
    campaign = campaign_factory(status=Campaign.Status.ACTIVE)
    ad = ad_factory(campaign=campaign)
    channel = channel_factory()

    placement = placement_factory(
        ad=ad,
        channel=channel,
        status=AdPlacement.Status.SCHEDULED,
        publisher_action=AdPlacement.PublisherAction.REJECTED,
        publisher_rejection_reason="No",
        reassignment_count=MAX_REASSIGNMENT_ATTEMPTS,
    )

    result = reassign_rejected_placement(placement.id)

    assert result["status"] == "max_attempts_reached"
    # Yeni placement oluşmamalı
    assert AdPlacement.objects.filter(ad=ad).count() == 1


def test_reassignment_noop_if_not_rejected(placement_factory):
    """publisher_action != REJECTED ise task no-op."""
    placement = placement_factory(
        status=AdPlacement.Status.SCHEDULED,
        publisher_action=AdPlacement.PublisherAction.AUTO,
    )
    result = reassign_rejected_placement(placement.id)
    assert result["status"] == "not_rejected"


def test_reassignment_noop_if_campaign_not_active(
    placement_factory, campaign_factory, ad_factory
):
    campaign = campaign_factory(status=Campaign.Status.PAUSED)
    ad = ad_factory(campaign=campaign)
    placement = placement_factory(
        ad=ad,
        status=AdPlacement.Status.SCHEDULED,
        publisher_action=AdPlacement.PublisherAction.REJECTED,
        publisher_rejection_reason="No",
    )
    result = reassign_rejected_placement(placement.id)
    assert result["status"] == "campaign_not_active"


# --- API endpoint testleri ---------------------------------------------------


def test_publisher_can_reject_own_placement(
    placement_factory, publisher_factory, channel_factory
):
    """Kanal sahibi publisher kendi kanalındaki placement'ı reddedebilir."""
    publisher = publisher_factory()
    channel = channel_factory(owner=publisher)
    placement = placement_factory(
        channel=channel,
        status=AdPlacement.Status.SCHEDULED,
    )

    client = APIClient()
    client.force_authenticate(user=publisher)

    response = client.post(
        f"/api/ads/placements/{placement.id}/reject/",
        {"reason": "Markamıza uygun değil"},
        format="json",
    )

    assert response.status_code == 200
    placement.refresh_from_db()
    assert placement.publisher_action == AdPlacement.PublisherAction.REJECTED
    assert placement.publisher_rejection_reason == "Markamıza uygun değil"


def test_publisher_cannot_reject_others_placement(
    placement_factory, publisher_factory, channel_factory
):
    """Başka bir yayıncının kanalındaki placement reddedilememeli."""
    owner = publisher_factory()
    intruder = publisher_factory()
    channel = channel_factory(owner=owner)
    placement = placement_factory(
        channel=channel,
        status=AdPlacement.Status.SCHEDULED,
    )

    client = APIClient()
    client.force_authenticate(user=intruder)

    response = client.post(
        f"/api/ads/placements/{placement.id}/reject/",
        {"reason": "No"},
        format="json",
    )

    # ReadOnlyModelViewSet queryset'i intruder için boş döner → 404,
    # queryset dahilse permission_denied → 403. İkisi de "yetkisiz".
    assert response.status_code in (403, 404)

    placement.refresh_from_db()
    assert placement.publisher_action == AdPlacement.PublisherAction.AUTO


def test_reject_requires_reason(placement_factory, publisher_factory, channel_factory):
    publisher = publisher_factory()
    channel = channel_factory(owner=publisher)
    placement = placement_factory(
        channel=channel,
        status=AdPlacement.Status.SCHEDULED,
    )

    client = APIClient()
    client.force_authenticate(user=publisher)

    response = client.post(
        f"/api/ads/placements/{placement.id}/reject/",
        {"reason": ""},
        format="json",
    )

    assert response.status_code == 400
    placement.refresh_from_db()
    assert placement.publisher_action == AdPlacement.PublisherAction.AUTO


def test_cannot_reject_already_decided_placement(
    placement_factory, publisher_factory, channel_factory
):
    publisher = publisher_factory()
    channel = channel_factory(owner=publisher)
    placement = placement_factory(
        channel=channel,
        status=AdPlacement.Status.SCHEDULED,
        publisher_action=AdPlacement.PublisherAction.ACCEPTED,
    )

    client = APIClient()
    client.force_authenticate(user=publisher)

    response = client.post(
        f"/api/ads/placements/{placement.id}/reject/",
        {"reason": "değiştim"},
        format="json",
    )

    assert response.status_code == 400
