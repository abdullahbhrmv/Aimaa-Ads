"""
Payme Merchant API entegrasyonu (FAZ 4a).

Payme JSON-RPC 2.0 protokolü ile çalışır. Webhook endpoint'i tek bir URL'dir;
`method` alanı hangi işlemin istendiğini belirtir.

Desteklenen metodlar:
- CheckPerformTransaction: "Bu tutarla bu hesaba ödeme mümkün mü?" — no-op
  doğrulama, Transaction yaratılmaz.
- CreateTransaction: Yeni transaction kaydı yarat (status=1 create).
- PerformTransaction: Transaction'ı tamamla, bakiyeye yansıt (status=2 perform).
- CancelTransaction: İptal et; gerekirse ters kayıt (status=-1 cancelled before perform,
  -2 cancelled after perform).
- CheckTransaction: Durum sorgu.
- GetStatement: Tarih aralığında raporlama (FAZ 4b'de gerçek veri, şimdilik boş liste).

Doğrulama:
- `Authorization: Basic base64(Paycom:MERCHANT_KEY)` header'ı zorunlu.
- Eksik veya yanlış → `-32504` error.

Error codes (Payme spec, FAZ 4a için kritik olanlar):
    -32504: Insufficient privileges (auth)
    -32601: Method not found
    -32602: Invalid params
    -32400: System error
    -31001: Invalid amount
    -31003: Transaction not found
    -31007: Cannot cancel
    -31008: Cannot perform
    -31050..-31099: Account validation
"""

from __future__ import annotations

import base64
import binascii
import hmac
import logging
import os
from datetime import datetime, timezone as dt_tz
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction as db_tx
from django.utils import timezone

from payments.models import Transaction
from payments.services import _lock_balance, _sync_user_balance_mirror

from .base import BasePaymentProvider, parse_merchant_trans_id

logger = logging.getLogger(__name__)
User = get_user_model()


# Payme error codes
PAYME_ERR_UNAUTHORIZED = -32504
PAYME_ERR_METHOD_NOT_FOUND = -32601
PAYME_ERR_INVALID_PARAMS = -32602
PAYME_ERR_SYSTEM = -32400
PAYME_ERR_INVALID_AMOUNT = -31001
PAYME_ERR_TRANSACTION_NOT_FOUND = -31003
PAYME_ERR_CANNOT_CANCEL = -31007
PAYME_ERR_CANNOT_PERFORM = -31008
PAYME_ERR_INVALID_ACCOUNT = -31050


# Payme kendi status şemasını kullanır — bizim Transaction.status'tan ayrı
PAYME_STATUS_CREATED = 1
PAYME_STATUS_PERFORMED = 2
PAYME_STATUS_CANCELLED_BEFORE = -1
PAYME_STATUS_CANCELLED_AFTER = -2


