"""
Pixel HTTP endpoint testleri (FAZ 5 Adım 3).

Kapsam:
- POST /api/pixel/event/ — valid + invalid origin + duplicate event_id
- CORS preflight (OPTIONS) dinamik origin echo
- Disabled pixel, eksik pixel_id → doğru status code
- Throttle fixture bazında sınırlama (production sabiti değişmeden)
- Install snippet endpoint — auth + HTML doğru pixel_id ile
- Pixel script endpoint — placeholder 501 (Adım 1'e kadar)
"""

from __future__ import annotations

import uuid

import pytest
from django.test import Client
from rest_framework.test import APIClient

from pixel.models import ConversionEvent, PixelInstallation


pytestmark = pytest.mark.django_db(transaction=True)


INGEST_URL = "/api/pixel/event/"
SCRIPT_URL = "/api/pixel/p.js"
SNIPPET_URL = "/api/pixel/install-snippet/"


def _payload(pixel_id: str, **overrides) -> dict:
    base = {
        "pixel_id": pixel_id,
        "event_name": "Purchase",
        "event_id": str(uuid.uuid4()),
        "url": "https://example.com/thanks",
        "value": "50000",
        "currency": "UZS",
    }
    base.update(overrides)
    return base


# --- Ingest happy path ------------------------------------------------------


