"""
Ödeme provider'ları için ortak arayüz (FAZ 4a).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderNotConfiguredError(Exception):
    """Provider için gerekli env var'lar eksik — webhook 503 döner."""


class BasePaymentProvider(ABC):
    """Click / Payme / Manuel provider'lar bu arayüzü implement eder."""

    code: str  # "click", "payme", "manual"

    @abstractmethod
    def is_configured(self) -> bool:
        """Provider işletime hazır mı (secret'lar env'de var mı)."""

    @abstractmethod
    def verify_request(self, request) -> bool:
        """Gelen webhook'un imza/basic-auth doğrulaması."""

    @abstractmethod
    def handle_webhook(self, request) -> tuple[dict, int]:
        """Webhook payload'ını işle; (response_body, http_status) döndür."""


def parse_merchant_trans_id(merchant_trans_id: str) -> int | None:
    """Convention: `deposit-<user_id>-<nonce>` → user_id.

    Provider'lara verdiğimiz merchant_trans_id formatı yukarıdaki gibidir.
    Tersine mühendislik edilmemesi için hash ile güçlendirmek FAZ 4b'de
    yapılabilir; şu an basit, açık bir format.
    """
    if not merchant_trans_id:
        return None
    parts = merchant_trans_id.split("-")
    if len(parts) < 2 or parts[0] != "deposit":
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def build_merchant_trans_id(user_id: int, nonce: str) -> str:
    """Çıkış konvansiyonu — deposit URL üretilirken kullanılır (FAZ 4b)."""
    return f"deposit-{user_id}-{nonce}"


def flatten_request_data(request) -> dict:
    """DRF `request.data`'yı tek-değerli flat dict'e çevir.

    Form-encoded webhook'lar (Click.uz application/x-www-form-urlencoded)
    DRF'te `QueryDict` olarak parse edilir. `dict(query_dict)` her anahtar
    için liste döner (multi-value desteği); imza doğrulama ve payload
    işleme tek değer bekliyor. Bu helper onu flatten eder. JSON payload'lar
    zaten düz dict olduğu için no-op.
    """
    data = request.data
    if hasattr(data, "dict"):
        return data.dict()
    return dict(data)
