"""
Billing doğruluğu ve idempotency testleri (FAZ 1).

Kapsama:
- CPM ve CPC maliyet hesapları Decimal kesinliğinde
- Komisyon bölüşümü %30/%70 → platform_fee + publisher_revenue == total_cost
- Sıfır impression/click → billing atlanır, skipped işaretlenir
- Aynı placement'ı iki kez settle → ikinci çağrı no-op
- Telegram delete fail → billing geri alınmaz
- Bütçe tükenirse `check_campaign_budgets` kampanyayı completed'a alır
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from ads.models import AdPlacement, Campaign
from ads.services import AdDeliveryService
from ads.tasks import _settle_placement, check_campaign_budgets
from channels_app.models import TelegramChannel


pytestmark = pytest.mark.django_db(transaction=True)


# --- calculate_placement_cost --------------------------------------------------


def test_cpm_cost_calculation_is_exact(placement_factory, money):
    """1000 impression × 5000 UZS bid → 5000.00 UZS maliyet."""
    placement = placement_factory(
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
        impressions=1000,
    )

    costs = AdDeliveryService.calculate_placement_cost(placement)

    assert costs["total_cost"] == money("5000.00")
    assert isinstance(costs["total_cost"], Decimal)


def test_cpm_fractional_impressions_preserve_precision(placement_factory, money):
    """250 impression × 5000 UZS → 1250.00 UZS (1/4 × 5000)."""
    placement = placement_factory(
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
        impressions=250,
    )

    costs = AdDeliveryService.calculate_placement_cost(placement)

    assert costs["total_cost"] == money("1250.00")


def test_cpc_cost_calculation_is_exact(placement_factory, money):
    """10 click × 500 UZS bid → 5000.00 UZS maliyet."""
    placement = placement_factory(
        ad__campaign__billing_type=Campaign.BillingType.CPC,
        ad__campaign__bid_amount=money("500.00"),
        clicks=10,
    )

    costs = AdDeliveryService.calculate_placement_cost(placement)

    assert costs["total_cost"] == money("5000.00")


def test_commission_split_preserves_total(placement_factory, money):
    """platform_fee + publisher_revenue tam olarak total_cost'a eşit olmalı."""
    placement = placement_factory(
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
        impressions=1000,
    )

    costs = AdDeliveryService.calculate_placement_cost(placement)

    assert costs["platform_fee"] + costs["publisher_revenue"] == costs["total_cost"]
    # 30/70 bölüşümü: 5000 × 0.30 = 1500, kalan 3500 publisher
    assert costs["platform_fee"] == money("1500.00")
    assert costs["publisher_revenue"] == money("3500.00")


def test_commission_split_with_rounding_edge(placement_factory, money):
    """Yuvarlama kenar durumunda invariant bozulmamalı."""
    # 333 impression × 7000 UZS / 1000 = 2331.00
    # fee = 2331 × 0.30 = 699.30 → quantize → 699.30
    # revenue = 2331 - 699.30 = 1631.70
    placement = placement_factory(
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("7000.00"),
        impressions=333,
    )

    costs = AdDeliveryService.calculate_placement_cost(placement)

    assert costs["platform_fee"] + costs["publisher_revenue"] == costs["total_cost"]


# --- Settlement idempotency ----------------------------------------------------


def test_zero_impressions_settlement_marks_skipped(placement_factory, money):
    """0 impression ile CPM → billing_status='skipped', herkesin hesabı 0."""
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=999,
        impressions=0,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
    )

    _settle_placement(placement.id)

    placement.refresh_from_db()
    assert placement.billing_status == AdPlacement.BillingStatus.SKIPPED
    assert placement.billed_at is not None
    assert placement.cost == money("0.00")

    placement.ad.campaign.refresh_from_db()
    assert placement.ad.campaign.spent == money("0.00")


