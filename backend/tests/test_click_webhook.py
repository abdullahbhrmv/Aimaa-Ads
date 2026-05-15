"""
Click.uz webhook testleri (FAZ 4a).

Click env var'ları test ortamında monkeypatch ile set edilir; webhook
yapılandırılmamışsa 503 döner.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest
from django.test import Client

from payments.models import PaymentAuditLog, Transaction, UserBalance


pytestmark = pytest.mark.django_db(transaction=True)


CLICK_URL = "/api/payments/click/webhook/"


@pytest.fixture
def click_env(monkeypatch):
    """Click env var'larını test ortamı için set et."""
    monkeypatch.setenv("CLICK_SERVICE_ID", "12345")
    monkeypatch.setenv("CLICK_MERCHANT_ID", "67890")
    monkeypatch.setenv("CLICK_SECRET_KEY", "test-secret-xyz")
    yield {
        "service_id": "12345",
        "merchant_id": "67890",
        "secret_key": "test-secret-xyz",
    }


def _sign_prepare(payload: dict, secret: str) -> str:
    parts = [
        payload["click_trans_id"],
        payload["service_id"],
        secret,
        payload["merchant_trans_id"],
        payload["amount"],
        payload["action"],
        payload["sign_time"],
    ]
    raw = "".join(str(p) for p in parts).encode()
    return hashlib.md5(raw).hexdigest()


def _sign_complete(payload: dict, secret: str) -> str:
    parts = [
        payload["click_trans_id"],
        payload["service_id"],
        secret,
        payload["merchant_trans_id"],
        payload["merchant_prepare_id"],
        payload["amount"],
        payload["action"],
        payload["sign_time"],
    ]
    raw = "".join(str(p) for p in parts).encode()
    return hashlib.md5(raw).hexdigest()


# --- Signature verification --------------------------------------------------


def test_webhook_rejects_invalid_signature(click_env, advertiser_factory):
    user = advertiser_factory()
    payload = {
        "click_trans_id": "abc",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-n1",
        "amount": "50000.00",
        "action": "0",
        "sign_time": "2026-01-01 00:00:00",
        "sign_string": "wrongwrongwrongwrongwrongwrongwrongwrong",
    }
    response = Client().post(CLICK_URL, payload)
    assert response.status_code == 200
    assert response.json()["error"] == -1

    audit = PaymentAuditLog.objects.filter(provider="click").first()
    assert audit.signature_valid is False


def test_webhook_503_when_provider_not_configured(monkeypatch, advertiser_factory):
    # Env'leri temizle
    monkeypatch.delenv("CLICK_SECRET_KEY", raising=False)
    monkeypatch.delenv("CLICK_SERVICE_ID", raising=False)
    user = advertiser_factory()
    payload = {
        "click_trans_id": "abc",
        "service_id": "",
        "merchant_trans_id": f"deposit-{user.id}-n1",
        "amount": "50000.00",
        "action": "0",
        "sign_time": "2026-01-01 00:00:00",
        "sign_string": "x",
    }
    response = Client().post(CLICK_URL, payload)
    assert response.status_code == 503


# --- Prepare (action=0) -----------------------------------------------------


def test_prepare_creates_pending_transaction(click_env, advertiser_factory):
    user = advertiser_factory()
    payload = {
        "click_trans_id": "abc-001",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-n1",
        "amount": "50000.00",
        "action": "0",
        "sign_time": "2026-01-01 00:00:00",
    }
    payload["sign_string"] = _sign_prepare(payload, click_env["secret_key"])

    response = Client().post(CLICK_URL, payload)
    body = response.json()
    assert body["error"] == 0
    assert "merchant_prepare_id" in body

    tx = Transaction.objects.get(provider="click", provider_ref="abc-001")
    assert tx.status == Transaction.Status.PENDING
    assert tx.amount == Decimal("50000.00")
    # Bakiye henüz artmamalı
    wallet = UserBalance.objects.filter(user=user).first()
    assert wallet is None or wallet.balance == Decimal("0")


def test_prepare_rejects_invalid_merchant_trans_id(click_env):
    payload = {
        "click_trans_id": "abc-002",
        "service_id": click_env["service_id"],
        "merchant_trans_id": "malformed",
        "amount": "50000.00",
        "action": "0",
        "sign_time": "2026-01-01 00:00:00",
    }
    payload["sign_string"] = _sign_prepare(payload, click_env["secret_key"])

    response = Client().post(CLICK_URL, payload)
    assert response.json()["error"] == -5  # USER_NOT_FOUND


def test_prepare_rejects_nonexistent_user(click_env):
    payload = {
        "click_trans_id": "abc-003",
        "service_id": click_env["service_id"],
        "merchant_trans_id": "deposit-999999-n1",
        "amount": "50000.00",
        "action": "0",
        "sign_time": "2026-01-01 00:00:00",
    }
    payload["sign_string"] = _sign_prepare(payload, click_env["secret_key"])
    response = Client().post(CLICK_URL, payload)
    assert response.json()["error"] == -5


