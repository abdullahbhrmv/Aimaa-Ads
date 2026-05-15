"""
Payments HTTP endpoints (FAZ 4a).

Endpoint'ler:
- `GET /api/payments/balance/`      → kullanıcının cüzdanı (auth gerekli)
- `GET /api/payments/transactions/` → işlem geçmişi (auth gerekli)
- `GET /api/payments/invoices/`     → faturalar (auth gerekli)
- `POST /api/payments/click/webhook/` → Click.uz webhook (public, HMAC)
- `POST /api/payments/payme/webhook/` → Payme webhook (public, Basic Auth)

Webhook endpoint'leri:
- IP bazlı rate limiting
- Her çağrı `PaymentAuditLog` satırı bırakır (signature_valid ayarlı)
- Provider env'de yapılandırılmamışsa `503` döner (FAZ 4b key'ler gelince
  aktif olur)
"""

from __future__ import annotations

import logging

from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice, PaymentAuditLog, Transaction, UserBalance
from .providers import ClickProvider, PaymeProvider, ProviderNotConfiguredError
from .providers.base import flatten_request_data
from .serializers import (
    InvoiceSerializer, TransactionSerializer, UserBalanceSerializer,
)
from .throttle import ClickWebhookThrottle, PaymeWebhookThrottle

logger = logging.getLogger(__name__)


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# --- Authenticated endpoints (UI için) --------------------------------------


class MyBalanceView(generics.RetrieveAPIView):
    """Giriş yapmış kullanıcının cüzdan özetini döner."""

    serializer_class = UserBalanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        obj, _ = UserBalance.objects.get_or_create(user=self.request.user)
        return obj


class MyTransactionsView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)


class MyInvoicesView(generics.ListAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.filter(user=self.request.user)


# --- Webhook endpoints (public) ---------------------------------------------


class ClickWebhookView(APIView):
    """Click.uz merchant webhook.

    Click iki aşamalı çağrı yapar (action=0 prepare, action=1 complete).
    Her iki aşamada aynı endpoint çağrılır; dispatch payload.action'a göre.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ClickWebhookThrottle]

    def post(self, request):
        provider = ClickProvider()
        audit = PaymentAuditLog.objects.create(
            event_type="webhook_received",
            provider="click",
            payload=flatten_request_data(request),
            ip_address=_client_ip(request),
        )

        if not provider.is_configured():
            audit.result = "error"
            audit.error_message = "provider not configured"
            audit.save(update_fields=["result", "error_message"])
            return Response(
                {"error": -8, "error_note": "Provider not configured"},
                status=503,
            )

        if not provider.verify_request(request):
            audit.signature_valid = False
            audit.result = "rejected"
            audit.save(update_fields=["signature_valid", "result"])
            return Response({"error": -1, "error_note": "SIGN CHECK FAILED"})

        audit.signature_valid = True
        try:
            body, status_code = provider.handle_webhook(request)
            audit.result = "success" if body.get("error", 0) >= 0 else "rejected"
            audit.error_message = str(body.get("error_note", ""))
            audit.save(update_fields=["signature_valid", "result", "error_message"])
            return Response(body, status=status_code)
        except ProviderNotConfiguredError as exc:
            audit.result = "error"
            audit.error_message = str(exc)
            audit.save(update_fields=["signature_valid", "result", "error_message"])
            return Response({"error": -8, "error_note": str(exc)}, status=503)
        except Exception as exc:
            logger.exception("Click webhook handler failed: %s", exc)
            audit.result = "error"
            audit.error_message = str(exc)
            audit.save(update_fields=["signature_valid", "result", "error_message"])
            return Response({"error": -8, "error_note": "internal error"})


class PaymeWebhookView(APIView):
    """Payme merchant webhook — JSON-RPC 2.0."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PaymeWebhookThrottle]

    def post(self, request):
        provider = PaymeProvider()
        audit = PaymentAuditLog.objects.create(
            event_type="webhook_received",
            provider="payme",
            payload=flatten_request_data(request),
            ip_address=_client_ip(request),
        )

        if not provider.is_configured():
            audit.result = "error"
            audit.error_message = "provider not configured"
            audit.save(update_fields=["result", "error_message"])
            # Payme spec gereği system error döndürelim.
            return Response(
                {
                    "jsonrpc": "2.0",
                    "id": request.data.get("id"),
                    "error": {
                        "code": -32400,
                        "message": {
                            "uz": "Provider not configured",
                            "ru": "Provider not configured",
                            "en": "Provider not configured",
                        },
                    },
                },
                status=503,
            )

        if not provider.verify_request(request):
            audit.signature_valid = False
            audit.result = "rejected"
            audit.save(update_fields=["signature_valid", "result"])
            return Response({
                "jsonrpc": "2.0",
                "id": request.data.get("id"),
                "error": {
                    "code": -32504,
                    "message": {
                        "uz": "Ruxsat yo'q",
                        "ru": "Недостаточно привилегий",
                        "en": "Insufficient privileges",
                    },
                },
            })

        audit.signature_valid = True
        try:
            body, status_code = provider.handle_webhook(request)
            audit.result = "success" if "result" in body else "rejected"
            audit.save(update_fields=["signature_valid", "result"])
            return Response(body, status=status_code)
        except Exception as exc:
            logger.exception("Payme webhook handler failed: %s", exc)
            audit.result = "error"
            audit.error_message = str(exc)
            audit.save(update_fields=["signature_valid", "result", "error_message"])
            return Response({
                "jsonrpc": "2.0",
                "id": request.data.get("id"),
                "error": {
                    "code": -32400,
                    "message": {"uz": "Xato", "ru": "Ошибка", "en": "Error"},
                },
            })
