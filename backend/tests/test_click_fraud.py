"""
Click fraud tespit testleri (FAZ 3).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone
from freezegun import freeze_time

from ads.models import AdPlacement, Campaign
from ads.tasks import _settle_placement
from analytics.fraud import (
    ClickContext,
    detect_ip_cluster_fraud,
    hash_ip,
    hash_user_agent,
    sign_tracking_token,
    validate_click,
)
from analytics.models import ClickEvent


pytestmark = pytest.mark.django_db(transaction=True)


# --- hash helpers ------------------------------------------------------------


def test_hash_ip_returns_full_and_subnet_hashes():
    full, subnet = hash_ip("203.0.113.42")
    assert len(full) == 64
    assert len(subnet) == 64
    assert full != subnet


def test_hash_ip_same_subnet_produces_same_subnet_hash():
    _, subnet_a = hash_ip("203.0.113.10")
    _, subnet_b = hash_ip("203.0.113.200")
    # Aynı /24 → aynı subnet hash
    assert subnet_a == subnet_b

    _, subnet_c = hash_ip("203.0.114.10")
    # Farklı /24 → farklı subnet hash
    assert subnet_a != subnet_c


def test_hash_ua_handles_empty():
    empty = hash_user_agent("")
    assert len(empty) == 64
    # Boş UA sabit bir hash'e gider (salt'a bağlı)
    assert hash_user_agent("") == empty


# --- validate_click real-time kurallar ---------------------------------------


def test_clean_click_is_valid(placement_factory):
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now() - timedelta(seconds=30),  # bot_speed eşiği üstü
    )
    ctx = ClickContext(
        ip="198.51.100.10",
        user_agent="Mozilla/5.0 (Macintosh) AppleWebKit/537",
    )
    click = validate_click(placement, ctx)

    assert click.is_suspicious is False
    assert click.suspicion_reasons == []

    placement.refresh_from_db()
    assert placement.clicks == 1
    assert placement.valid_clicks == 1


def test_rapid_same_ip_marked_suspicious(placement_factory):
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now() - timedelta(seconds=30),
    )
    ctx = ClickContext(ip="198.51.100.10", user_agent="Mozilla/5.0")

    first = validate_click(placement, ctx)
    second = validate_click(placement, ctx)

    assert first.is_suspicious is False
    assert second.is_suspicious is True
    assert "rate_limit" in second.suspicion_reasons

    placement.refresh_from_db()
    assert placement.clicks == 2
    # Yalnızca 1 valid (ilk temiz click)
    assert placement.valid_clicks == 1


def test_click_too_soon_after_send_marked_bot_speed(placement_factory):
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now() - timedelta(milliseconds=500),  # 0.5 sn
    )
    ctx = ClickContext(ip="198.51.100.11", user_agent="Mozilla/5.0")
    click = validate_click(placement, ctx)

    assert click.is_suspicious is True
    assert "bot_speed" in click.suspicion_reasons


def test_missing_user_agent_flagged(placement_factory):
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now() - timedelta(seconds=30),
    )
    ctx = ClickContext(ip="198.51.100.12", user_agent="")
    click = validate_click(placement, ctx)

    assert "suspicious_ua" in click.suspicion_reasons


def test_bot_user_agent_flagged(placement_factory):
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now() - timedelta(seconds=30),
    )
    ctx = ClickContext(ip="198.51.100.13", user_agent="Python-urllib/3.12")
    click = validate_click(placement, ctx)

    assert "suspicious_ua" in click.suspicion_reasons
    assert click.is_suspicious is True


# --- Cluster detection -------------------------------------------------------


def test_ip_cluster_detected_when_one_subnet_dominates(
    placement_factory, channel_factory
):
    channel = channel_factory()
    placement = placement_factory(channel=channel, status=AdPlacement.Status.SENT)

    # 30 click — 20 tanesi aynı /24'ten
    from analytics.models import ClickEvent as CE
    for i in range(20):
        CE.objects.create(
            placement=placement,
            ip_hash=f"unique-{i}".ljust(64, "x"),
            ip_subnet_hash="cluster-subnet".ljust(64, "x"),
            user_agent_hash="ua".ljust(64, "x"),
            is_suspicious=False,
        )
    for i in range(10):
        CE.objects.create(
            placement=placement,
            ip_hash=f"diverse-{i}".ljust(64, "x"),
            ip_subnet_hash=f"subnet-{i}".ljust(64, "x"),
            user_agent_hash="ua".ljust(64, "x"),
            is_suspicious=False,
        )

    result = detect_ip_cluster_fraud(channel)
    assert result["flagged"] is True
    assert result["total_clicks"] == 30
    assert result["top_subnet_clicks"] == 20


def test_ip_cluster_not_flagged_below_min_clicks(placement_factory, channel_factory):
    channel = channel_factory()
    placement = placement_factory(channel=channel)
    for i in range(5):
        ClickEvent.objects.create(
            placement=placement,
            ip_hash=f"h-{i}".ljust(64, "x"),
            ip_subnet_hash="same-subnet".ljust(64, "x"),
            user_agent_hash="ua".ljust(64, "x"),
        )
    result = detect_ip_cluster_fraud(channel)
    assert result["flagged"] is False  # < IP_CLUSTER_MIN_CLICKS


# --- Billing entegrasyonu ----------------------------------------------------


def test_cpc_billing_uses_valid_clicks_only(placement_factory, money):
    """CPC kampanyası: sadece valid_clicks faturalandırılmalı."""
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=101,
        clicks=10,
        valid_clicks=7,  # 3 şüpheli click var
        ad__campaign__billing_type=Campaign.BillingType.CPC,
        ad__campaign__bid_amount=money("500.00"),
    )

    _settle_placement(placement.id)

    placement.refresh_from_db()
    # 7 valid click × 500 UZS = 3500 UZS
    assert placement.cost == money("3500.00")


def test_cpc_billing_fallback_to_clicks_when_valid_clicks_zero(
    placement_factory, money
):
    """valid_clicks=0 ise (eski veri) raw clicks kullanılır — geriye uyum."""
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now(),
        telegram_message_id=102,
        clicks=5,
        valid_clicks=0,
        ad__campaign__billing_type=Campaign.BillingType.CPC,
        ad__campaign__bid_amount=money("500.00"),
    )

    _settle_placement(placement.id)

    placement.refresh_from_db()
    assert placement.cost == money("2500.00")


# --- Tracking redirect endpoint ---------------------------------------------


def test_redirect_endpoint_records_click_and_302s(placement_factory):
    placement = placement_factory(
        status=AdPlacement.Status.SENT,
        sent_at=timezone.now() - timedelta(seconds=30),
    )
    target = "https://example.test/landing"
    token = sign_tracking_token(placement.id, target)

    client = Client()
    response = client.get(
        f"/api/analytics/track/c/{placement.id}/{token}/",
        {"u": target},
        HTTP_USER_AGENT="Mozilla/5.0",
        REMOTE_ADDR="198.51.100.77",
    )

    assert response.status_code == 302
    assert response["Location"] == target
    assert ClickEvent.objects.filter(placement=placement).count() == 1


def test_redirect_endpoint_rejects_invalid_token(placement_factory):
    placement = placement_factory(status=AdPlacement.Status.SENT)
    client = Client()
    response = client.get(
        f"/api/analytics/track/c/{placement.id}/deadbeefdeadbeef/",
        {"u": "https://example.test/x"},
    )
    assert response.status_code == 403
    assert ClickEvent.objects.count() == 0


def test_redirect_endpoint_requires_target_url(placement_factory):
    placement = placement_factory(status=AdPlacement.Status.SENT)
    token = sign_tracking_token(placement.id, "")
    client = Client()
    response = client.get(f"/api/analytics/track/c/{placement.id}/{token}/")
    assert response.status_code == 400
