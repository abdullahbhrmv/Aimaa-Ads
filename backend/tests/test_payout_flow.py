"""
Publisher payout akışı testleri (FAZ 4a).

Akış:
  Publisher'ın UserBalance.balance'ı var (ad_earning'lerden)
  → PayoutRequest oluşturulur (status=pending)
  → Admin approve → withdraw_for_payout: balance düşer, Transaction(withdraw, PENDING)
  → Status PROCESSING (provider ödeme FAZ 4b'de completed'a çevirir)

Ayrıca:
  - Yetersiz bakiyede admin approve reddeder
  - MIN_PAYOUT_AMOUNT PaymentSettings'ten okunur
  - Transaction idempotency provider_ref üzerinden
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from core.models import PayoutRequest, User
from payments.models import PaymentSettings, Transaction, UserBalance


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="payout-root", email="p@example.test", password="x"
    )


def _approve_payout(admin_user, payout_id, note=""):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client.post(
        f"/api/admin-panel/payouts/{payout_id}/approve/",
        {"note": note},
        format="json",
    )


def _reject_payout(admin_user, payout_id, note=""):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client.post(
        f"/api/admin-panel/payouts/{payout_id}/reject/",
        {"note": note},
        format="json",
    )


# --- Happy path --------------------------------------------------------------


def test_payout_approve_deducts_balance_and_creates_transaction(
    admin_user, publisher_factory, payout_factory, money,
):
    publisher = publisher_factory()
    UserBalance.objects.create(user=publisher, balance=money("200000"))
    payout = payout_factory(
        user=publisher, amount=money("150000"),
        provider=PayoutRequest.Provider.CLICK,
        provider_account="+998901234567",
    )

    response = _approve_payout(admin_user, payout.id, note="ok")
    assert response.status_code == 200

    wallet = UserBalance.objects.get(user=publisher)
    assert wallet.balance == money("50000")

    tx = Transaction.objects.get(
        user=publisher,
        type=Transaction.Type.WITHDRAW,
        related_payout=payout,
    )
    # FAZ 4a: provider ödemesi tamamlanmadı → PENDING
    assert tx.status == Transaction.Status.PENDING
    assert tx.amount == money("150000")

    payout.refresh_from_db()
    assert payout.status == PayoutRequest.Status.PROCESSING


def test_payout_approve_rejects_insufficient_balance(
    admin_user, publisher_factory, payout_factory, money,
):
    publisher = publisher_factory()
    UserBalance.objects.create(user=publisher, balance=money("10000"))
    payout = payout_factory(user=publisher, amount=money("150000"))

    response = _approve_payout(admin_user, payout.id)
    assert response.status_code == 400

    payout.refresh_from_db()
    assert payout.status == PayoutRequest.Status.PENDING  # değişmemeli

    wallet = UserBalance.objects.get(user=publisher)
    assert wallet.balance == money("10000")  # dokunulmamış


def test_payout_reject_does_not_touch_balance(
    admin_user, publisher_factory, payout_factory, money,
):
    publisher = publisher_factory()
    UserBalance.objects.create(user=publisher, balance=money("200000"))
    payout = payout_factory(user=publisher, amount=money("100000"))

    response = _reject_payout(admin_user, payout.id, note="missing info")
    assert response.status_code == 200

    payout.refresh_from_db()
    assert payout.status == PayoutRequest.Status.REJECTED

    wallet = UserBalance.objects.get(user=publisher)
    assert wallet.balance == money("200000")  # değişmedi

    # Withdraw transaction oluşmamış olmalı
    assert not Transaction.objects.filter(
        user=publisher, type=Transaction.Type.WITHDRAW,
    ).exists()


# --- State transitions ------------------------------------------------------


def test_cannot_approve_already_processed_payout(
    admin_user, publisher_factory, payout_factory, money,
):
    publisher = publisher_factory()
    UserBalance.objects.create(user=publisher, balance=money("200000"))
    payout = payout_factory(
        user=publisher, amount=money("100000"),
        status=PayoutRequest.Status.COMPLETED,
    )

    response = _approve_payout(admin_user, payout.id)
    assert response.status_code == 400


# --- Provider field persistence ---------------------------------------------


def test_payout_provider_fields_are_stored(
    admin_user, publisher_factory, payout_factory, money,
):
    publisher = publisher_factory()
    UserBalance.objects.create(user=publisher, balance=money("200000"))
    payout = payout_factory(
        user=publisher, amount=money("50000"),
        provider=PayoutRequest.Provider.PAYME,
        provider_account="8600123412341234",
        provider_ref="payme-manual-ref-1",
    )

    _approve_payout(admin_user, payout.id)

    tx = Transaction.objects.get(related_payout=payout)
    # Withdraw transaction provider_ref'i PayoutRequest'ten alınır
    assert tx.provider == "payme"
    assert tx.provider_ref == "payme-manual-ref-1"


# --- PaymentSettings --------------------------------------------------------


def test_payment_settings_singleton_defaults():
    settings = PaymentSettings.get_solo()
    assert settings.min_payout_amount == Decimal("50000")
    assert settings.platform_commission_rate == Decimal("0.3000")
    assert settings.kdv_rate == Decimal("0.1200")


def test_payment_settings_singleton_is_idempotent():
    a = PaymentSettings.get_solo()
    b = PaymentSettings.get_solo()
    assert a.pk == b.pk
    assert PaymentSettings.objects.count() == 1