def test_prepare_rejects_non_positive_amount(click_env, advertiser_factory):
    user = advertiser_factory()
    payload = {
        "click_trans_id": "abc-004",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-n2",
        "amount": "0.00",
        "action": "0",
        "sign_time": "2026-01-01 00:00:00",
    }
    payload["sign_string"] = _sign_prepare(payload, click_env["secret_key"])
    response = Client().post(CLICK_URL, payload)
    assert response.json()["error"] == -2


# --- Complete (action=1) ----------------------------------------------------


def test_complete_credits_balance(click_env, advertiser_factory):
    user = advertiser_factory(balance=Decimal("0"))

    # 1) Prepare
    prepare = {
        "click_trans_id": "full-001",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-done",
        "amount": "75000.00",
        "action": "0",
        "sign_time": "2026-01-01 00:00:00",
    }
    prepare["sign_string"] = _sign_prepare(prepare, click_env["secret_key"])
    prep_resp = Client().post(CLICK_URL, prepare).json()
    prepare_id = prep_resp["merchant_prepare_id"]

    # 2) Complete
    complete = {
        "click_trans_id": "full-001",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-done",
        "merchant_prepare_id": str(prepare_id),
        "amount": "75000.00",
        "action": "1",
        "sign_time": "2026-01-01 00:00:05",
    }
    complete["sign_string"] = _sign_complete(complete, click_env["secret_key"])

    response = Client().post(CLICK_URL, complete)
    body = response.json()
    assert body["error"] == 0
    assert body["merchant_confirm_id"] == prepare_id

    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == Decimal("75000.00")

    tx = Transaction.objects.get(provider="click", provider_ref="full-001")
    assert tx.status == Transaction.Status.COMPLETED


def test_complete_is_idempotent_on_replay(click_env, advertiser_factory):
    """Complete iki kez gelirse bakiye bir kere artar — replay attack koruması."""
    user = advertiser_factory(balance=Decimal("0"))

    prepare = {
        "click_trans_id": "idem-001",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-idem",
        "amount": "30000.00",
        "action": "0",
        "sign_time": "2026-01-01 00:00:00",
    }
    prepare["sign_string"] = _sign_prepare(prepare, click_env["secret_key"])
    prep_resp = Client().post(CLICK_URL, prepare).json()
    prepare_id = prep_resp["merchant_prepare_id"]

    complete = {
        "click_trans_id": "idem-001",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-idem",
        "merchant_prepare_id": str(prepare_id),
        "amount": "30000.00",
        "action": "1",
        "sign_time": "2026-01-01 00:00:05",
    }
    complete["sign_string"] = _sign_complete(complete, click_env["secret_key"])

    Client().post(CLICK_URL, complete)
    Client().post(CLICK_URL, complete)  # replay

    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == Decimal("30000.00")  # bir kez


def test_complete_without_prepare_is_rejected(click_env, advertiser_factory):
    user = advertiser_factory()
    complete = {
        "click_trans_id": "orphan-001",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-x",
        "merchant_prepare_id": "999",
        "amount": "10000.00",
        "action": "1",
        "sign_time": "2026-01-01 00:00:05",
    }
    complete["sign_string"] = _sign_complete(complete, click_env["secret_key"])
    response = Client().post(CLICK_URL, complete)
    assert response.json()["error"] == -6  # TRANSACTION_NOT_FOUND


# --- Other actions ----------------------------------------------------------


def test_unknown_action_returns_action_not_found(click_env, advertiser_factory):
    user = advertiser_factory()
    payload = {
        "click_trans_id": "xyz",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-?",
        "amount": "10000.00",
        "action": "99",
        "sign_time": "2026-01-01 00:00:00",
    }
    # Compute signature as if it were prepare format (action=99 fallback)
    parts = [
        payload["click_trans_id"], payload["service_id"], click_env["secret_key"],
        payload["merchant_trans_id"], payload["amount"], payload["action"],
        payload["sign_time"],
    ]
    payload["sign_string"] = hashlib.md5("".join(parts).encode()).hexdigest()

    response = Client().post(CLICK_URL, payload)
    assert response.json()["error"] == -3


# --- Audit log --------------------------------------------------------------


def test_every_webhook_call_creates_audit_log(click_env, advertiser_factory):
    user = advertiser_factory()
    payload = {
        "click_trans_id": "aud-1",
        "service_id": click_env["service_id"],
        "merchant_trans_id": f"deposit-{user.id}-a",
        "amount": "1000.00",
        "action": "0",
        "sign_time": "2026-01-01 00:00:00",
    }
    payload["sign_string"] = _sign_prepare(payload, click_env["secret_key"])
    Client().post(CLICK_URL, payload)

    log = PaymentAuditLog.objects.filter(provider="click").first()
    assert log is not None
    assert log.signature_valid is True
    assert log.payload["click_trans_id"] == "aud-1"
