"""
Click.uz Merchant API entegrasyonu (FAZ 4a).

Webhook iki aşamalıdır:
1. **Prepare** (action=0): Click ödemeyi hazırlamadan önce çağırır; biz
   merchant_trans_id formatını doğrular, bir `pending` Transaction oluşturur
   ve `merchant_prepare_id` döneriz.
2. **Complete** (action=1): Ödeme gerçekleştikten sonra çağrılır; pending
   Transaction `completed`'a taşınır ve `payments.services.deposit()` ile
   bakiyeye yansıtılır.

İmza:
    prepare  = md5(click_trans_id + service_id + SECRET + merchant_trans_id
                  + amount + action + sign_time)
    complete = md5(click_trans_id + service_id + SECRET + merchant_trans_id
                  + merchant_prepare_id + amount + action + sign_time)

Not: Public dokümantasyona göre `amount` string'i iki ondalık basamaklıdır
("1000.00"); imza hesabında olduğu gibi kullanılır.

Error codes (Click spec):
     0: Success
    -1: SIGN CHECK FAILED
    -2: Incorrect parameter amount
    -3: Action not found
    -4: Already paid
    -5: User does not exist
    -6: Transaction does not exist
    -7: Failed to update user
    -8: Error in request from Click
    -9: Transaction cancelled
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from decimal import Decimal

from django.contrib.auth import get_user_model

from payments.models import Transaction
from payments.services import deposit

from .base import BasePaymentProvider, flatten_request_data, parse_merchant_trans_id

logger = logging.getLogger(__name__)
User = get_user_model()


CLICK_ACTION_PREPARE = 0
CLICK_ACTION_COMPLETE = 1


# Error code sabitleri — response body'lerinde kullanılır.
ERR_SUCCESS = 0
ERR_SIGN_CHECK = -1
ERR_INCORRECT_AMOUNT = -2
ERR_ACTION_NOT_FOUND = -3
ERR_ALREADY_PAID = -4
ERR_USER_NOT_FOUND = -5
ERR_TRANSACTION_NOT_FOUND = -6
ERR_FAILED_UPDATE = -7
ERR_BAD_REQUEST = -8
ERR_CANCELLED = -9


class ClickProvider(BasePaymentProvider):
    code = "click"

    def __init__(self):
        self.service_id = os.getenv("CLICK_SERVICE_ID", "")
        self.merchant_id = os.getenv("CLICK_MERCHANT_ID", "")
        self.secret_key = os.getenv("CLICK_SECRET_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.service_id and self.secret_key)

    # -- İmza ---------------------------------------------------------------

    def compute_signature(self, payload: dict) -> str:
        """Payload'daki action'a göre doğru imza string'ini üret."""
        action = int(payload.get("action", -1))
        parts = [
            str(payload.get("click_trans_id", "")),
            str(payload.get("service_id", "")),
            self.secret_key,
            str(payload.get("merchant_trans_id", "")),
        ]
        if action == CLICK_ACTION_COMPLETE:
            parts.append(str(payload.get("merchant_prepare_id", "")))
        parts.extend([
            str(payload.get("amount", "")),
            str(payload.get("action", "")),
            str(payload.get("sign_time", "")),
        ])
        raw = "".join(parts).encode("utf-8")
        return hashlib.md5(raw).hexdigest()

    def verify_signature(self, payload: dict) -> bool:
        given = str(payload.get("sign_string", ""))
        if not given:
            return False
        expected = self.compute_signature(payload)
        return hmac.compare_digest(expected, given)

    def verify_request(self, request) -> bool:
        return self.verify_signature(flatten_request_data(request))

    # -- Webhook dispatch ---------------------------------------------------

    def handle_webhook(self, request) -> tuple[dict, int]:
        payload = flatten_request_data(request)
        try:
            action = int(payload.get("action", -1))
        except (TypeError, ValueError):
            return self._error(ERR_BAD_REQUEST, "invalid action"), 200

        if action == CLICK_ACTION_PREPARE:
            return self.handle_prepare(payload), 200
        if action == CLICK_ACTION_COMPLETE:
            return self.handle_complete(payload), 200
        return self._error(ERR_ACTION_NOT_FOUND, "Action not found"), 200

    def handle_prepare(self, payload: dict) -> dict:
        """Aşama 1 — henüz para gelmedi; pending Transaction oluştur, prepare_id döndür."""
        merchant_trans_id = str(payload.get("merchant_trans_id", ""))
        click_trans_id = str(payload.get("click_trans_id", ""))

        user_id = parse_merchant_trans_id(merchant_trans_id)
        if user_id is None:
            return self._error(ERR_USER_NOT_FOUND, "invalid merchant_trans_id")

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return self._error(ERR_USER_NOT_FOUND, "User does not exist")

        try:
            amount = Decimal(str(payload.get("amount", "0")))
        except Exception:
            return self._error(ERR_INCORRECT_AMOUNT, "invalid amount")
        if amount <= 0:
            return self._error(ERR_INCORRECT_AMOUNT, "amount must be positive")

        # Idempotency — aynı click_trans_id geldiyse mevcut pending tx'i döndür.
        existing = Transaction.objects.filter(
            provider="click", provider_ref=click_trans_id
        ).first()
        if existing:
            # Zaten completed ise artık hazırlık yapılamaz.
            if existing.status == Transaction.Status.COMPLETED:
                return self._error(ERR_ALREADY_PAID, "Already paid")
            prepare_id = existing.id
        else:
            tx = Transaction.objects.create(
                user=user,
                type=Transaction.Type.DEPOSIT,
                status=Transaction.Status.PENDING,
                amount=amount,
                provider="click",
                provider_ref=click_trans_id,
                description=f"Click prepare {click_trans_id}",
            )
            prepare_id = tx.id

        return {
            "click_trans_id": payload.get("click_trans_id"),
            "merchant_trans_id": merchant_trans_id,
            "merchant_prepare_id": prepare_id,
            "error": ERR_SUCCESS,
            "error_note": "Success",
        }

    def handle_complete(self, payload: dict) -> dict:
        """Aşama 2 — para geldi, bakiye artır."""
        click_trans_id = str(payload.get("click_trans_id", ""))
        merchant_prepare_id = payload.get("merchant_prepare_id")

        try:
            tx = Transaction.objects.select_related("user").get(
                provider="click", provider_ref=click_trans_id
            )
        except Transaction.DoesNotExist:
            return self._error(ERR_TRANSACTION_NOT_FOUND, "Transaction not found")

        # Prepare id eşleşmeli.
        if merchant_prepare_id is not None and str(merchant_prepare_id) != str(tx.id):
            return self._error(ERR_TRANSACTION_NOT_FOUND, "prepare_id mismatch")

        # Cancelled ise reddet.
        if tx.status == Transaction.Status.CANCELLED:
            return self._error(ERR_CANCELLED, "Transaction cancelled")

        # Zaten completed ise idempotent — aynı yanıtı döneriz, tekrar deposit etmeyiz.
        if tx.status == Transaction.Status.COMPLETED:
            return {
                "click_trans_id": payload.get("click_trans_id"),
                "merchant_trans_id": payload.get("merchant_trans_id"),
                "merchant_confirm_id": tx.id,
                "error": ERR_SUCCESS,
                "error_note": "Already completed",
            }

        # Pending → COMPLETE: bakiye mutasyonu `deposit` servisi üzerinden.
        # Ancak `deposit` yeni tx yaratmaya çalışır — biz mevcut pending tx'i
        # güncellemek istiyoruz. Bu yüzden burada manuel olarak bakiyeyi artır
        # ve tx'i completed'a çek.
        from django.db import transaction as db_tx
        from payments.services import _lock_balance, _sync_user_balance_mirror

        with db_tx.atomic():
            balance = _lock_balance(tx.user)
            balance.balance += tx.amount
            balance.save(update_fields=["balance", "updated_at"])

            tx.status = Transaction.Status.COMPLETED
            tx.balance_after = balance.balance
            tx.frozen_after = balance.frozen_amount
            tx.description = f"Click complete {click_trans_id}"
            tx.save(update_fields=[
                "status", "balance_after", "frozen_after", "description",
            ])
            _sync_user_balance_mirror(tx.user, balance)

        return {
            "click_trans_id": payload.get("click_trans_id"),
            "merchant_trans_id": payload.get("merchant_trans_id"),
            "merchant_confirm_id": tx.id,
            "error": ERR_SUCCESS,
            "error_note": "Success",
        }

    @staticmethod
    def _error(code: int, note: str) -> dict:
        return {"error": code, "error_note": note}
