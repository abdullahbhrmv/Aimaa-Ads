"""
Click fraud tespit motoru (FAZ 3).

Tasarım:
- `validate_click` real-time — redirect endpoint'i tarafından tıklama
  anında çağrılır. Üç kural gerçek zamanda çalışır (rate_limit, bot_speed,
  suspicious_ua). Sonuç bir `ClickEvent` satırı döner.
- `detect_ip_cluster_fraud` nightly — pahalı kümeleme analizi, tüm
  onaylı kanalların son 24 saatlik click'lerini /24 subnet hash'i bazında
  grupluyor. Eşiği aşan kanallar `ip_cluster_fraud_flag=True` işaretlenir.

Mahremiyet:
- IP asla raw olarak saklanmaz. `SHA-256(ip || FRAUD_IP_SALT)` →
  `ip_hash`; `SHA-256("subnet-v4:<prefix>" || SALT)` → `ip_subnet_hash`.
- `FRAUD_IP_SALT` ayarı yoksa `SECRET_KEY`'in ilk 32 karakteri fallback.
- Salt rotasyonu 24h cluster analizini geçici olarak kırar (kabul edilebilir).
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F
from django.utils import timezone

from analytics.models import ClickEvent


# --- Tracking URL imzalama (FAZ 3) ------------------------------------------
# Button URL'i direkt advertiser URL'ine gitmek yerine bir redirect
# endpoint'inden geçer. Token HMAC-SHA256(SECRET, "placement_id:button_url")
# ile üretilir; endpoint'te doğrulanır — token bilinmeden URL enjekte
# edilemez.

_TOKEN_LENGTH = 16  # hex karakter sayısı (64-bit imza — placement_id ile yeterli)


def _tracking_secret() -> bytes:
    secret = getattr(settings, "CLICK_TRACKING_SECRET", "") or settings.SECRET_KEY
    return secret.encode("utf-8")


def sign_tracking_token(placement_id: int, target_url: str) -> str:
    """HMAC tabanlı token üret — URL ve placement_id'ye bağlı."""
    import hmac
    payload = f"{placement_id}:{target_url}".encode("utf-8")
    mac = hmac.new(_tracking_secret(), payload, hashlib.sha256)
    return mac.hexdigest()[:_TOKEN_LENGTH]


def verify_tracking_token(
    placement_id: int, target_url: str, token: str
) -> bool:
    """Token'ı sabit zamanlı karşılaştır."""
    import hmac
    expected = sign_tracking_token(placement_id, target_url)
    return hmac.compare_digest(expected, token)

logger = logging.getLogger(__name__)

# Real-time kurallar — threshold'lar ayarlanabilir olsun diye settings fallback.
RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_MAX_CLICKS = 1  # aynı IP+placement → 10sn'de >1 click şüpheli
BOT_SPEED_SECONDS = 2  # placement sent_at + 2sn → bot tahmini

# Cluster analizi — kanalın son 24h click'lerinin bir /24 subnet'ten gelen oranı
# bu yüzdeyi aşarsa kanal flag'lanır.
IP_CLUSTER_THRESHOLD_PCT = 50
IP_CLUSTER_MIN_CLICKS = 20  # küçük örneklerde cluster'a inanmıyoruz

# UA pattern — bot/crawler/headless.
_SUSPICIOUS_UA_RE = re.compile(
    r"bot|crawler|spider|curl|python|wget|headless|scrapy|puppeteer",
    re.IGNORECASE,
)


@dataclass
class ClickContext:
    """Request'ten çıkarılan tıklama bağlamı."""

    ip: str
    user_agent: str
    telegram_user_id: int | None = None


def _get_salt() -> bytes:
    salt = getattr(settings, "FRAUD_IP_SALT", "") or settings.SECRET_KEY[:32]
    return salt.encode("utf-8")


def hash_ip(ip: str) -> tuple[str, str]:
    """IP'yi (full_hash, subnet_hash) olarak hash'le.

    IPv4 → /24 prefix, IPv6 → /48 prefix subnet hash'i.
    Geçersiz IP'lerde tam IP string'i hash'lenir; subnet aynı olur.
    """
    salt = _get_salt()
    full = hashlib.sha256(salt + ip.encode("utf-8")).hexdigest()

    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv4Address):
            network = ipaddress.ip_network(f"{ip}/24", strict=False)
            subnet_key = f"v4:{network.network_address}"
        else:
            network = ipaddress.ip_network(f"{ip}/48", strict=False)
            subnet_key = f"v6:{network.network_address}"
    except ValueError:
        subnet_key = f"raw:{ip}"

    subnet = hashlib.sha256(salt + subnet_key.encode("utf-8")).hexdigest()
    return full, subnet


