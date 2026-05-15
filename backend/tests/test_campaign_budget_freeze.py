"""
Campaign budget freeze akışı testleri (FAZ 4a).

Akış:
  Campaign create → status=pending, bakiye dokunulmaz
  Admin approve    → freeze_for_campaign çağrılır, balance → frozen
  _settle_placement → frozen havuzundan AD_SPEND düşülür
  Campaign complete → refund_unspent_campaign (kalan frozen → balance)
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ads.models import AdPlacement, Campaign
from ads.tasks import _settle_placement, check_campaign_budgets
from core.models import User
from payments.models import Transaction, UserBalance


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="fr-root", email="fr@example.test", password="x"
    )


def _approve_as_admin(admin_user, campaign_id):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client.post(f"/api/admin-panel/campaigns/{campaign_id}/approve/")


def _reject_as_admin(admin_user, campaign_id, reason="no"):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client.post(
        f"/api/admin-panel/campaigns/{campaign_id}/reject/",
        {"reason": reason},
        format="json",
    )


# --- Approve → freeze --------------------------------------------------------


def test_admin_approve_freezes_budget(
    admin_user, advertiser_factory, campaign_factory, money,
):
    advertiser = advertiser_factory()
    UserBalance.objects.create(user=advertiser, balance=money("500000"))
    campaign = campaign_factory(
        advertiser=advertiser, budget=money("200000"), status="pending",
    )

    response = _approve_as_admin(admin_user, campaign.id)
    assert response.status_code == 200

    wallet = UserBalance.objects.get(user=advertiser)
    assert wallet.balance == money("300000")
    assert wallet.frozen_amount == money("200000")

    # Freeze transaction kaydedilmiş
    tx = Transaction.objects.get(
        user=advertiser, type=Transaction.Type.FREEZE, related_campaign=campaign,
    )
    assert tx.amount == money("200000")


def test_admin_approve_rejects_insufficient_balance(
    admin_user, advertiser_factory, campaign_factory, money,
):
    advertiser = advertiser_factory()
    UserBalance.objects.create(user=advertiser, balance=money("50000"))
    campaign = campaign_factory(
        advertiser=advertiser, budget=money("200000"), status="pending",
    )

    response = _approve_as_admin(admin_user, campaign.id)
    assert response.status_code == 400

    campaign.refresh_from_db()
    assert campaign.status == "pending"  # değişmemeli

    wallet = UserBalance.objects.get(user=advertiser)
    assert wallet.balance == money("50000")
    assert wallet.frozen_amount == money("0")


# --- Settle → spend from frozen ---------------------------------------------


def test_settle_placement_draws_from_frozen(
    advertiser_factory, placement_factory, money,
):
    advertiser = advertiser_factory()
    UserBalance.objects.create(
        user=advertiser, balance=money("0"), frozen_amount=money("100000"),
    )
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=1,
        impressions=1000,
        ad__campaign__advertiser=advertiser,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000"),
    )

    _settle_placement(placement.id)

    wallet = UserBalance.objects.get(user=advertiser)
    # 1000 imp × 5000/1000 = 5000 UZS düştü
    assert wallet.frozen_amount == money("95000")
    assert wallet.balance == money("0")

    # AD_SPEND transaction var
    assert Transaction.objects.filter(
        user=advertiser,
        type=Transaction.Type.AD_SPEND,
        related_placement=placement,
    ).exists()


def test_settle_placement_credits_publisher_balance(
    publisher_factory, channel_factory, placement_factory, money,
):
    publisher = publisher_factory()
    channel = channel_factory(owner=publisher)
    placement = placement_factory(
        channel=channel,
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=1,
        impressions=1000,
        ad__campaign__billing_type=Campaign.BillingType.CPM,
        ad__campaign__bid_amount=money("5000"),
    )
    # Advertiser'ın frozen'ına yeter miktarı koy
    advertiser = placement.ad.campaign.advertiser
    UserBalance.objects.create(
        user=advertiser, balance=money("0"), frozen_amount=money("10000"),
    )

    _settle_placement(placement.id)

    # Publisher bakiyesi 5000 × 70% = 3500 UZS arttı
    pub_wallet = UserBalance.objects.get(user=publisher)
    assert pub_wallet.balance == money("3500")

    assert Transaction.objects.filter(
        user=publisher, type=Transaction.Type.AD_EARNING,
    ).exists()


# --- Complete → refund ------------------------------------------------------


def test_reject_campaign_refunds_frozen_budget(
    admin_user, advertiser_factory, campaign_factory, money,
):
    advertiser = advertiser_factory()
    UserBalance.objects.create(user=advertiser, balance=money("500000"))
    campaign = campaign_factory(
        advertiser=advertiser, budget=money("200000"), status="pending",
    )

    _approve_as_admin(admin_user, campaign.id)  # freeze
    _reject_as_admin(admin_user, campaign.id, reason="test")

    wallet = UserBalance.objects.get(user=advertiser)
    # Tam iade — henüz harcama yok
    assert wallet.balance == money("500000")
    assert wallet.frozen_amount == money("0")

    assert Transaction.objects.filter(
        user=advertiser,
        type=Transaction.Type.REFUND,
        related_campaign=campaign,
    ).exists()


def test_check_campaign_budgets_refunds_completed_campaigns(
    advertiser_factory, campaign_factory, money,
):
    advertiser = advertiser_factory()
    UserBalance.objects.create(
        user=advertiser, balance=money("0"), frozen_amount=money("100000"),
    )
    campaign = campaign_factory(
        advertiser=advertiser,
        budget=money("100000"),
        spent=money("100000"),  # budget exhausted
        status=Campaign.Status.ACTIVE,
    )

    check_campaign_budgets()

    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.COMPLETED
    wallet = UserBalance.objects.get(user=advertiser)
    # Tamamen harcanmış — iade yok
    assert wallet.balance == money("0")


def test_partial_spend_refunds_remainder(
    advertiser_factory, campaign_factory, money,
):
    advertiser = advertiser_factory()
    UserBalance.objects.create(
        user=advertiser, balance=money("0"), frozen_amount=money("100000"),
    )
    campaign = campaign_factory(
        advertiser=advertiser,
        budget=money("100000"),
        spent=money("40000"),
        # end_date geçmiş — check_campaign_budgets complete'ı tetikler
        end_date=timezone.now() - timezone.timedelta(hours=1),
        status=Campaign.Status.ACTIVE,
    )

    check_campaign_budgets()

    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.COMPLETED
    wallet = UserBalance.objects.get(user=advertiser)
    # 100000 - 40000 = 60000 iade
    assert wallet.balance == money("60000")
    assert wallet.frozen_amount == money("40000")


# --- Full flow integration --------------------------------------------------


def test_end_to_end_budget_lifecycle(
    admin_user, advertiser_factory, campaign_factory,
    placement_factory, money,
):
    """Create → approve (freeze) → settle (spend) → complete (refund)."""
    advertiser = advertiser_factory()
    UserBalance.objects.create(user=advertiser, balance=money("200000"))

    # 1) Create campaign
    campaign = campaign_factory(
        advertiser=advertiser,
        budget=money("100000"),
        spent=money("0"),
        billing_type=Campaign.BillingType.CPM,
        bid_amount=money("5000"),
        status="pending",
    )

    # 2) Approve → freeze 100k
    _approve_as_admin(admin_user, campaign.id)
    wallet = UserBalance.objects.get(user=advertiser)
    assert wallet.balance == money("100000")
    assert wallet.frozen_amount == money("100000")

    # 3) Set campaign active and settle a placement (4000 UZS cost)
    campaign.status = Campaign.Status.ACTIVE
    campaign.save(update_fields=["status"])
    placement = placement_factory(
        ad__campaign=campaign,
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=42,
        impressions=800,  # 800 imp × 5000/1000 = 4000 UZS
    )
    _settle_placement(placement.id)

    campaign.refresh_from_db()
    wallet.refresh_from_db()
    assert campaign.spent == money("4000")
    assert wallet.frozen_amount == money("96000")

    # 4) Complete via end_date expiration
    campaign.end_date = timezone.now() - timezone.timedelta(minutes=1)
    campaign.save(update_fields=["end_date"])
    check_campaign_budgets()

    wallet.refresh_from_db()
    # 96000 iade edildi
    assert wallet.balance == money("196000")
    assert wallet.frozen_amount == money("0")
