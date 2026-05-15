"""
Payme Merchant API webhook testleri (FAZ 4a).

JSON-RPC 2.0 Basic Auth doğrulama + 6 metodun akışı.
"""

from __future__ import annotations

import base64
from decimal import Decimal

import pytest
from django.test import Client

from payments.models import PaymentAuditLog, Transaction, UserBalance


pytestmark = pytest.mark.django_db(transaction=True)


PAYME_URL = "/api/payments/payme/webhook/"


@pytest.fixture
def payme_env(monkeypatch):
    monkeypatch.setenv("PAYME_MERCHANT_ID", "merchant-x")
    monkeypatch.setenv("PAYME_MERCHANT_KEY", "test-key-abc")
    yield {"merchant_key": "test-key-abc"}


def _auth_header(key: str) -> str:
    token = base64.b64encode(f"Paycom:{key}".encode()).decode()
    return f"Basic {token}"


def _post_rpc(method: str, params: dict, key: str, req_id=1):
    body = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    return Client().post(
        PAYME_URL,
        body,
        content_type="application/json",
        HTTP_AUTHORIZATION=_auth_header(key),
    )


# --- Auth --------------------------------------------------------------------


def test_missing_auth_returns_unauthorized_error(payme_env):
    response = Client().post(
        PAYME_URL,
        {"jsonrpc": "2.0", "id": 1, "method": "CheckPerformTransaction", "params": {}},
        content_type="application/json",
    )
    assert response.json()["error"]["code"] == -32504