class PaymeProvider(BasePaymentProvider):
    code = "payme"

    def __init__(self):
        self.merchant_key = os.getenv("PAYME_MERCHANT_KEY", "")
        self.merchant_id = os.getenv("PAYME_MERCHANT_ID", "")

    def is_configured(self) -> bool:
        return bool(self.merchant_key)

    # -- Basic auth doğrulama -----------------------------------------------

    def verify_basic_auth(self, auth_header: str) -> bool:
        if not auth_header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return False
        _, sep, password = decoded.partition(":")
        if not sep:
            return False
        return hmac.compare_digest(password, self.merchant_key)

    def verify_request(self, request) -> bool:
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        return self.verify_basic_auth(auth)

    # -- JSON-RPC dispatch --------------------------------------------------

    def handle_webhook(self, request) -> tuple[dict, int]:
        payload = request.data or {}
        req_id = payload.get("id")
        method = payload.get("method", "")
        params = payload.get("params", {}) or {}

        try:
            if method == "CheckPerformTransaction":
                result = self.check_perform_transaction(params)
            elif method == "CreateTransaction":
                result = self.create_transaction(params)
            elif method == "PerformTransaction":
                result = self.perform_transaction(params)
            elif method == "CancelTransaction":
                result = self.cancel_transaction(params)
            elif method == "CheckTransaction":
                result = self.check_transaction(params)
            elif method == "GetStatement":
                result = self.get_statement(params)
            else:
                return self._rpc_error(req_id, PAYME_ERR_METHOD_NOT_FOUND, "Method not found"), 200
        except _PaymeError as exc:
            return self._rpc_error(req_id, exc.code, exc.message, exc.data), 200
        except Exception as exc:
            logger.exception("Payme unhandled error: %s", exc)
            return self._rpc_error(req_id, PAYME_ERR_SYSTEM, "System error"), 200

        return {"jsonrpc": "2.0", "id": req_id, "result": result}, 200

    # -- Method implementations ---------------------------------------------

    def check_perform_transaction(self, params: dict) -> dict:
        account = params.get("account", {}) or {}
        amount_tiyin = params.get("amount")
        user = self._resolve_user(account)
        self._validate_amount(amount_tiyin)
        # Herhangi bir iş kuralı (min/max amount, kullanıcı rolü, vs.) burada
        # kontrol edilebilir. Şimdilik sadece kullanıcı varsa allow.
        _ = user  # referans — silme
        return {"allow": True}

    def create_transaction(self, params: dict) -> dict:
        tx_id = params.get("id")
        if not tx_id:
            raise _PaymeError(PAYME_ERR_INVALID_PARAMS, "id required")

        amount_tiyin = params.get("amount")
        self._validate_amount(amount_tiyin)
        amount_uzs = Decimal(amount_tiyin) / Decimal(100)

        account = params.get("account", {}) or {}
        user = self._resolve_user(account)

        time_ms = params.get("time") or int(timezone.now().timestamp() * 1000)

        # Idempotency — aynı id ikinci kez gelirse mevcut tx'i döndür.
        existing = Transaction.objects.filter(
            provider="payme", provider_ref=str(tx_id)
        ).first()
        if existing:
            if existing.status == Transaction.Status.CANCELLED:
                raise _PaymeError(PAYME_ERR_CANNOT_PERFORM, "Cannot create cancelled transaction")
            return {
                "create_time": time_ms,
                "transaction": str(existing.pk),
                "state": _payme_state_for(existing),
            }

        tx = Transaction.objects.create(
            user=user,
            type=Transaction.Type.DEPOSIT,
            status=Transaction.Status.PENDING,
            amount=amount_uzs,
            provider="payme",
            provider_ref=str(tx_id),
            description=f"Payme create {tx_id}",
        )
        return {
            "create_time": time_ms,
            "transaction": str(tx.pk),
            "state": PAYME_STATUS_CREATED,
        }

    def perform_transaction(self, params: dict) -> dict:
        tx_id = params.get("id")
        tx = self._get_tx(tx_id)

        if tx.status == Transaction.Status.CANCELLED:
            raise _PaymeError(PAYME_ERR_CANNOT_PERFORM, "Transaction cancelled")

        if tx.status == Transaction.Status.COMPLETED:
            # Idempotent — zaten perform edildi.
            return {
                "transaction": str(tx.pk),
                "perform_time": int(tx.created_at.timestamp() * 1000),
                "state": PAYME_STATUS_PERFORMED,
            }

        with db_tx.atomic():
            balance = _lock_balance(tx.user)
            balance.balance += tx.amount
            balance.save(update_fields=["balance", "updated_at"])

            tx.status = Transaction.Status.COMPLETED
            tx.balance_after = balance.balance
            tx.frozen_after = balance.frozen_amount
            tx.description = f"Payme perform {tx_id}"
            tx.save(update_fields=[
                "status", "balance_after", "frozen_after", "description",
            ])
            _sync_user_balance_mirror(tx.user, balance)

        return {
            "transaction": str(tx.pk),
            "perform_time": int(timezone.now().timestamp() * 1000),
            "state": PAYME_STATUS_PERFORMED,
        }

    def cancel_transaction(self, params: dict) -> dict:
        tx_id = params.get("id")
        reason = params.get("reason")
        tx = self._get_tx(tx_id)

        if tx.status == Transaction.Status.CANCELLED:
            return {
                "transaction": str(tx.pk),
                "cancel_time": int(timezone.now().timestamp() * 1000),
                "state": _payme_state_for(tx),
            }

        # Perform edildikten sonra iptal: bakiyeyi geri al.
        if tx.status == Transaction.Status.COMPLETED:
            with db_tx.atomic():
                balance = _lock_balance(tx.user)
                if balance.balance < tx.amount:
                    # Para zaten harcanmış olabilir — iptal mümkün değil.
                    raise _PaymeError(PAYME_ERR_CANNOT_CANCEL, "Cannot cancel after spend")
                balance.balance -= tx.amount
                balance.save(update_fields=["balance", "updated_at"])

                tx.status = Transaction.Status.CANCELLED
                tx.balance_after = balance.balance
                tx.frozen_after = balance.frozen_amount
                tx.description = f"Payme cancel (after perform) reason={reason}"
                tx.save(update_fields=[
                    "status", "balance_after", "frozen_after", "description",
                ])
                _sync_user_balance_mirror(tx.user, balance)
        else:
            tx.status = Transaction.Status.CANCELLED
            tx.description = f"Payme cancel (before perform) reason={reason}"
            tx.save(update_fields=["status", "description"])

        return {
            "transaction": str(tx.pk),
            "cancel_time": int(timezone.now().timestamp() * 1000),
            "state": _payme_state_for(tx),
        }

    def check_transaction(self, params: dict) -> dict:
        tx_id = params.get("id")
        tx = self._get_tx(tx_id)
        created = int(tx.created_at.timestamp() * 1000)
        perform_time = 0
        cancel_time = 0
        if tx.status == Transaction.Status.COMPLETED:
            perform_time = created  # prod'da ayrı alan tutulabilir
        if tx.status == Transaction.Status.CANCELLED:
            cancel_time = created
        return {
            "create_time": created,
            "perform_time": perform_time,
            "cancel_time": cancel_time,
            "transaction": str(tx.pk),
            "state": _payme_state_for(tx),
            "reason": None,
        }

    def get_statement(self, params: dict) -> dict:
        """Belirtilen aralıktaki perform edilmiş transaction'ları döndür."""
        from_ms = params.get("from")
        to_ms = params.get("to")
        if from_ms is None or to_ms is None:
            raise _PaymeError(PAYME_ERR_INVALID_PARAMS, "from/to required")

        qs = Transaction.objects.filter(
            provider="payme",
            status=Transaction.Status.COMPLETED,
            created_at__gte=datetime.fromtimestamp(from_ms / 1000, tz=dt_tz.utc),
            created_at__lte=datetime.fromtimestamp(to_ms / 1000, tz=dt_tz.utc),
        ).order_by("created_at")

        transactions = []
        for tx in qs:
            created_ms = int(tx.created_at.timestamp() * 1000)
            transactions.append({
                "id": tx.provider_ref,
                "time": created_ms,
                "amount": int(tx.amount * Decimal(100)),
                "account": {"user_id": str(tx.user_id)},
                "create_time": created_ms,
                "perform_time": created_ms,
                "cancel_time": 0,
                "transaction": str(tx.pk),
                "state": _payme_state_for(tx),
                "reason": None,
            })
        return {"transactions": transactions}

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _resolve_user(account: dict):
        """`account` parametresinden user'ı bul.

        Konvansiyon: `account.user_id` (string veya int) — Payme merchant
        ayarlarında account field olarak `user_id` tanımlanmalı.
        """
        raw = account.get("user_id")
        if raw is None:
            # Merchant_trans_id tarzı fallback için `order_id` de kabul et.
            raw = account.get("order_id")
        if raw is None:
            raise _PaymeError(PAYME_ERR_INVALID_ACCOUNT, "user_id missing")

        # `order_id` deposit-<uid>-<nonce> formatı da olabilir.
        if isinstance(raw, str) and raw.startswith("deposit-"):
            uid = parse_merchant_trans_id(raw)
        else:
            try:
                uid = int(raw)
            except (TypeError, ValueError):
                raise _PaymeError(PAYME_ERR_INVALID_ACCOUNT, "invalid user_id")

        if uid is None:
            raise _PaymeError(PAYME_ERR_INVALID_ACCOUNT, "invalid account")

        try:
            return User.objects.get(pk=uid)
        except User.DoesNotExist:
            raise _PaymeError(PAYME_ERR_INVALID_ACCOUNT, "User not found")

    @staticmethod
    def _validate_amount(amount_tiyin) -> None:
        try:
            amount = int(amount_tiyin)
        except (TypeError, ValueError):
            raise _PaymeError(PAYME_ERR_INVALID_AMOUNT, "invalid amount")
        if amount <= 0:
            raise _PaymeError(PAYME_ERR_INVALID_AMOUNT, "amount must be positive")

    @staticmethod
    def _get_tx(tx_id):
        if not tx_id:
            raise _PaymeError(PAYME_ERR_TRANSACTION_NOT_FOUND, "id required")
        try:
            return Transaction.objects.select_related("user").get(
                provider="payme", provider_ref=str(tx_id)
            )
        except Transaction.DoesNotExist:
            raise _PaymeError(PAYME_ERR_TRANSACTION_NOT_FOUND, "Transaction not found")

    @staticmethod
    def _rpc_error(req_id, code: int, message: str, data=None) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": {
                    "uz": message,
                    "ru": message,
                    "en": message,
                },
                "data": data,
            },
        }


def _payme_state_for(tx: Transaction) -> int:
    """Bizim Transaction.status → Payme state kodu."""
    if tx.status == Transaction.Status.CANCELLED:
        # Was it cancelled before or after perform?
        # Approximation: if balance_after is None, it was cancelled before perform.
        if tx.balance_after is None:
            return PAYME_STATUS_CANCELLED_BEFORE
        return PAYME_STATUS_CANCELLED_AFTER
    if tx.status == Transaction.Status.COMPLETED:
        return PAYME_STATUS_PERFORMED
    return PAYME_STATUS_CREATED


class _PaymeError(Exception):
    def __init__(self, code: int, message: str, data=None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)
