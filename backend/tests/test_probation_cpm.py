"""
Probation ve dynamic CPM multiplier testleri (FAZ 3).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone


pytestmark = pytest.mark.django_db(transaction=True)


def test_cpm_floor_respected_always(channel_factory, money):
    """min_cpm effective CPM'in altında kalamaz."""
    channel = channel_factory(
        subscriber_count=100,  # base=5000
        quality_score=10,  # multiplier düşük (0.7)
        min_cpm=money("6000.00"),  # floor base'den yüksek
    )
    assert channel.cpm_rate >= money("6000.00")


def test_probation_reduces_cpm(channel_factory, money):
    """Probation'daki kanalın CPM'i x0.7 ile çarpılır."""
    on_probation = channel_factory(
        subscriber_count=20000,  # base=10000
        quality_score=60,  # quality_mult=1.0
        min_cpm=money("1000.00"),  # düşük floor — multiplier görünsün
        probation_ends_at=timezone.now() + timedelta(days=10),
    )
    off_probation = channel_factory(
        subscriber_count=20000,
        quality_score=60,
        min_cpm=money("1000.00"),
        probation_ends_at=None,
    )

    assert on_probation.cpm_rate < off_probation.cpm_rate
    # Oran 0.7 olmalı
    ratio = Decimal(on_probation.cpm_rate) / Decimal(off_probation.cpm_rate)
    assert ratio.quantize(Decimal("0.01")) == Decimal("0.70")


def test_expired_probation_not_applied(channel_factory, money):
    channel = channel_factory(
        subscriber_count=20000,
        quality_score=60,
        min_cpm=money("1000.00"),
        probation_ends_at=timezone.now() - timedelta(days=1),  # süresi bitti
    )
    ref = channel_factory(
        subscriber_count=20000,
        quality_score=60,
        min_cpm=money("1000.00"),
    )
    assert channel.cpm_rate == ref.cpm_rate


def test_quality_score_multiplier_applied(channel_factory, money):
    low = channel_factory(
        subscriber_count=20000, quality_score=20, min_cpm=money("1.00"),
    )
    mid = channel_factory(
        subscriber_count=20000, quality_score=60, min_cpm=money("1.00"),
    )
    high = channel_factory(
        subscriber_count=20000, quality_score=80, min_cpm=money("1.00"),
    )
    top = channel_factory(
        subscriber_count=20000, quality_score=95, min_cpm=money("1.00"),
    )

    assert low.cpm_rate < mid.cpm_rate < high.cpm_rate < top.cpm_rate


def test_trusted_override_bypasses_probation_and_boosts_quality(
    channel_factory, money
):
    channel = channel_factory(
        subscriber_count=20000,
        quality_score=20,  # normalde 0.7 multiplier
        min_cpm=money("1.00"),
        probation_ends_at=timezone.now() + timedelta(days=10),
        is_trusted_override=True,
    )
    # Trusted → probation iptal, quality multiplier >= 1.0
    # base=10000 × 1.0 × 1.0 = 10000
    assert channel.cpm_rate == Decimal("10000")


def test_is_on_probation_property(channel_factory):
    active = channel_factory(
        probation_ends_at=timezone.now() + timedelta(days=5),
    )
    expired = channel_factory(
        probation_ends_at=timezone.now() - timedelta(days=1),
    )
    none_prob = channel_factory(probation_ends_at=None)
    trusted = channel_factory(
        probation_ends_at=timezone.now() + timedelta(days=5),
        is_trusted_override=True,
    )

    assert active.is_on_probation is True
    assert expired.is_on_probation is False
    assert none_prob.is_on_probation is False
    assert trusted.is_on_probation is False


def test_channel_approve_sets_probation(channel_factory):
    """Admin approve action'ı probation_ends_at'i ~30 gün ileri set etmeli."""
    from rest_framework.test import APIClient
    from core.models import User

    admin_user = User.objects.create_superuser(
        username="root-admin", email="admin@example.test", password="x"
    )
    channel = channel_factory(
        status="pending",
        is_active=False,
        probation_ends_at=None,
        is_trusted_override=False,
    )

    client = APIClient()
    client.force_authenticate(user=admin_user)
    response = client.post(f"/api/admin-panel/channels/{channel.id}/approve/")

    assert response.status_code == 200
    channel.refresh_from_db()
    assert channel.status == "approved"
    assert channel.probation_ends_at is not None
    # Yaklaşık 30 gün sonra
    expected = timezone.now() + timedelta(days=30)
    delta = abs((channel.probation_ends_at - expected).total_seconds())
    assert delta < 60


def test_trust_toggle_endpoint_trust_and_untrust(channel_factory):
    from rest_framework.test import APIClient
    from core.models import User

    admin_user = User.objects.create_superuser(
        username="root2", email="root2@example.test", password="x"
    )
    channel = channel_factory(
        probation_ends_at=timezone.now() + timedelta(days=10),
        suspicious_growth_flag=True,
        ip_cluster_fraud_flag=True,
        is_trusted_override=False,
    )

    client = APIClient()
    client.force_authenticate(user=admin_user)

    # Trust
    response = client.post(
        f"/api/admin-panel/channels/{channel.id}/trust/",
        {"action": "trust"},
        format="json",
    )
    assert response.status_code == 200
    channel.refresh_from_db()
    assert channel.is_trusted_override is True
    assert channel.probation_ends_at is None
    assert channel.suspicious_growth_flag is False
    assert channel.ip_cluster_fraud_flag is False

    # Untrust
    response = client.post(
        f"/api/admin-panel/channels/{channel.id}/trust/",
        {"action": "untrust"},
        format="json",
    )
    assert response.status_code == 200
    channel.refresh_from_db()
    assert channel.is_trusted_override is False


def test_trust_toggle_requires_valid_action(channel_factory):
    from rest_framework.test import APIClient
    from core.models import User

    admin_user = User.objects.create_superuser(
        username="root3", email="root3@example.test", password="x"
    )
    channel = channel_factory()
    client = APIClient()
    client.force_authenticate(user=admin_user)

    response = client.post(
        f"/api/admin-panel/channels/{channel.id}/trust/",
        {"action": "weird"},
        format="json",
    )
    assert response.status_code == 400