def test_wrong_key_returns_unauthorized_error(payme_env):
    response = Client().post(
        PAYME_URL,
        {"jsonrpc": "2.0", "id": 1, "method": "CheckPerformTransaction", "params": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=_auth_header("wrong-key"),
    )
    assert response.json()["error"]["code"] == -32504


def test_503_when_not_configured(monkeypatch):
    monkeypatch.delenv("PAYME_MERCHANT_KEY", raising=False)
    response = Client().post(
        PAYME_URL,
        {"jsonrpc": "2.0", "id": 1, "method": "CheckPerformTransaction", "params": {}},
        content_type="application/json",
    )
    assert response.status_code == 503


# --- CheckPerformTransaction ------------------------------------------------


def test_check_perform_transaction_allows_valid_user(payme_env, advertiser_factory):
    user = advertiser_factory()
    response = _post_rpc(
        "CheckPerformTransaction",
        {"amount": 100_00 * 500, "account": {"user_id": str(user.id)}},
        payme_env["merchant_key"],
    )
    assert response.json()["result"]["allow"] is True


def test_check_perform_transaction_rejects_invalid_account(payme_env):
    response = _post_rpc(
        "CheckPerformTransaction",
        {"amount": 1000_00, "account": {"user_id": "nonexistent"}},
        payme_env["merchant_key"],
    )
    assert response.json()["error"]["code"] == -31050


def test_check_perform_transaction_rejects_negative_amount(payme_env, advertiser_factory):
    user = advertiser_factory()
    response = _post_rpc(
        "CheckPerformTransaction",
        {"amount": -500, "account": {"user_id": str(user.id)}},
        payme_env["merchant_key"],
    )
    assert response.json()["error"]["code"] == -31001


# --- CreateTransaction -------------------------------------------------------


def test_create_transaction_persists_pending(payme_env, advertiser_factory):
    user = advertiser_factory()
    response = _post_rpc(
        "CreateTransaction",
        {
            "id": "payme-tx-1",
            "time": 1700000000000,
            "amount": 500000 * 100,  # 500 000 UZS in tiyin
            "account": {"user_id": str(user.id)},
        },
        payme_env["merchant_key"],
    )
    body = response.json()["result"]
    assert body["state"] == 1  # created

    tx = Transaction.objects.get(provider="payme", provider_ref="payme-tx-1")
    assert tx.status == Transaction.Status.PENDING
    assert tx.amount == Decimal("500000")

    # Bakiye artmamalı
    assert not UserBalance.objects.filter(user=user).exists() or \
        UserBalance.objects.get(user=user).balance == Decimal("0")


def test_create_transaction_is_idempotent(payme_env, advertiser_factory):
    user = advertiser_factory()
    params = {
        "id": "payme-idem",
        "time": 1700000000000,
        "amount": 100_00 * 100,
        "account": {"user_id": str(user.id)},
    }
    r1 = _post_rpc("CreateTransaction", params, payme_env["merchant_key"]).json()
    r2 = _post_rpc("CreateTransaction", params, payme_env["merchant_key"]).json()

    assert r1["result"]["transaction"] == r2["result"]["transaction"]
    assert Transaction.objects.filter(
        provider="payme", provider_ref="payme-idem"
    ).count() == 1


def test_create_transaction_accepts_order_id_account(payme_env, advertiser_factory):
    user = advertiser_factory()
    response = _post_rpc(
        "CreateTransaction",
        {
            "id": "payme-order-1",
            "amount": 10000 * 100,
            "account": {"order_id": f"deposit-{user.id}-n1"},
        },
        payme_env["merchant_key"],
    )
    assert response.json()["result"]["state"] == 1


# --- PerformTransaction ------------------------------------------------------


def test_perform_credits_balance(payme_env, advertiser_factory):
    user = advertiser_factory(balance=Decimal("0"))
    _post_rpc(
        "CreateTransaction",
        {
            "id": "payme-perf-1",
            "amount": 250000 * 100,
            "account": {"user_id": str(user.id)},
        },
        payme_env["merchant_key"],
    )
    response = _post_rpc(
        "PerformTransaction",
        {"id": "payme-perf-1"},
        payme_env["merchant_key"],
    )
    assert response.json()["result"]["state"] == 2  # performed
    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == Decimal("250000")


def test_perform_is_idempotent(payme_env, advertiser_factory):
    user = advertiser_factory(balance=Decimal("0"))
    _post_rpc(
        "CreateTransaction",
        {
            "id": "payme-perf-dup",
            "amount": 100000 * 100,
            "account": {"user_id": str(user.id)},
        },
        payme_env["merchant_key"],
    )
    _post_rpc("PerformTransaction", {"id": "payme-perf-dup"}, payme_env["merchant_key"])
    _post_rpc("PerformTransaction", {"id": "payme-perf-dup"}, payme_env["merchant_key"])

    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == Decimal("100000")  # bir kere artmış


def test_perform_unknown_id_returns_error(payme_env):
    response = _post_rpc(
        "PerformTransaction",
        {"id": "ghost"},
        payme_env["merchant_key"],
    )
    assert response.json()["error"]["code"] == -31003


# --- CancelTransaction ------------------------------------------------------


def test_cancel_before_perform_marks_cancelled(payme_env, advertiser_factory):
    user = advertiser_factory()
    _post_rpc(
        "CreateTransaction",
        {"id": "payme-cancel-1", "amount": 50000 * 100,
         "account": {"user_id": str(user.id)}},
        payme_env["merchant_key"],
    )
    response = _post_rpc(
        "CancelTransaction",
        {"id": "payme-cancel-1", "reason": 5},
        payme_env["merchant_key"],
    )
    assert response.json()["result"]["state"] == -1  # cancelled before perform

    # Bakiye etkilenmemeli
    assert not UserBalance.objects.filter(user=user, balance__gt=0).exists()


def test_cancel_after_perform_reverses_balance(payme_env, advertiser_factory):
    user = advertiser_factory()
    _post_rpc(
        "CreateTransaction",
        {"id": "payme-cancel-2", "amount": 80000 * 100,
         "account": {"user_id": str(user.id)}},
        payme_env["merchant_key"],
    )
    _post_rpc("PerformTransaction", {"id": "payme-cancel-2"}, payme_env["merchant_key"])

    wallet = UserBalance.objects.get(user=user)
    assert wallet.balance == Decimal("80000")

    response = _post_rpc(
        "CancelTransaction",
        {"id": "payme-cancel-2", "reason": 3},
        payme_env["merchant_key"],
    )
    assert response.json()["result"]["state"] == -2

    wallet.refresh_from_db()
    assert wallet.balance == Decimal("0")


def test_cancel_after_perform_rejected_when_balance_spent(payme_env, advertiser_factory):
    """Kullanıcı parayı harcamışsa iptal edilmez."""
    user = advertiser_factory()
    _post_rpc(
        "CreateTransaction",
        {"id": "payme-cancel-3", "amount": 80000 * 100,
         "account": {"user_id": str(user.id)}},
        payme_env["merchant_key"],
    )
    _post_rpc("PerformTransaction", {"id": "payme-cancel-3"}, payme_env["merchant_key"])

    # Para harcandı — balance düşür
    wallet = UserBalance.objects.get(user=user)
    wallet.balance = Decimal("0")
    wallet.save()

    response = _post_rpc(
        "CancelTransaction",
        {"id": "payme-cancel-3", "reason": 3},
        payme_env["merchant_key"],
    )
    assert response.json()["error"]["code"] == -31007


# --- CheckTransaction -------------------------------------------------------


def test_check_transaction_returns_state(payme_env, advertiser_factory):
    user = advertiser_factory()
    _post_rpc(
        "CreateTransaction",
        {"id": "payme-chk-1", "amount": 10000 * 100,
         "account": {"user_id": str(user.id)}},
        payme_env["merchant_key"],
    )
    response = _post_rpc("CheckTransaction", {"id": "payme-chk-1"}, payme_env["merchant_key"])
    assert response.json()["result"]["state"] == 1


# --- GetStatement -----------------------------------------------------------


def test_get_statement_returns_performed_transactions(payme_env, advertiser_factory):
    user = advertiser_factory()
    _post_rpc(
        "CreateTransaction",
        {"id": "payme-stmt-1", "amount": 10000 * 100,
         "account": {"user_id": str(user.id)}},
        payme_env["merchant_key"],
    )
    _post_rpc("PerformTransaction", {"id": "payme-stmt-1"}, payme_env["merchant_key"])

    response = _post_rpc(
        "GetStatement",
        {"from": 0, "to": 9999999999999},
        payme_env["merchant_key"],
    )
    txs = response.json()["result"]["transactions"]
    assert any(t["id"] == "payme-stmt-1" for t in txs)


# --- Unknown method ---------------------------------------------------------


def test_unknown_method_returns_method_not_found(payme_env):
    response = _post_rpc("DoSomethingWeird", {}, payme_env["merchant_key"])
    assert response.json()["error"]["code"] == -32601


# --- Audit log --------------------------------------------------------------


def test_webhook_creates_audit_log(payme_env, advertiser_factory):
    user = advertiser_factory()
    _post_rpc(
        "CheckPerformTransaction",
        {"amount": 1000 * 100, "account": {"user_id": str(user.id)}},
        payme_env["merchant_key"],
    )
    log = PaymentAuditLog.objects.filter(provider="payme").first()
    assert log is not None
    assert log.signature_valid is True
