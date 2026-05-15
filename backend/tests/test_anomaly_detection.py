"""
Subscriber anomaly detection testleri (FAZ 3).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from ads.tasks import detect_subscriber_anomalies
from channels_app.models import DailyChannelSnapshot
from channels_app.quality import (
    ANOMALY_PROBATION_DAYS,
    GROWTH_ABSOLUTE_MIN,
    GROWTH_RATIO_THRESHOLD,
    detect_growth_anomaly,
)


pytestmark = pytest.mark.django_db(transaction=True)


# --- detect_growth_anomaly birimsel ------------------------------------------


def test_clean_growth_not_flagged():
    anomaly, pct = detect_growth_anomaly(10000, 10100)  # %1 artış
    assert anomaly is False
    assert pct == Decimal("1.00")


def test_huge_ratio_but_small_absolute_not_flagged():
    """Küçük kanal: %50 artış ama sadece 5 kişi → flag yok."""
    anomaly, pct = detect_growth_anomaly(10, 15)
    assert anomaly is False  # absolute threshold aşılmadı
    assert pct == Decimal("50.00")


def test_sudden_spike_flagged():
    # 10k → 20k: %100 artış, mutlak 10k kişi
    anomaly, pct = detect_growth_anomaly(10000, 20000)
    assert anomaly is True
    assert pct == Decimal("100.00")


def test_threshold_boundaries():
    # Tam eşikte: %GROWTH_RATIO_THRESHOLD + >GROWTH_ABSOLUTE_MIN
    base = 2000
    delta = GROWTH_ABSOLUTE_MIN  # tam absolute eşiğinde
    # pct = delta/base*100 = 500/2000*100 = %25 → threshold altı
    anomaly, _ = detect_growth_anomaly(base, base + delta)
    assert anomaly is False

    # Büyük kanalı düzgün %50 büyüt:
    big_base = GROWTH_ABSOLUTE_MIN * 2
    big_delta = GROWTH_ABSOLUTE_MIN  # tam absolute eşik + %50 büyüme
    anomaly_big, pct_big = detect_growth_anomaly(big_base, big_base + big_delta)
    assert pct_big == GROWTH_RATIO_THRESHOLD.quantize(Decimal("0.01"))
    assert anomaly_big is True


def test_zero_or_negative_baseline_is_not_flagged():
    # 0 subscriber'dan artış → anomaly hesaplanamaz
    anomaly, _ = detect_growth_anomaly(0, 1000)
    assert anomaly is False


def test_shrinking_channel_not_flagged():
    anomaly, pct = detect_growth_anomaly(10000, 9000)
    assert anomaly is False
    assert pct < 0


# --- detect_subscriber_anomalies task ----------------------------------------


def test_anomaly_task_flags_channel_and_puts_on_probation(channel_factory):
    channel = channel_factory(
        subscriber_count=25000,
        status="approved",
        is_active=True,
        probation_ends_at=None,
        suspicious_growth_flag=False,
    )
    yesterday = timezone.now().date() - timedelta(days=1)

    # Dün 10k, bugün 25k → +%150 artış
    DailyChannelSnapshot.objects.create(
        channel=channel,
        date=yesterday,
        subscriber_count=10000,
        avg_views=2000,
        quality_score=50,
    )

    detect_subscriber_anomalies()

    channel.refresh_from_db()
    assert channel.suspicious_growth_flag is True
    assert channel.probation_ends_at is not None
    # Probation yaklaşık 14 gün sonra bitmeli
    expected_end = timezone.now() + timedelta(days=ANOMALY_PROBATION_DAYS)
    delta = abs((channel.probation_ends_at - expected_end).total_seconds())
    assert delta < 60  # 1 dakika tolerans

    today_snap = DailyChannelSnapshot.objects.get(
        channel=channel, date=timezone.now().date()
    )
    assert today_snap.suspicious_growth_flag is True


def test_anomaly_task_organic_growth_not_flagged(channel_factory):
    channel = channel_factory(
        subscriber_count=10200,
        status="approved",
        is_active=True,
    )
    yesterday = timezone.now().date() - timedelta(days=1)
    DailyChannelSnapshot.objects.create(
        channel=channel,
        date=yesterday,
        subscriber_count=10000,
        quality_score=50,
    )

    detect_subscriber_anomalies()

    channel.refresh_from_db()
    assert channel.suspicious_growth_flag is False


def test_trusted_override_bypasses_anomaly_flagging(channel_factory):
    channel = channel_factory(
        subscriber_count=50000,
        status="approved",
        is_active=True,
        is_trusted_override=True,
    )
    yesterday = timezone.now().date() - timedelta(days=1)
    DailyChannelSnapshot.objects.create(
        channel=channel, date=yesterday,
        subscriber_count=10000,
        quality_score=50,
    )

    detect_subscriber_anomalies()

    channel.refresh_from_db()
    assert channel.suspicious_growth_flag is False
    assert channel.probation_ends_at is None


def test_anomaly_task_idempotent_creates_single_snapshot_per_day(channel_factory):
    channel = channel_factory(
        subscriber_count=10000,
        status="approved",
        is_active=True,
    )
    yesterday = timezone.now().date() - timedelta(days=1)
    DailyChannelSnapshot.objects.create(
        channel=channel, date=yesterday,
        subscriber_count=9500,
        quality_score=50,
    )

    detect_subscriber_anomalies()
    detect_subscriber_anomalies()

    today_count = DailyChannelSnapshot.objects.filter(
        channel=channel, date=timezone.now().date()
    ).count()
    assert today_count == 1


def test_first_day_no_yesterday_no_flag(channel_factory):
    """İlk gün — dünkü snapshot yok → anomaly hesaplanamaz, sessizce atla."""
    channel = channel_factory(
        subscriber_count=10000,
        status="approved",
        is_active=True,
    )

    detect_subscriber_anomalies()

    channel.refresh_from_db()
    assert channel.suspicious_growth_flag is False
    # Bugünün snapshot'ı oluşmalı
    assert DailyChannelSnapshot.objects.filter(
        channel=channel, date=timezone.now().date()
    ).exists()
