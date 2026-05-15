"""
Publisher kazanç muhasebesi testleri (FAZ 1).

`TelegramChannel.total_earnings` ve `pending_earnings` alanları
settlement sonrası birlikte artar, negatif değere düşmez ve
farklı kanallar arasında izole kalır.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from ads.models import AdPlacement, Campaign
from ads.tasks import _settle_placement


pytestmark = pytest.mark.django_db(transaction=True)


def test_pending_and_total_earnings_increment_together(placement_factory, money):
    """Settlement sonrası iki alan da eşit miktarda artar."""
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=1,
        impressions=1000,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
    )

    _settle_placement(placement.id)

    placement.channel.refresh_from_db()
    assert placement.channel.total_earnings == money("3500.00")
    assert placement.channel.pending_earnings == money("3500.00")
    # İkisi her zaman aynı miktarda artmalı (payout başlamadığı sürece)
    assert placement.channel.total_earnings == placement.channel.pending_earnings


def test_earnings_accumulate_across_multiple_placements(placement_factory, money):
    """Aynı kanalda birden çok placement için gelir toplanır."""
    channel_kwargs = {"telegram_chat_id": -100_999}
    p1 = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=1,
        impressions=1000,
        channel__telegram_chat_id=channel_kwargs["telegram_chat_id"],
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
    )
    p2 = placement_factory(
        ad=p1.ad,
        channel=p1.channel,
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=2,
        impressions=2000,
        scheduled_at=timezone.now() + timezone.timedelta(minutes=10),
    )

    _settle_placement(p1.id)
    _settle_placement(p2.id)

    p1.channel.refresh_from_db()
    # 3500 + 7000 = 10500 UZS
    assert p1.channel.total_earnings == money("10500.00")
    assert p1.channel.pending_earnings == money("10500.00")


def test_earnings_isolated_between_channels(
    placement_factory, channel_factory, money
):
    """Farklı kanallar birbirinin kazancını etkilememeli."""
    channel_a = channel_factory(telegram_chat_id=-100_001)
    channel_b = channel_factory(telegram_chat_id=-100_002)

    p_a = placement_factory(
        channel=channel_a,
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=11,
        impressions=1000,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
    )
    p_b = placement_factory(
        channel=channel_b,
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=22,
        impressions=2000,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
    )

    _settle_placement(p_a.id)
    _settle_placement(p_b.id)

    channel_a.refresh_from_db()
    channel_b.refresh_from_db()

    assert channel_a.total_earnings == money("3500.00")
    assert channel_b.total_earnings == money("7000.00")


def test_earnings_never_go_negative_after_settlements(placement_factory, money):
    """Bir dizi settlement sonrası total_earnings >= 0 invariantı korunmalı."""
    placements = []
    for i in range(5):
        placements.append(
            placement_factory(
                status=AdPlacement.Status.SENT,
                sent_at=timezone.now(),
                telegram_message_id=1000 + i,
                impressions=500,
                ad__campaign__billing_type=Campaign.BillingType.CPM,
                ad__campaign__bid_amount=money("5000.00"),
                scheduled_at=timezone.now() + timezone.timedelta(minutes=i),
            )
        )

    for p in placements:
        _settle_placement(p.id)

    for p in placements:
        p.channel.refresh_from_db()
        assert p.channel.total_earnings >= Decimal("0")
        assert p.channel.pending_earnings >= Decimal("0")
        assert p.channel.total_earnings >= p.channel.pending_earnings or (
            p.channel.total_earnings == p.channel.pending_earnings
        )


def test_zero_cost_settlement_does_not_change_earnings(placement_factory, money):
    """0 impression → billing_status=skipped → earnings hiç dokunulmaz."""
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=1,
        impressions=0,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
    )
    original_total = placement.channel.total_earnings
    original_pending = placement.channel.pending_earnings

    _settle_placement(placement.id)

    placement.channel.refresh_from_db()
    assert placement.channel.total_earnings == original_total
    assert placement.channel.pending_earnings == original_pending
