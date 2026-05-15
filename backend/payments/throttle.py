"""
Webhook rate limiting (FAZ 4a).

Anonim IP bazlı throttle — her provider için ayrı scope tanımlı; bir
provider abuse edilirse diğerleri etkilenmesin.
"""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle


class WebhookThrottle(AnonRateThrottle):
    """Webhook endpoint'leri için IP-bazlı rate limit.

    Oran `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['webhook']` üzerinden
    gelir; default `60/min`. Provider-spesifik oranlar için bu sınıfı
    subclass'layıp `scope`'u override edin.
    """

    scope = "webhook"


class ClickWebhookThrottle(WebhookThrottle):
    scope = "webhook_click"


class PaymeWebhookThrottle(WebhookThrottle):
    scope = "webhook_payme"
