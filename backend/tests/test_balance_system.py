"""
Bakiye servisleri birim testleri (FAZ 4a).

Kapsam:
- deposit: idempotency, pozitif artış, User.balance mirror
- freeze_for_campaign: yetersiz bakiye → InsufficientBalanceError
- spend_from_frozen: normal akış ve frozen underrun edge case'i
- credit_publisher: pozitif kazanç, sıfır/negatif reddi
- refund_unspent_campaign: budget - spent kadar iade, clamping
- withdraw_for_payout: yetersiz bakiyede hata
- adjust: credit/debit
- Negatif bakiye asla oluşmaz invariantı
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from payments.models import Transaction, UserBalance
from payments.services import (
    InsufficientBalanceError,
    adjust,
    credit_publisher,
    deposit,
    freeze_for_campaign,
    refund_unspent_campaign,
    spend_from_frozen,
    withdraw_for_payout,
)


pytestmark = pytest.mark.django_db(transaction=True)


# --- deposit -----------------------------------------------------------------


def test_deposit_increments_balance_and_creates_transaction(advertiser_factory, money):
    user = advertiser_factory(balance=money("0"))
    tx = deposit(user, money("100000"), provider="click", provider_ref="ref-1")

    assert tx.type == Transaction.Type.DEPOSIT
    assert tx.status == Transaction.Status.COMPLETED
    assert tx.amount == money("100000")
    assert tx.balance_after == money("100000")

    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == money("100000")

    user.refresh_from_db()
    assert user.balance == money("100000")  # mirror


def test_deposit_is_idempotent_on_same_provider_ref(advertiser_factory, money):
    user = advertiser_factory(balance=money("0"))
    tx1 = deposit(user, money("50000"), provider="click", provider_ref="dup-1")
    tx2 = deposit(user, money("50000"), provider="click", provider_ref="dup-1")

    assert tx1.id == tx2.id
    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == money("50000")  # bir kez artmış


def test_deposit_rejects_zero_or_negative(advertiser_factory, money):
    user = advertiser_factory()
    with pytest.raises(ValueError):
        deposit(user, money("0"), provider="click", provider_ref="z")
    with pytest.raises(ValueError):
        deposit(user, money("-100"), provider="click", provider_ref="n")


# --- freeze_for_campaign -----------------------------------------------------


def test_freeze_moves_budget_from_balance_to_frozen(
    advertiser_factory, campaign_factory, money
):
    user = advertiser_factory()
    UserBalance.objects.create(user=user, balance=money("500000"))
    campaign = campaign_factory(advertiser=user, budget=money("200000"))

    tx = freeze_for_campaign(campaign)

    assert tx.type == Transaction.Type.FREEZE
    assert tx.amount == money("200000")
    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == money("300000")
    assert wallet.frozen_amount == money("200000")


def test_freeze_rejects_insufficient_balance(
    advertiser_factory, campaign_factory, money
):
    user = advertiser_factory()
    UserBalance.objects.create(user=user, balance=money("10000"))
    campaign = campaign_factory(advertiser=user, budget=money("50000"))

    with pytest.raises(InsufficientBalanceError):
        freeze_for_campaign(campaign)

    # Hiçbir yan etki yok — balance değişmedi
    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == money("10000")
    assert wallet.frozen_amount == money("0")


# --- spend_from_frozen -------------------------------------------------------


def test_spend_from_frozen_reduces_frozen(
    placement_factory, advertiser_factory, money
):
    advertiser = advertiser_factory()
    UserBalance.objects.create(user=advertiser, balance=money("0"), frozen_amount=money("50000"))
    placement = placement_factory(ad__campaign__advertiser=advertiser)

    tx = spend_from_frozen(placement, money("10000"))

    assert tx.type == Transaction.Type.AD_SPEND
    wallet = UserBalance.objects.get(user=advertiser)
    assert wallet.frozen_amount == money("40000")
    assert wallet.balance == money("0")  # balance'a dokunulmadı


def test_spend_underrun_draws_from_balance(
    placement_factory, advertiser_factory, money
):
    advertiser = advertiser_factory()
    UserBalance.objects.create(user=advertiser, balance=money("5000"), frozen_amount=money("3000"))
    placement = placement_factory(ad__campaign__advertiser=advertiser)

    # Cost 7000 > frozen 3000, kalan 4000 balance'tan
    tx = spend_from_frozen(placement, money("7000"))

    assert tx.amount == money("7000")
    wallet = UserBalance.objects.get(user=advertiser)
    assert wallet.frozen_amount == money("0")
    assert wallet.balance == money("1000")  # 5000 - 4000


def test_spend_zero_is_noop(placement_factory, money):
    placement = placement_factory()
    result = spend_from_frozen(placement, money("0"))
    assert result is None


# --- credit_publisher --------------------------------------------------------


def test_credit_publisher_increments_balance(
    placement_factory, publisher_factory, channel_factory, money
):
    publisher = publisher_factory()
    channel = channel_factory(owner=publisher)
    placement = placement_factory(channel=channel)

    tx = credit_publisher(placement, money("3500"))

    assert tx.type == Transaction.Type.AD_EARNING
    wallet = UserBalance.objects.get(user=publisher)
    assert wallet.balance == money("3500")


def test_credit_publisher_zero_is_noop(placement_factory, money):
    placement = placement_factory()
    assert credit_publisher(placement, money("0")) is None


# --- refund_unspent_campaign -------------------------------------------------


def test_refund_returns_remaining_budget(
    campaign_factory, advertiser_factory, money
):
    user = advertiser_factory()
    UserBalance.objects.create(
        user=user, balance=money("0"), frozen_amount=money("100000"),
    )
    campaign = campaign_factory(
        advertiser=user, budget=money("100000"), spent=money("30000"),
    )

    tx = refund_unspent_campaign(campaign)

    assert tx.type == Transaction.Type.REFUND
    assert tx.amount == money("70000")
    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == money("70000")
    assert wallet.frozen_amount == money("30000")


def test_refund_noop_if_fully_spent(campaign_factory, advertiser_factory, money):
    user = advertiser_factory()
    UserBalance.objects.create(user=user, balance=money("0"))
    campaign = campaign_factory(
        advertiser=user, budget=money("50000"), spent=money("50000"),
    )

    assert refund_unspent_campaign(campaign) is None


def test_refund_clamps_to_available_frozen(
    campaign_factory, advertiser_factory, money
):
    """Frozen havuzu beklenenden az — sadece mevcut kadarı iade et."""
    user = advertiser_factory()
    UserBalance.objects.create(
        user=user, balance=money("0"), frozen_amount=money("20000"),
    )
    campaign = campaign_factory(
        advertiser=user, budget=money("100000"), spent=money("30000"),
    )
    # budget-spent = 70000 ama frozen sadece 20000

    tx = refund_unspent_campaign(campaign)

    assert tx.amount == money("20000")
    wallet = UserBalance.objects.get(user=user)
    assert wallet.frozen_amount == money("0")
    assert wallet.balance == money("20000")


# --- withdraw_for_payout -----------------------------------------------------


def test_withdraw_for_payout_reduces_balance(
    publisher_factory, payout_factory, money,
):
    publisher = publisher_factory()
    UserBalance.objects.create(user=publisher, balance=money("200000"))
    payout = payout_factory(user=publisher, amount=money("150000"))

    tx = withdraw_for_payout(payout)

    assert tx.type == Transaction.Type.WITHDRAW
    assert tx.status == Transaction.Status.PENDING  # provider ödemesi bekleniyor
    wallet = UserBalance.objects.get(user=publisher)
    assert wallet.balance == money("50000")


def test_withdraw_rejects_insufficient_balance(
    publisher_factory, payout_factory, money,
):
    publisher = publisher_factory()
    UserBalance.objects.create(user=publisher, balance=money("10000"))
    payout = payout_factory(user=publisher, amount=money("50000"))

    with pytest.raises(InsufficientBalanceError):
        withdraw_for_payout(payout)

    wallet = UserBalance.objects.get(user=publisher)
    assert wallet.balance == money("10000")  # değişmedi


# --- adjust ------------------------------------------------------------------


def test_adjust_credit_increases_balance(advertiser_factory, money):
    user = advertiser_factory()
    UserBalance.objects.create(user=user, balance=money("1000"))

    adjust(user, money("500"), description="bonus", direction="credit")

    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == money("1500")


def test_adjust_debit_requires_sufficient_balance(advertiser_factory, money):
    user = advertiser_factory()
    UserBalance.objects.create(user=user, balance=money("100"))

    with pytest.raises(InsufficientBalanceError):
        adjust(user, money("500"), description="correction", direction="debit")


def test_adjust_rejects_invalid_direction(advertiser_factory, money):
    user = advertiser_factory()
    with pytest.raises(ValueError):
        adjust(user, money("100"), description="x", direction="backwards")


# --- Transaction unique constraint ------------------------------------------


def test_duplicate_provider_ref_raises_integrity(advertiser_factory, money):
    """(provider, provider_ref) unique — aynı ref ikinci insert reddedilir."""
    from django.db import IntegrityError

    user = advertiser_factory()
    Transaction.objects.create(
        user=user, type=Transaction.Type.DEPOSIT,
        amount=money("100"), provider="click", provider_ref="dupe-x",
    )
    with pytest.raises(IntegrityError):
        Transaction.objects.create(
            user=user, type=Transaction.Type.DEPOSIT,
            amount=money("200"), provider="click", provider_ref="dupe-x",
        )


def test_empty_provider_ref_allows_multiple_rows(advertiser_factory, money):
    """Internal transaction'lar (provider_ref boş) birden çok satır olabilir."""
    user = advertiser_factory()
    Transaction.objects.create(
        user=user, type=Transaction.Type.AD_SPEND,
        amount=money("100"), provider="internal",
    )
    # İkinci satır aynı boş ref ile — IntegrityError olmamalı.
    Transaction.objects.create(
        user=user, type=Transaction.Type.AD_SPEND,
        amount=money("200"), provider="internal",
    )
    assert Transaction.objects.filter(user=user).count() == 2
