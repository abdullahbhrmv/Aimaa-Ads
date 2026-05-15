"""
Kanal kalite skoru testleri (FAZ 3).

`calculate_quality_score` fonksiyonunun bileşenlerinin doğru ağırlıklarda
toplandığını ve penaltilerin uygulandığını doğrular.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from ads.models import AdPlacement
from channels_app.quality import calculate_quality_score


pytestmark = pytest.mark.django_db(transaction=True)


def test_empty_channel_score_is_based_on_stability_only(channel_factory):
    """Hiç reklam görmemiş taze kanal: yalnızca stability ve engagement puanı alır."""
    channel = channel_factory(
        subscriber_count=1000,
        avg_views=100,  # %10 engagement
    )
    components = calculate_quality_score(channel)

    # Placement istatistikleri boş → completion_pts, ctr_pts = 0
    assert components.completion_pts == 0
    assert components.ctr_pts == 0
    assert components.sent_count == 0
    # %10 engagement / 30 sat = 1/3 × 30 ≈ 10 puan
    assert 8 <= components.engagement_pts <= 11
    # final score = engagement + stability (henüz penalty yok)
    assert 0 <= components.final_score <= 100


def test_high_engagement_raises_score(channel_factory):
    high_eng = channel_factory(subscriber_count=1000, avg_views=300)  # %30
    low_eng = channel_factory(subscriber_count=1000, avg_views=50)  # %5

    high_comp = calculate_quality_score(high_eng)
    low_comp = calculate_quality_score(low_eng)

    assert high_comp.engagement_pts > low_comp.engagement_pts
    # %30 saturation'a tam değerde → 30 puan
    assert high_comp.engagement_pts == 30


def test_failed_placements_drop_completion_rate(channel_factory, placement_factory):
    channel = channel_factory(subscriber_count=5000, avg_views=1000)
    # 5 sent, 5 failed
    now = timezone.now()
    for i in range(5):
        placement_factory(
            channel=channel,
            status=AdPlacement.Status.SENT,
            scheduled_at=now + timedelta(minutes=i),
        )
    for i in range(5):
        placement_factory(
            channel=channel,
            status=AdPlacement.Status.FAILED,
            scheduled_at=now + timedelta(minutes=100 + i),
        )

    components = calculate_quality_score(channel)
    # 5/10 = %50 → 12-13 puan
    assert components.ad_completion_rate == Decimal("50.00")
    assert 11 <= components.completion_pts <= 13


def test_high_ctr_raises_score(channel_factory, placement_factory):
    channel = channel_factory(subscriber_count=5000, avg_views=1000)
    placement_factory(
        channel=channel,
        status=AdPlacement.Status.DELETED,
        scheduled_at=timezone.now(),
        impressions=1000,
        valid_clicks=50,  # %5 CTR (saturation)
    )

    components = calculate_quality_score(channel)
    assert components.avg_ctr == Decimal("5.00")
    assert components.ctr_pts == 25  # tam saturation


def test_suspicious_growth_applies_penalty(channel_factory):
    flagged = channel_factory(
        subscriber_count=5000,
        avg_views=1000,
        suspicious_growth_flag=True,
    )
    clean = channel_factory(
        subscriber_count=5000,
        avg_views=1000,
        suspicious_growth_flag=False,
    )
    flagged_comp = calculate_quality_score(flagged)
    clean_comp = calculate_quality_score(clean)

    assert flagged_comp.growth_penalty == 30
    assert clean_comp.growth_penalty == 0
    assert flagged_comp.final_score < clean_comp.final_score


def test_ip_cluster_fraud_applies_penalty(channel_factory):
    flagged = channel_factory(
        subscriber_count=5000,
        avg_views=1000,
        ip_cluster_fraud_flag=True,
    )
    clean = channel_factory(
        subscriber_count=5000,
        avg_views=1000,
    )
    flagged_comp = calculate_quality_score(flagged)
    clean_comp = calculate_quality_score(clean)

    assert flagged_comp.cluster_penalty == 20
    assert clean_comp.final_score - flagged_comp.final_score == 20


def test_score_is_clamped_to_0_100(channel_factory):
    # Tüm penaltiler aktif ama engagement hiç yok
    channel = channel_factory(
        subscriber_count=10,
        avg_views=0,
        suspicious_growth_flag=True,
        ip_cluster_fraud_flag=True,
    )
    components = calculate_quality_score(channel)
    assert 0 <= components.final_score <= 100
    # raw negatif olabilir, final >= 0 kalmalı
    assert components.final_score >= 0


def test_components_dict_is_json_serializable(channel_factory):
    channel = channel_factory()
    components = calculate_quality_score(channel)

    # DailyChannelSnapshot.components alanına yazılabilmeli
    import json
    serialized = json.dumps(components.to_dict())
    assert "engagement_rate" in serialized


def test_recalculate_task_updates_channel_and_creates_snapshot(
    channel_factory, placement_factory
):
    """Nightly task: denormalize alanlar + DailyChannelSnapshot upsert."""
    from ads.tasks import recalculate_channel_quality_scores
    from channels_app.models import DailyChannelSnapshot

    channel = channel_factory(
        subscriber_count=5000, avg_views=1000, status="approved", is_active=True,
    )
    placement_factory(
        channel=channel,
        status=AdPlacement.Status.DELETED,
        impressions=2000,
        valid_clicks=100,
    )

    recalculate_channel_quality_scores()

    channel.refresh_from_db()
    assert channel.quality_updated_at is not None
    assert channel.avg_ctr == Decimal("5.00")

    snapshot = DailyChannelSnapshot.objects.get(
        channel=channel, date=timezone.now().date()
    )
    assert snapshot.quality_score == channel.quality_score
    assert "engagement_rate" in snapshot.components
