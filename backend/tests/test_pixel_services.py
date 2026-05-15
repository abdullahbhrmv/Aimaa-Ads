"""
pixel.services edge case testleri (FAZ 5 Adım 2).

Kapsam — kullanıcı review'unda istediği kritik kararlar:
- C1: Domain whitelist service katmanında
- C2: Wildcard `*.example.com` permissive (kök + subdomain + nested)
- C3: Dedup (event_id tekrarı) → idempotent, status "duplicate"
- C4: Clock skew > 24h → server_time kullanılır, raw_params'e flag
- Advanced matching: pre-hashed veya raw'dan normalize+hash
- Disabled pixel → PixelDisabledError
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from pixel.models import ConversionEvent
from pixel.services import (
    DomainNotAllowedError,
    EventValidationError,
    PixelDisabledError,
    hash_for_matching,
    matches_allowed_domain,
    record_event,
)


pytestmark = pytest.mark.django_db(transaction=True)


# --- C2: Wildcard domain matching -------------------------------------------


def test_exact_domain_match():
    assert matches_allowed_domain(
        "https://example.com", ["example.com"], debug_mode=False,
    )


def test_wildcard_matches_root_domain():
    """*.example.com → example.com (kök domain DAHİL)."""
    assert matches_allowed_domain(
        "https://example.com", ["*.example.com"], debug_mode=False,
    )


def test_wildcard_matches_single_subdomain():
    assert matches_allowed_domain(
        "https://shop.example.com", ["*.example.com"], debug_mode=False,
    )


def test_wildcard_matches_nested_subdomain():
    """*.example.com → a.b.example.com (çoklu seviye)."""
    assert matches_allowed_domain(
        "https://api.v2.example.com", ["*.example.com"], debug_mode=False,
    )


def test_wildcard_does_not_match_unrelated():
    assert not matches_allowed_domain(
        "https://evil.com", ["*.example.com"], debug_mode=False,
    )


def test_port_ignored_in_host_match():
    assert matches_allowed_domain(
        "https://shop.example.com:8443", ["*.example.com"], debug_mode=False,
    )


def test_debug_mode_accepts_localhost():
    assert matches_allowed_domain(
        "http://localhost:3000", [], debug_mode=True,
    )
    assert matches_allowed_domain(
        "http://127.0.0.1:8000", [], debug_mode=True,
    )


def test_debug_mode_off_rejects_localhost():
    assert not matches_allowed_domain(
        "http://localhost:3000", ["example.com"], debug_mode=False,
    )


# --- C1 & C3: record_event flow + dedup -------------------------------------


def _payload(**overrides) -> dict:
    base = {
        "event_name": "Purchase",
        "event_id": str(uuid.uuid4()),
        "url": "https://example.com/thanks",
        "value": "50000",
        "currency": "UZS",
    }
    base.update(overrides)
    return base


def test_domain_not_allowed_raises(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    with pytest.raises(DomainNotAllowedError):
        record_event(
            pixel, _payload(), origin="https://evil.com",
            client_ip="203.0.113.1", user_agent="Mozilla/5.0",
        )


def test_disabled_pixel_raises(pixel_factory):
    pixel = pixel_factory(enabled=False, allowed_domains=["example.com"])
    with pytest.raises(PixelDisabledError):
        record_event(
            pixel, _payload(), origin="https://example.com",
            client_ip="203.0.113.1", user_agent="Mozilla/5.0",
        )


def test_missing_event_id_raises(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    payload = _payload()
    payload.pop("event_id")
    with pytest.raises(EventValidationError):
        record_event(
            pixel, payload, origin="https://example.com",
            client_ip="203.0.113.1", user_agent="Mozilla/5.0",
        )


def test_successful_record_creates_event(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    event, status = record_event(
        pixel, _payload(), origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0",
    )
    assert status == "created"
    assert event.event_name == "Purchase"
    assert event.value == Decimal("50000")


def test_duplicate_event_id_returns_duplicate_status(pixel_factory):
    """C3: Aynı (pixel, event_id) ikinci record_event → 200 duplicate, yeni kayıt yok."""
    pixel = pixel_factory(allowed_domains=["example.com"])
    payload = _payload()

    e1, s1 = record_event(
        pixel, payload, origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0",
    )
    e2, s2 = record_event(
        pixel, payload, origin="https://example.com",
        client_ip="203.0.113.2", user_agent="Mozilla/5.0",
    )
    assert s1 == "created"
    assert s2 == "duplicate"
    assert e1.id == e2.id
    assert ConversionEvent.objects.filter(pixel=pixel).count() == 1


# --- C4: Clock skew ---------------------------------------------------------


def test_clock_skew_beyond_24h_flagged(pixel_factory):
    """client_ts > ±24h → server_time kullan, raw_params.clock_skew_detected=True."""
    pixel = pixel_factory(allowed_domains=["example.com"])
    # 48 saat önce
    bad_ts_ms = int((timezone.now() - timedelta(hours=48)).timestamp() * 1000)
    payload = _payload(client_ts=bad_ts_ms)

    event, status = record_event(
        pixel, payload, origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0",
    )
    assert status == "created"
    assert event.raw_params.get("clock_skew_detected") is True
    # created_at server tarafından set edildi — yaklaşık "şimdi"
    assert (timezone.now() - event.created_at).total_seconds() < 60


def test_clock_skew_within_tolerance_no_flag(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    # 1 saat önce — tolerans içinde
    ok_ts_ms = int((timezone.now() - timedelta(hours=1)).timestamp() * 1000)
    payload = _payload(client_ts=ok_ts_ms)

    event, _ = record_event(
        pixel, payload, origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0",
    )
    assert "clock_skew_detected" not in event.raw_params


def test_clock_skew_missing_client_ts_no_flag(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    event, _ = record_event(
        pixel, _payload(), origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0",
    )
    assert "clock_skew_detected" not in event.raw_params


# --- Advanced matching ------------------------------------------------------


def test_pre_hashed_em_accepted_as_is(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    pre_hashed = hash_for_matching("user@example.com", "email")
    payload = _payload(advanced_matching={"em_hash": pre_hashed})

    event, _ = record_event(
        pixel, payload, origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0",
    )
    assert event.em_hash == pre_hashed


def test_raw_em_hashed_by_backend(pixel_factory):
    """Server-side Conversions API raw email gönderirse backend hash'ler."""
    pixel = pixel_factory(allowed_domains=["example.com"])
    payload = _payload(advanced_matching={"em": "  User@Example.COM  "})

    event, _ = record_event(
        pixel, payload, origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0",
        event_source=ConversionEvent.Source.SERVER,
    )
    assert event.em_hash == hash_for_matching("user@example.com", "email")


