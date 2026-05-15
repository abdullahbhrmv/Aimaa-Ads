"""
Manuel provider — admin tarafından elle girilen işlemler (FAZ 4a).

Webhook endpoint'i yok; `payments.services.deposit()` ve `adjust()` admin
panelinden çağrılır. Bu sınıf provider taksonomisi içinde tutarlılık için
tanımlıdır, webhook metodları no-op'tur.
"""

from __future__ import annotations

from .base import BasePaymentProvider


class ManualProvider(BasePaymentProvider):
    code = "manual"

    def is_configured(self) -> bool:
        return True  # manuel kanal her zaman açık

    def verify_request(self, request) -> bool:
        return False  # webhook yok

    def handle_webhook(self, request) -> tuple[dict, int]:
        return {"error": "manual provider has no webhook"}, 405