def test_settlement_is_idempotent(placement_factory, money):
    """Aynı placement'ı iki kez settle et → sadece bir kere faturalanır."""
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=999,
        impressions=1000,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
    )

    _settle_placement(placement.id)
    first_billed_at = AdPlacement.objects.get(id=placement.id).billed_at

    # İkinci çağrı no-op olmalı
    _settle_placement(placement.id)

    placement.refresh_from_db()
    campaign = placement.ad.campaign
    campaign.refresh_from_db()

    # billed_at değişmemeli (ikinci settle guard tarafından engellenmeli)
    assert placement.billed_at == first_billed_at
    # spent sadece bir kez artmalı: 5000 UZS
    assert campaign.spent == money("5000.00")


def test_settlement_skips_already_billed_row(placement_factory, money):
    """billed_at NOT NULL olan bir placement settle çağrılsa bile atlanır."""
    already_billed_at = timezone.now()
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=999,
        impressions=1000,
        billed_at=already_billed_at,
        billing_status=AdPlacement.BillingStatus.BILLED,
        cost=money("5000.00"),
        publisher_revenue=money("3500.00"),
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
        ad__campaign__spent=money("5000.00"),
    )
    original_campaign_spent = placement.ad.campaign.spent

    result = _settle_placement(placement.id)

    assert result["status"] == "already_billed"
    placement.ad.campaign.refresh_from_db()
    assert placement.ad.campaign.spent == original_campaign_spent


def test_settlement_skips_non_sent_placements(placement_factory):
    """status='scheduled' veya 'failed' placement'lar faturalanmaz."""
    placement = placement_factory(status=AdPlacement.Status.SCHEDULED)

    result = _settle_placement(placement.id)

    assert result["status"] == "not_sent"
    placement.refresh_from_db()
    assert placement.billed_at is None


def test_telegram_delete_failure_does_not_rollback_billing(
    placement_factory, telegram_sender_mock, money
):
    """Silme sırasında Telegram exception'u atsa bile billing korunmalı."""
    telegram_sender_mock.delete_message.side_effect = RuntimeError("telegram down")

    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=777,
        impressions=1000,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
    )

    _settle_placement(placement.id)

    placement.refresh_from_db()
    # Billing commit olmuş olmalı
    assert placement.billed_at is not None
    assert placement.billing_status == AdPlacement.BillingStatus.BILLED
    assert placement.cost == money("5000.00")
    # Ancak Telegram'dan silinemediği için status='sent' kalır
    assert placement.status == AdPlacement.Status.SENT

    placement.ad.campaign.refresh_from_db()
    assert placement.ad.campaign.spent == money("5000.00")


# --- Campaign budget enforcement ------------------------------------------------


def test_budget_exhausted_triggers_completion(placement_factory, money):
    """spent >= budget olduğunda check_campaign_budgets kampanyayı completed yapar."""
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=999,
        impressions=20000,  # 20k imp × 5000/1000 = 100_000 UZS
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000.00"),
        ad__campaign__budget=money("100000.00"),
    )
    campaign = placement.ad.campaign

    _settle_placement(placement.id)
    check_campaign_budgets()

    campaign.refresh_from_db()
    assert campaign.spent == money("100000.00")
    assert campaign.status == Campaign.Status.COMPLETED


def test_campaign_spent_increment_is_atomic(placement_factory, money):
    """F() güncellemesi iki ayrı placement için toplanmalı."""
    campaign_bid = money("5000.00")
    p1 = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=1,
        impressions=1000,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=campaign_bid,
    )
    # İkinci placement aynı kampanyada, aynı ad altında — scheduled_at farklı
    p2 = placement_factory(
        ad=p1.ad,
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=2,
        impressions=2000,
        scheduled_at=timezone.now() + timezone.timedelta(minutes=5),
    )

    _settle_placement(p1.id)
    _settle_placement(p2.id)

    p1.ad.campaign.refresh_from_db()
    # 5000 + 10000 = 15000 UZS
    assert p1.ad.campaign.spent == money("15000.00")