def test_ingest_valid_event_returns_200_created(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    resp = Client().post(
        INGEST_URL,
        _payload(str(pixel.pixel_id)),
        content_type="application/json",
        HTTP_ORIGIN="https://example.com",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "created"
    assert "event_id" in body
    assert ConversionEvent.objects.filter(pixel=pixel).count() == 1


def test_ingest_duplicate_event_id_returns_duplicate(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    payload = _payload(str(pixel.pixel_id))

    r1 = Client().post(
        INGEST_URL, payload, content_type="application/json",
        HTTP_ORIGIN="https://example.com",
    )
    r2 = Client().post(
        INGEST_URL, payload, content_type="application/json",
        HTTP_ORIGIN="https://example.com",
    )
    assert r1.json()["status"] == "created"
    assert r2.json()["status"] == "duplicate"
    assert ConversionEvent.objects.filter(pixel=pixel).count() == 1


# --- Ingest validation ------------------------------------------------------


def test_ingest_missing_pixel_returns_404():
    resp = Client().post(
        INGEST_URL,
        {"event_name": "Purchase", "event_id": str(uuid.uuid4())},
        content_type="application/json",
        HTTP_ORIGIN="https://example.com",
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "pixel_not_found"


def test_ingest_unknown_pixel_id_returns_404():
    resp = Client().post(
        INGEST_URL,
        _payload(str(uuid.uuid4())),  # random uuid, no DB row
        content_type="application/json",
        HTTP_ORIGIN="https://example.com",
    )
    assert resp.status_code == 404


def test_ingest_disallowed_origin_returns_403(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    resp = Client().post(
        INGEST_URL,
        _payload(str(pixel.pixel_id)),
        content_type="application/json",
        HTTP_ORIGIN="https://evil.com",
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "domain_not_allowed"


def test_ingest_disabled_pixel_returns_403(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"], enabled=False)
    resp = Client().post(
        INGEST_URL,
        _payload(str(pixel.pixel_id)),
        content_type="application/json",
        HTTP_ORIGIN="https://example.com",
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "pixel_disabled"


def test_ingest_missing_event_id_returns_400(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    payload = _payload(str(pixel.pixel_id))
    payload.pop("event_id")
    resp = Client().post(
        INGEST_URL, payload, content_type="application/json",
        HTTP_ORIGIN="https://example.com",
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_payload"


def test_ingest_wildcard_subdomain_accepted(pixel_factory):
    pixel = pixel_factory(allowed_domains=["*.example.com"])
    resp = Client().post(
        INGEST_URL,
        _payload(str(pixel.pixel_id)),
        content_type="application/json",
        HTTP_ORIGIN="https://shop.example.com",
    )
    assert resp.status_code == 200


# --- CORS -------------------------------------------------------------------


def test_cors_preflight_echoes_allowed_origin(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    resp = Client().options(
        INGEST_URL + f"?pixel_id={pixel.pixel_id}",
        HTTP_ORIGIN="https://example.com",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert resp.status_code == 200
    assert resp["Access-Control-Allow-Origin"] == "https://example.com"
    assert "POST" in resp["Access-Control-Allow-Methods"]
    # Vary Django tarafından diğer değerlerle birleştirilebilir (Accept vs.);
    # yalnız "Origin"'in dahil olduğundan emin ol.
    assert "Origin" in resp["Vary"]


def test_cors_preflight_rejects_disallowed_origin(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    resp = Client().options(
        INGEST_URL + f"?pixel_id={pixel.pixel_id}",
        HTTP_ORIGIN="https://evil.com",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    # 200 döner ama Allow-Origin YOK — tarayıcı bloklar.
    assert resp.status_code == 200
    assert "Access-Control-Allow-Origin" not in resp


def test_post_response_has_cors_header_on_success(pixel_factory):
    pixel = pixel_factory(allowed_domains=["example.com"])
    resp = Client().post(
        INGEST_URL,
        _payload(str(pixel.pixel_id)),
        content_type="application/json",
        HTTP_ORIGIN="https://example.com",
    )
    assert resp.status_code == 200
    assert resp["Access-Control-Allow-Origin"] == "https://example.com"


# --- Install snippet --------------------------------------------------------


def test_install_snippet_requires_authentication():
    resp = APIClient().get(SNIPPET_URL)
    assert resp.status_code in (401, 403)


def test_install_snippet_returns_503_when_sdk_not_deployed(advertiser_factory, settings):
    """K1: Default settings.AIMAA_SDK_DEPLOYED=False → 503 advertiser-safe."""
    settings.AIMAA_SDK_DEPLOYED = False
    advertiser = advertiser_factory()
    client = APIClient()
    client.force_authenticate(user=advertiser)

    resp = client.get(SNIPPET_URL)
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "sdk_deployment_pending"


def test_install_snippet_returns_html_with_pixel_id(advertiser_factory, settings):
    settings.AIMAA_SDK_DEPLOYED = True
    advertiser = advertiser_factory()
    client = APIClient()
    client.force_authenticate(user=advertiser)

    resp = client.get(SNIPPET_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert "pixel_id" in body
    assert "snippet" in body
    # Pixel ID snippet içinde görünmeli
    assert body["pixel_id"] in body["snippet"]
    # Script URL doğru host'ta
    assert "/api/pixel/p.js" in body["snippet"]
    # Endpoint field ingest URL'ini göstermeli
    assert body["endpoint"].endswith("/api/pixel/event/")
    # I3: Snippet version tag — SDK ile downstream teşhis için.
    assert body["snippet_version"] == 1
    assert "data-aimaa-version" in body["snippet"]


def test_install_snippet_creates_pixel_if_missing(advertiser_factory, settings):
    """Advertiser ilk kez snippet çağırırsa Pixel kaydı otomatik yaratılır."""
    settings.AIMAA_SDK_DEPLOYED = True
    advertiser = advertiser_factory()
    assert not PixelInstallation.objects.filter(advertiser=advertiser).exists()

    client = APIClient()
    client.force_authenticate(user=advertiser)
    resp = client.get(SNIPPET_URL)

    assert resp.status_code == 200
    assert PixelInstallation.objects.filter(advertiser=advertiser).exists()


# --- Pixel script placeholder -----------------------------------------------


def test_pixel_script_returns_501_when_bundle_missing(monkeypatch, tmp_path):
    """Build edilmemiş (dist yok) → 501 + placeholder, no-store."""
    from pixel import views

    monkeypatch.setattr(views, "_PIXEL_DIST_PATH", tmp_path / "missing.js")
    resp = Client().get(SCRIPT_URL)
    assert resp.status_code == 501
    assert resp["Content-Type"].startswith("application/javascript")
    assert resp["Cache-Control"] == "no-store"
    assert b"not yet built" in resp.content.lower()


def test_pixel_script_serves_dist_when_present(monkeypatch, tmp_path):
    """Build edilmiş dist mevcutsa view dosyayı 200 + JS body olarak serve eder."""
    from pixel import views

    dist = tmp_path / "pixel.js"
    dist.write_bytes(b"/* fake bundle */\nwindow.aimaa=function(){};\n")
    monkeypatch.setattr(views, "_PIXEL_DIST_PATH", dist)

    resp = Client().get(SCRIPT_URL)
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/javascript")
    assert b"fake bundle" in resp.content
    assert "Cache-Control" in resp


# --- Throttle (isolation-friendly test) ------------------------------------


def test_ingest_throttle_returns_429_after_limit(pixel_factory, pixel_throttle_override):
    """Production oranı 300/min; test için `pixel_throttle_override`
    fixture'ı geçici olarak düşürür ve teardown'da restore eder."""
    pixel_throttle_override("2/min")
    pixel = pixel_factory(allowed_domains=["example.com"])

    def hit():
        return Client().post(
            INGEST_URL,
            _payload(str(pixel.pixel_id)),
            content_type="application/json",
            HTTP_ORIGIN="https://example.com",
            HTTP_X_FORWARDED_FOR="203.0.113.99",
            REMOTE_ADDR="203.0.113.99",
        )

    assert hit().status_code == 200
    assert hit().status_code == 200
    limited = hit()
    assert limited.status_code == 429