def hash_user_agent(ua: str) -> str:
    """User-agent string'ini hash'le (boş UA için sabit sentinel)."""
    ua = (ua or "").strip()
    return hashlib.sha256(_get_salt() + ua.encode("utf-8")).hexdigest()


def _check_rate_limit(placement_id: int, ip_hash: str) -> bool:
    """Aynı IP + placement → son RATE_LIMIT_WINDOW_SECONDS içinde limit aşıldı mı?"""
    window_start = timezone.now() - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    recent = ClickEvent.objects.filter(
        placement_id=placement_id,
        ip_hash=ip_hash,
        created_at__gte=window_start,
    ).count()
    return recent >= RATE_LIMIT_MAX_CLICKS


def _check_bot_speed(placement) -> bool:
    """Placement gönderilmesinden < BOT_SPEED_SECONDS sonraki click şüpheli."""
    if not placement.sent_at:
        # Placement henüz sent_at set edilmediyse (ör. başarısız gönderim)
        # tıklama anormal — şüpheli.
        return True
    delta = timezone.now() - placement.sent_at
    return delta.total_seconds() < BOT_SPEED_SECONDS


def _check_suspicious_ua(user_agent: str) -> bool:
    if not user_agent:
        return True
    return bool(_SUSPICIOUS_UA_RE.search(user_agent))


def validate_click(placement, context: ClickContext) -> ClickEvent:
    """Bir tıklamayı fraud kurallarına karşı doğrula ve `ClickEvent` oluştur.

    - Kurallar sırayla çalıştırılır; herhangi biri pozitif olursa
      `suspicion_reasons` listesine eklenir.
    - `is_suspicious = bool(reasons)`.
    - `AdPlacement.clicks` ve (şüpheli değilse) `valid_clicks` atomik olarak
      artırılır — eşzamanlı click'lerde F() expression güvenlidir.
    """
    from ads.models import AdPlacement

    ip_hash_full, ip_subnet = hash_ip(context.ip)
    ua_hash = hash_user_agent(context.user_agent)

    reasons: list[str] = []

    if _check_rate_limit(placement.id, ip_hash_full):
        reasons.append("rate_limit")
    if _check_bot_speed(placement):
        reasons.append("bot_speed")
    if _check_suspicious_ua(context.user_agent):
        reasons.append("suspicious_ua")

    is_suspicious = bool(reasons)

    with transaction.atomic():
        click = ClickEvent.objects.create(
            placement=placement,
            ip_hash=ip_hash_full,
            ip_subnet_hash=ip_subnet,
            user_agent_hash=ua_hash,
            is_suspicious=is_suspicious,
            suspicion_reasons=reasons,
            telegram_user_id=context.telegram_user_id,
        )

        # Sayaçları F() ile atomik artır.
        update = {"clicks": F("clicks") + 1}
        if not is_suspicious:
            update["valid_clicks"] = F("valid_clicks") + 1
        AdPlacement.objects.filter(id=placement.id).update(**update)

    if is_suspicious:
        logger.info(
            "Suspicious click blocked: placement=%s reasons=%s",
            placement.id,
            reasons,
        )

    return click


def detect_ip_cluster_fraud(channel) -> dict:
    """Bir kanal için son 24h click'lerinin /24 subnet yoğunluğunu analiz et.

    Döndürülen dict:
        {
            "flagged": bool,
            "total_clicks": int,
            "top_subnet_clicks": int,
            "top_subnet_pct": Decimal,
        }

    Nightly task `detect_ip_cluster_fraud_task` bu yardımcıyı çağırır ve
    sonuca göre `channel.ip_cluster_fraud_flag`'ı günceller.
    """
    from decimal import Decimal

    since = timezone.now() - timedelta(hours=24)
    clicks_qs = ClickEvent.objects.filter(
        placement__channel=channel,
        created_at__gte=since,
    )

    total = clicks_qs.count()
    if total < IP_CLUSTER_MIN_CLICKS:
        return {
            "flagged": False,
            "total_clicks": total,
            "top_subnet_clicks": 0,
            "top_subnet_pct": Decimal(0),
        }

    top = (
        clicks_qs.values("ip_subnet_hash")
        .annotate(c=Count("id"))
        .order_by("-c")
        .first()
    )
    top_count = top["c"] if top else 0
    pct = (
        Decimal(top_count) / Decimal(total) * Decimal(100)
    ).quantize(Decimal("0.01"))

    flagged = pct >= IP_CLUSTER_THRESHOLD_PCT

    return {
        "flagged": flagged,
        "total_clicks": total,
        "top_subnet_clicks": top_count,
        "top_subnet_pct": pct,
    }
