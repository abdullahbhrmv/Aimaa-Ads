"""
Yayıncı kalite skorlama motoru (FAZ 3).

Bir kanalın son 30 günlük performansına göre 0-100 arası skor üretir.
Bileşenler:

    engagement_rate    → 0–30 puan
    ad_completion_rate → 0–25 puan
    avg_ctr            → 0–25 puan
    stability_bonus    → 0–20 puan (kanal yaşı + anomaly yok)
    suspicious_growth  → −30 penalty
    ip_cluster_fraud   → −20 penalty

Skor `max(0, min(100, raw))` ile sınırlandırılır. Yeni kanal (ölçüm yok)
varsayılan olarak 50 alır — `TelegramChannel.quality_score` default'u.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

LOOKBACK_DAYS = 30

# Bileşen ağırlıkları (maksimum katkı).
W_ENGAGEMENT = 30
W_COMPLETION = 25
W_CTR = 25
W_STABILITY = 20

# Penaltiler.
P_SUSPICIOUS_GROWTH = 30
P_IP_CLUSTER = 20

# Engagement rate kalibrasyon eşikleri.
# Telegram kanallarında "sağlıklı" engagement genelde %10-30 aralığıdır.
# %30+ → max puan; %0 → min puan.
ENGAGEMENT_SATURATION_PCT = Decimal("30")

# CTR kalibrasyonu — %5 çok iyi, %0.5 ortalama.
CTR_SATURATION_PCT = Decimal("5")

# Stability — kanalın yaşı (gün). 90 günden eski kanallar max bonus alır.
STABILITY_SATURATION_DAYS = 90


@dataclass
class QualityComponents:
    """Skorun alt bileşenleri — audit ve dashboard için."""

    engagement_rate: Decimal
    ad_completion_rate: Decimal
    avg_ctr: Decimal
    channel_age_days: int
    engagement_pts: int
    completion_pts: int
    ctr_pts: int
    stability_pts: int
    growth_penalty: int
    cluster_penalty: int
    raw_total: int
    final_score: int
    sent_count: int
    failed_count: int
    impressions: int
    valid_clicks: int

    def to_dict(self) -> dict:
        result = asdict(self)
        # Decimal → str (JSONField uyumluluğu)
        for key in ("engagement_rate", "ad_completion_rate", "avg_ctr"):
            result[key] = str(result[key])
        return result


def _pts(value: Decimal, saturation: Decimal, max_pts: int) -> int:
    """value/saturation oranını [0, max_pts] aralığına eşle."""
    if saturation <= 0:
        return 0
    ratio = max(Decimal(0), min(Decimal(1), value / saturation))
    return int((ratio * Decimal(max_pts)).to_integral_value())


def calculate_quality_score(channel) -> QualityComponents:
    """Kanalın güncel kalite skorunu hesapla — DB yazmaz, sadece hesaplar.

    `recalculate_channel_quality_scores` task'ı bu fonksiyonun sonucunu
    hem `TelegramChannel` denormalize alanlarına hem de
    `DailyChannelSnapshot` satırına yazar.
    """
    from ads.models import AdPlacement

    now = timezone.now()
    since = now - timedelta(days=LOOKBACK_DAYS)

    # --- Engagement (subscriber başına ortalama view yüzdesi) --------------
    subs = max(channel.subscriber_count or 0, 1)
    engagement_rate = (
        Decimal(channel.avg_views or 0) / Decimal(subs) * Decimal(100)
    )

    # --- Placement istatistikleri ------------------------------------------
    placement_stats = AdPlacement.objects.filter(
        channel=channel,
        created_at__gte=since,
    ).aggregate(
        sent=Count("id", filter=Q(status="sent") | Q(status="deleted")),
        failed=Count("id", filter=Q(status="failed")),
        impressions=Sum("impressions"),
        valid_clicks=Sum("valid_clicks"),
    )

    sent_count = placement_stats["sent"] or 0
    failed_count = placement_stats["failed"] or 0
    impressions = placement_stats["impressions"] or 0
    valid_clicks = placement_stats["valid_clicks"] or 0

    total_attempts = sent_count + failed_count
    completion_rate = (
        Decimal(sent_count) / Decimal(total_attempts) * Decimal(100)
        if total_attempts > 0 else Decimal(0)
    )

    ctr = (
        Decimal(valid_clicks) / Decimal(impressions) * Decimal(100)
        if impressions > 0 else Decimal(0)
    )

    # --- Stability bonus ----------------------------------------------------
    age_days = (now - channel.created_at).days if channel.created_at else 0

    # --- Puan hesabı --------------------------------------------------------
    engagement_pts = _pts(engagement_rate, ENGAGEMENT_SATURATION_PCT, W_ENGAGEMENT)
    completion_pts = _pts(completion_rate, Decimal(100), W_COMPLETION)
    ctr_pts = _pts(ctr, CTR_SATURATION_PCT, W_CTR)
    stability_pts = _pts(
        Decimal(age_days),
        Decimal(STABILITY_SATURATION_DAYS),
        W_STABILITY,
    )

    growth_penalty = P_SUSPICIOUS_GROWTH if channel.suspicious_growth_flag else 0
    cluster_penalty = P_IP_CLUSTER if channel.ip_cluster_fraud_flag else 0

    raw_total = (
        engagement_pts + completion_pts + ctr_pts + stability_pts
        - growth_penalty - cluster_penalty
    )
    final_score = max(0, min(100, raw_total))

    return QualityComponents(
        engagement_rate=engagement_rate.quantize(Decimal("0.01")),
        ad_completion_rate=completion_rate.quantize(Decimal("0.01")),
        avg_ctr=ctr.quantize(Decimal("0.01")),
        channel_age_days=age_days,
        engagement_pts=engagement_pts,
        completion_pts=completion_pts,
        ctr_pts=ctr_pts,
        stability_pts=stability_pts,
        growth_penalty=growth_penalty,
        cluster_penalty=cluster_penalty,
        raw_total=raw_total,
        final_score=final_score,
        sent_count=sent_count,
        failed_count=failed_count,
        impressions=impressions,
        valid_clicks=valid_clicks,
    )


# --- Anomaly detection -------------------------------------------------------
# Ani subscriber artışı tespit parametreleri.

# Oransal eşik — %50 günlük artış (küçük kanallarda bile belirgin).
GROWTH_RATIO_THRESHOLD = Decimal("50")
# Mutlak eşik — 500 yeni subscriber (küçük kanalların %50'si 1-2 kişi olabilir).
GROWTH_ABSOLUTE_MIN = 500
# Probation sıfırlama süresi — anomaly tespit edilirse kanal bu kadar gün
# yeniden probation'a alınır.
ANOMALY_PROBATION_DAYS = 14


def detect_growth_anomaly(
    previous_count: int, current_count: int
) -> tuple[bool, Decimal]:
    """(flag, growth_pct) döndür — anomaly eşikleri bu fonksiyonda merkezidir."""
    if previous_count <= 0:
        # Önceki değer yoksa karşılaştırma yapılamaz — anomaly değil.
        return False, Decimal(0)
    delta = current_count - previous_count
    if delta <= 0:
        return False, (
            Decimal(delta) / Decimal(previous_count) * Decimal(100)
            if previous_count else Decimal(0)
        ).quantize(Decimal("0.01"))
    pct = (Decimal(delta) / Decimal(previous_count) * Decimal(100)).quantize(
        Decimal("0.01")
    )
    suspicious = pct >= GROWTH_RATIO_THRESHOLD and delta >= GROWTH_ABSOLUTE_MIN
    return suspicious, pct
