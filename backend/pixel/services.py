"""
AimaaPixel backend servisleri (FAZ 5 Adım 2).

Sorumluluklar:
- `normalize_for_hash` + `hash_for_matching` — pixel/src/hash.js ile BİREBİR
  aynı çıktı üretmek zorunda. Ground truth: pixel/fixtures/hash_fixtures.json.
  Parity bozukluğu cross-device attribution'ı sessizce yıkar.
- `matches_allowed_domain` — Origin header'ının pixel whitelist'ine uyup
  uymadığını kontrol eder. Wildcard davranışı Meta Pixel konvansiyonuna
  uygun (permissive): `*.example.com` → `example.com` + herhangi bir
  subdomain + subdomain'in subdomain'i.
- `record_event` — payload'ı doğrular, ConversionEvent yaratır veya
  duplicate tespit eder. Dedup unique constraint (pixel, event_id) üzerinden
  DB seviyesinde; 200 OK + "duplicate" status idempotent API sözleşmesi.
- Clock skew: client timestamp ±24h dışındaysa server_time kullanılır ve
  `raw_params.clock_skew_detected=True` işaretlenir. Event asla reddedilmez.

Kontrat (pixel/fixtures/hash_fixtures.json):
- email / name : strip + lower + NFC
- phone        : regex [^0-9] strip, NFC GEREKMEZ (çıktı ASCII-only)
- external_id  : strip + NFC (case KORUNUR)
- boş input    : boş hash (SHA-256(empty) DEĞİL — "değer yok" sinyali)
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from django.db import IntegrityError, transaction
from django.utils import timezone

from analytics.fraud import hash_ip, hash_user_agent
from pixel.models import ConversionEvent, PixelInstallation

logger = logging.getLogger(__name__)


# --- Hash normalization (pixel/src/hash.js paraleli) ------------------------
#
# Hot path — regex module-level compiled. re.sub("[^0-9]", ...) JS'in
# /[^0-9]/g davranışıyla uyumlu (ASCII-only; Unicode digit'leri SİLER).
# Python default \D pattern'i KULLANMA — Unicode digit'leri tutar.
_PHONE_STRIP_RE = re.compile(r"[^0-9]")

_VALID_KINDS = {"email", "phone", "name", "external_id"}


def normalize_for_hash(raw: Any, kind: str) -> str:
    """Hash öncesi tip-bazlı normalize.

    JS `pixel/src/hash.js::normalize` ile BİREBİR aynı çıktı üretir.
    Parity ground truth: `pixel/fixtures/hash_fixtures.json`.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    if raw is None or raw == "":
        return ""
    s = str(raw)
    if kind == "email" or kind == "name":
        s = s.strip().lower()
        s = unicodedata.normalize("NFC", s)
    elif kind == "phone":
        s = _PHONE_STRIP_RE.sub("", s)
        # NFC gerekmez — çıktı garantili ASCII-only.
    elif kind == "external_id":
        s = s.strip()
        s = unicodedata.normalize("NFC", s)
    return s


def hash_for_matching(raw: Any, kind: str) -> str:
    """Normalize + SHA-256 hex. Boş normalize → boş hash (sinyal)."""
    normalized = normalize_for_hash(raw, kind)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# --- Allowed domain matching ------------------------------------------------

_DEBUG_ORIGINS = {"localhost", "127.0.0.1", "::1"}


def _extract_host(origin_or_url: str) -> str:
    """Bir Origin header veya URL'den host'u çıkar (port olmadan).

    Kabul edilen formatlar:
      - "https://example.com"       → "example.com"
      - "https://shop.example.com:8443" → "shop.example.com"
      - "example.com"               → "example.com"  (bare)
    """
    if not origin_or_url:
        return ""
    s = origin_or_url.strip()
    if "://" in s:
        parsed = urlparse(s)
        host = parsed.hostname or ""
    else:
        host = s.split(":")[0]
    return host.lower()


