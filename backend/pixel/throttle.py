"""
Pixel endpoint rate limiting (FAZ 5 Adım 3).

Browser SDK PageView gibi yüksek frekanslı event'ler yolluyor; IP bazlı
rate cap abuse'a karşı koruma ama normal trafik için bol toleranslı.

Ayar: `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["pixel"] = "300/min"`.
Aşım → 429; SDK silent fail yapar, event kaybı kabul edilir.
"""

from rest_framework.throttling import AnonRateThrottle


class PixelEventThrottle(AnonRateThrottle):
    """Pixel event ingest — IP başına dakikada 300."""

    scope = "pixel"