def test_advanced_matching_disabled_clears_all_hash_fields(pixel_factory):
    pixel = pixel_factory(
        allowed_domains=["example.com"],
        advanced_matching_enabled=False,
    )
    payload = _payload(advanced_matching={
        "em_hash": hash_for_matching("user@example.com", "email"),
        "ph": "+998901234567",
    })

    event, _ = record_event(
        pixel, payload, origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0",
    )
    assert event.em_hash == ""
    assert event.ph_hash == ""


def test_invalid_hash_format_ignored(pixel_factory):
    """Pre-hashed alan 64-char hex değilse empty string'e düşer (silent drop)."""
    pixel = pixel_factory(allowed_domains=["example.com"])
    payload = _payload(advanced_matching={"em_hash": "not-a-valid-hash"})

    event, _ = record_event(
        pixel, payload, origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0",
    )
    assert event.em_hash == ""


# --- Debug mode + IP/UA hashing ---------------------------------------------


def test_ip_and_ua_hashed_not_stored_raw(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    event, _ = record_event(
        pixel, _payload(), origin="https://example.com",
        client_ip="203.0.113.1", user_agent="Mozilla/5.0 (Macintosh)",
    )
    # 64 char hex
    assert len(event.ip_hash) == 64
    assert len(event.ip_subnet_hash) == 64
    assert len(event.user_agent_hash) == 64
    # Raw IP/UA kesinlikle saklanmıyor
    assert "203.0.113.1" not in event.ip_hash
    assert "Mozilla" not in event.user_agent_hash