def matches_allowed_domain(
    origin: str, allowed_domains: list[str], debug_mode: bool = False
) -> bool:
    """Origin header'ının pixel whitelist'ine uyup uymadığını kontrol et.

    Wildcard davranışı (Meta Pixel konvansiyonu, PERMISSIVE):
      "*.example.com" → matches:
        - example.com         (kök domain dahil)
        - foo.example.com     (1 seviye subdomain)
        - a.b.example.com     (çoklu seviye subdomain)

    `debug_mode=True` ise ayrıca localhost / 127.0.0.1 / [::1] kabul edilir.
    Pixel'in kendisinde `debug_mode=True` değilse bu bypass devre dışı.
    """
    host = _extract_host(origin)
    if not host:
        return False

    if debug_mode and host in _DEBUG_ORIGINS:
        return True

    for entry in allowed_domains or []:
        entry = entry.strip().lower()
        if not entry:
            continue
        if entry.startswith("*."):
            # Kök domain dahil — "*.example.com" matches "example.com"
            base = entry[2:]
            if host == base or host.endswith("." + base):
                return True
        else:
            if host == entry:
                return True
    return False


# --- record_event — ana giriş noktası ---------------------------------------


class EventValidationError(ValueError):
    """Payload validasyonu başarısız."""


class DomainNotAllowedError(EventValidationError):
    """Origin pixel.allowed_domains içinde değil."""


class PixelDisabledError(EventValidationError):
    """PixelInstallation.enabled=False."""


# Client timestamp ile server_time arası izin verilen fark.
# Bu değerin üzerindeki event'lerde server_time kullanılır ve flag konur.
CLOCK_SKEW_TOLERANCE_HOURS = 24

# Kabul edilen event_source değerleri — SDK "browser", Conversions API "server".
_VALID_SOURCES = {
    ConversionEvent.Source.BROWSER,
    ConversionEvent.Source.SERVER,
}


def _parse_client_timestamp(raw_ts: Any) -> datetime | None:
    """Payload'daki client timestamp'ı (epoch ms veya ISO string) UTC datetime'a çevir."""
    if raw_ts is None or raw_ts == "":
        return None
    if isinstance(raw_ts, (int, float)):
        try:
            return datetime.fromtimestamp(raw_ts / 1000, tz=dt_timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(raw_ts, str):
        try:
            # Python 3.11+ ISO 8601 destekli
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=dt_timezone.utc)
            return dt
        except ValueError:
            return None
    return None


def _detect_clock_skew(client_ts: datetime | None, server_now: datetime) -> bool:
    """Client timestamp server'dan ±24h'den fazla uzak mı."""
    if client_ts is None:
        return False
    delta = abs((client_ts - server_now).total_seconds())
    return delta > CLOCK_SKEW_TOLERANCE_HOURS * 3600


