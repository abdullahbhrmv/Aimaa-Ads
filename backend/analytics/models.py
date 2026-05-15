from django.db import models


class ClickEvent(models.Model):
    """Bir reklam placement'ına gelen tıklama kaydı (FAZ 3).

    Fraud detection için IP/UA hash'lenmiş halde saklanır (GDPR uyumluluğu).
    `is_suspicious=True` olan click'ler `AdPlacement.clicks` sayacını artırır
    ancak `valid_clicks`'a dahil edilmez — CPC billing yalnızca valid_clicks
    kullanır.

    `suspicion_reasons` tespit edilen kuralları (rate_limit, bot_speed,
    suspicious_ua, ip_cluster) içeren serbest formatlı bir liste.
    """

    placement = models.ForeignKey(
        "ads.AdPlacement",
        on_delete=models.CASCADE,
        related_name="click_events",
    )
    # `sha256(ip + settings.FRAUD_IP_SALT)` — 64 char hex.
    ip_hash = models.CharField(max_length=64, db_index=True)
    # IPv4 için /24, IPv6 için /48 prefix üzerinden hash — cluster analizinde kullanılır.
    ip_subnet_hash = models.CharField(max_length=64, db_index=True)
    user_agent_hash = models.CharField(max_length=64)

    is_suspicious = models.BooleanField(default=False, db_index=True)
    suspicion_reasons = models.JSONField(default=list, blank=True)

    telegram_user_id = models.BigIntegerField(null=True, blank=True)

    # Cross-device attribution için email hash (FAZ 5, FAZ 5.5'te aktif).
    # Şimdi sadece saklanır — attribution'da kullanımı FAZ 5.5'te etkinleşecek.
    # SDK ile backend arasında ortak normalizasyon: trim().lowercase() sonra SHA-256.
    # Index Meta.indexes'de partial (boş string'leri hariç tutar) — aşağıda.
    em_hash = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "click_events"
        indexes = [
            models.Index(fields=["placement", "is_suspicious"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["ip_subnet_hash", "created_at"]),
            # Partial — sadece em_hash set olan satırları indexle. Cross-device
            # attribution lookup'ta (FAZ 5.5) kullanılacak.
            models.Index(
                fields=["em_hash"],
                condition=~models.Q(em_hash=""),
                name="click_event_em_hash_partial",
            ),
        ]

    def __str__(self):
        return f"Click #{self.pk} → Placement {self.placement_id} (sus={self.is_suspicious})"


class AdEvent(models.Model):
    """Reklam etkileşim olayları — görüntülenme, tıklama vb."""

    class EventType(models.TextChoices):
        IMPRESSION = "impression", "Görüntülenme"
        CLICK = "click", "Tıklama"
        BUTTON_CLICK = "button_click", "Buton Tıklama"

    placement = models.ForeignKey(
        "ads.AdPlacement",
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ad_events"
        indexes = [
            models.Index(fields=["placement", "event_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} - Placement #{self.placement_id}"


class DailyStats(models.Model):
    """Günlük istatistik özeti — hızlı dashboard sorguları için."""

    date = models.DateField()
    campaign = models.ForeignKey(
        "ads.Campaign",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="daily_stats",
    )
    channel = models.ForeignKey(
        "channels_app.TelegramChannel",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="daily_stats",
    )
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "daily_stats"
        unique_together = ["date", "campaign", "channel"]
        indexes = [
            models.Index(fields=["date"]),
        ]


class DailyFunnelStats(models.Model):
    """Günlük impression → click → conversion funnel agregasyonu (FAZ 5).

    `DailyStats` ile farkı:
    - Conversion + conversion_value metrikleri eklenir (pixel'den gelir)
    - A/B test için `ad` seviyesinde breakdown sağlar (variant başına funnel)

    **Granülerlik tek seviyeli** — her satır `(date, campaign, ad, channel)`
    tuple'ında en granüler veriyi tutar. Kampanya veya ad seviyesinde
    rollup istenirse rapor endpoint'leri SUM/GROUP BY ile hesaplar.
    Bu kural double-count bug riskini ortadan kaldırır.

    Partitioning/TTL FAZ 5.5 konusu; bu sürüm açık sorgulama için yeterli.
    """

    date = models.DateField(db_index=True)
    campaign = models.ForeignKey(
        "ads.Campaign",
        on_delete=models.CASCADE,
        related_name="daily_funnel_stats",
    )
    # `ad` ve `channel` NOT NULL — tek granülerlik seviyesi için. Aggregation
    # task her zaman en granüler satırı yazar, üst-seviye toplamlar rapor
    # katmanında SUM ile hesaplanır.
    ad = models.ForeignKey(
        "ads.Ad",
        on_delete=models.CASCADE,
        related_name="daily_funnel_stats",
    )
    channel = models.ForeignKey(
        "channels_app.TelegramChannel",
        on_delete=models.CASCADE,
        related_name="daily_funnel_stats",
    )

    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    valid_clicks = models.IntegerField(default=0)
    conversion_count = models.IntegerField(default=0)
    conversion_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
    )
    spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "daily_funnel_stats"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "campaign", "ad", "channel"],
                name="unique_daily_funnel_tuple",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "-date"]),
            models.Index(fields=["ad", "-date"]),
        ]

    def __str__(self):
        return f"Funnel {self.campaign_id}/{self.ad_id}/{self.channel_id} @ {self.date}"