def record_event(
    pixel: PixelInstallation,
    payload: dict,
    origin: str | None,
    client_ip: str,
    user_agent: str,
    event_source: str = ConversionEvent.Source.BROWSER,
) -> tuple[ConversionEvent, str]:
    """Pixel payload'ını doğrula, ConversionEvent oluştur veya duplicate tespit et.

    Returns:
        (event, status) — status "created" veya "duplicate".

    Raises:
        PixelDisabledError: pixel.enabled=False
        DomainNotAllowedError: origin pixel.allowed_domains'te yok
        EventValidationError: payload eksik/bozuk (event_id veya event_name yok)
    """
    if not pixel.enabled:
        raise PixelDisabledError(f"Pixel {pixel.pixel_id} is disabled")

    # --- Domain whitelist (service katmanında, C1) ---
    if not matches_allowed_domain(origin or "", pixel.allowed_domains, pixel.debug_mode):
        raise DomainNotAllowedError(
            f"origin {origin!r} not in allowed_domains for pixel {pixel.pixel_id}"
        )

    # --- Payload zorunlu alanlar ---
    event_id = payload.get("event_id")
    event_name = payload.get("event_name")
    if not event_id:
        raise EventValidationError("event_id required")
    if not event_name:
        raise EventValidationError("event_name required")
    if event_source not in _VALID_SOURCES:
        raise EventValidationError(f"invalid event_source: {event_source!r}")

    # --- Clock skew (C4) — reject ETME, flag düş ---
    server_now = timezone.now()
    client_ts = _parse_client_timestamp(payload.get("client_ts"))
    clock_skew = _detect_clock_skew(client_ts, server_now)
    if clock_skew:
        logger.info(
            "Clock skew detected pixel=%s event_id=%s client_ts=%s server_now=%s",
            pixel.pixel_id, event_id, client_ts, server_now,
        )

    # --- IP + UA hash (FAZ 3 altyapısı) ---
    ip_hash_full, ip_subnet = hash_ip(client_ip or "")
    ua_hash = hash_user_agent(user_agent or "")

    # --- Advanced matching: backend PLAIN PII kabul etmez ---
    # Payload sadece pre-hashed değerler taşır (em_hash, ph_hash, ...).
    # Eğer advertiser raw PII gönderirse (ör. server-side Conversions API),
    # `hash_for_matching` burada hash'ler. İkisi de kabul, biri veya
    # diğeri — ambiguity varsa pre-hashed tercih edilir.
    adv = payload.get("advanced_matching") or {}
    if not pixel.advanced_matching_enabled:
        adv = {}

    def _resolve_hash(kind: str, hash_key: str, raw_key: str) -> str:
        if adv.get(hash_key):
            h = str(adv[hash_key]).strip().lower()
            # SHA-256 hex = 64 chars. Kaba format kontrolü.
            return h if len(h) == 64 and all(c in "0123456789abcdef" for c in h) else ""
        if adv.get(raw_key):
            return hash_for_matching(adv[raw_key], kind)
        return ""

    em_hash = _resolve_hash("email", "em_hash", "em")
    ph_hash = _resolve_hash("phone", "ph_hash", "ph")
    fn_hash = _resolve_hash("name", "fn_hash", "fn")
    ln_hash = _resolve_hash("name", "ln_hash", "ln")
    ext_id_hash = _resolve_hash("external_id", "external_id_hash", "external_id")

    # --- Click ID — cookie ya da query string'den SDK tarafı set etti ---
    click_id = payload.get("click_id")
    try:
        click_id_int = int(click_id) if click_id is not None else None
    except (TypeError, ValueError):
        click_id_int = None

    # --- Value / currency ---
    value_raw = payload.get("value")
    try:
        value_dec = Decimal(str(value_raw)) if value_raw is not None else None
    except (TypeError, ValueError, ArithmeticError):
        value_dec = None

    # --- raw_params: custom SDK params + debug meta ---
    raw_params = dict(payload.get("custom_params") or {})
    if clock_skew:
        raw_params["clock_skew_detected"] = True
        raw_params["client_ts"] = payload.get("client_ts")
    elif client_ts is not None:
        raw_params["client_ts"] = payload.get("client_ts")

    # --- Dedup via unique (pixel, event_id) — DB katmanında ---
    # IntegrityError'u yakalayıp mevcut event'i döndürürüz (idempotent API).
    defaults = dict(
        event_name=str(event_name)[:64],
        event_source=event_source,
        url=str(payload.get("url") or "")[:4000],
        referrer=str(payload.get("referrer") or "")[:4000],
        user_agent_hash=ua_hash,
        ip_hash=ip_hash_full,
        ip_subnet_hash=ip_subnet,
        click_id=click_id_int,
        utm_source=str(payload.get("utm_source") or "")[:100],
        utm_medium=str(payload.get("utm_medium") or "")[:100],
        utm_campaign=str(payload.get("utm_campaign") or "")[:100],
        utm_content=str(payload.get("utm_content") or "")[:100],
        utm_term=str(payload.get("utm_term") or "")[:100],
        value=value_dec,
        currency=str(payload.get("currency") or "")[:3],
        em_hash=em_hash,
        ph_hash=ph_hash,
        fn_hash=fn_hash,
        ln_hash=ln_hash,
        external_id_hash=ext_id_hash,
        raw_params=raw_params,
    )

    try:
        with transaction.atomic():
            event = ConversionEvent.objects.create(
                pixel=pixel,
                event_id=event_id,
                **defaults,
            )
        return event, "created"
    except IntegrityError:
        # (pixel, event_id) unique violation — duplicate.
        existing = ConversionEvent.objects.get(pixel=pixel, event_id=event_id)
        return existing, "duplicate"
