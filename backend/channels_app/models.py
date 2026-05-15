from django.db import models
from django.conf import settings


class Category(models.Model):
    """Kanal kategorileri — hedefleme için kullanılır."""

    name_uz = models.CharField(max_length=100)
    name_ru = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=10, default="📁")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name_uz


class TelegramChannel(models.Model):
    """Reklam yayınlanan Telegram kanalları."""

    class Status(models.TextChoices):
        PENDING = "pending", "Onay Bekliyor"
        APPROVED = "approved", "Onaylandı"
        REJECTED = "rejected", "Reddedildi"
        SUSPENDED = "suspended", "Askıya Alındı"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="channels",
    )
    telegram_chat_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=255, blank=True, default="")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name="channels",
    )
    language = models.CharField(
        max_length=5,
        choices=[("uz", "O'zbekcha"), ("ru", "Русский"), ("mixed", "Aralash")],
        default="uz",
    )
    subscriber_count = models.IntegerField(default=0)
    avg_views = models.IntegerField(default=0, help_text="Ortalama post görüntülenmesi")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    is_active = models.BooleanField(default=True)
    bot_added = models.BooleanField(default=False, help_text="Bot kanala admin olarak eklendi mi?")

    # Reklam ayarları
    max_ads_per_day = models.IntegerField(default=3)
    min_cpm = models.DecimalField(
        max_digits=10, decimal_places=2, default=5000,
        help_text="Minimum CPM (UZS cinsinden)"
    )
    ad_hours_start = models.IntegerField(default=9, help_text="Reklam başlangıç saati")
    ad_hours_end = models.IntegerField(default=22, help_text="Reklam bitiş saati")

    # Kazanç
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pending_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # --- Kalite skorlama (FAZ 3) ------------------------------------------
    # Denormalize alanlar `channels_app.quality.calculate_quality_score`
    # tarafından nightly task'ta doldurulur. `quality_score` hızlı sorgular
    # için, detay bileşenler dashboard için saklanır.
    quality_score = models.PositiveSmallIntegerField(
        default=50,
        help_text="0-100 arası ağırlıklı kalite skoru (default=50 yeni kanal)",
    )
    engagement_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text="avg_views / subscriber_count × 100",
    )
    ad_completion_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="sent / (sent+failed) × 100",
    )
    avg_ctr = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="CPC reklamlarda valid_clicks / impressions × 100",
    )
    suspicious_growth_flag = models.BooleanField(default=False, db_index=True)
    ip_cluster_fraud_flag = models.BooleanField(default=False, db_index=True)
    quality_updated_at = models.DateTimeField(null=True, blank=True)

    # --- Probation + trust override (FAZ 3) -------------------------------
    # `probation_ends_at` NULL ise kanal probation dışıdır (geriye dönük
    # uyumluluk için mevcut kanallar bu şekilde kalır). Yeni onaylarda
    # `approved_at + 30 gün` olarak set edilir.
    probation_ends_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Probation süresi bitişi; NULL → probation dışı",
    )
    is_trusted_override = models.BooleanField(
        default=False,
        help_text="Admin tarafından elle güvenilir işaretlendi — probation + fraud bypass",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telegram_channels"
        ordering = ["-subscriber_count"]

    def __str__(self):
        return f"{self.title} (@{self.username})"

    # --- CPM hesaplama -----------------------------------------------------

    @property
    def cpm_rate(self):
        """Kanal için geçerli CPM oranı.

        Mevcut aktif kampanyaları ETKİLEMEZ — billing `campaign.bid_amount`
        kullanır. Bu değer yalnızca `find_matching_channels` eşleştirmesi
        ve yayıncı panelinde gösterim amacıyla kullanılır.

        Hesaplama:
            base = subscriber tier tabanlı CPM (mevcut mantık)
            adjusted = base × quality_multiplier × probation_multiplier
            cpm_rate = max(min_cpm, adjusted)

        `is_trusted_override=True` ise probation penalty'si uygulanmaz ve
        quality multiplier minimum 1.0'a yükseltilir.
        """
        from decimal import Decimal
        base = self._calculate_base_cpm()
        q_mult = self._quality_multiplier()
        p_mult = self._probation_multiplier()
        if self.is_trusted_override:
            q_mult = max(q_mult, 1.0)
            p_mult = 1.0
        adjusted = Decimal(base) * Decimal(str(q_mult)) * Decimal(str(p_mult))
        return max(self.min_cpm, adjusted)

    def _calculate_base_cpm(self):
        """Abone sayısı tier'larına göre taban CPM (UZS)."""
        if self.subscriber_count > 50000:
            return 15000
        if self.subscriber_count > 10000:
            return 10000
        if self.subscriber_count > 1000:
            return 7000
        return 5000

    # Geriye dönük uyumluluk — mevcut kod bu metoda referans verebilir.
    # Yeni kod `_calculate_base_cpm` kullanmalıdır.
    _calculate_dynamic_cpm = _calculate_base_cpm

    def _quality_multiplier(self) -> float:
        """Kalite skoruna göre CPM çarpanı (0.5 – 1.5)."""
        score = self.quality_score or 50
        if score < 30:
            return 0.7
        if score < 50:
            return 0.85
        if score < 75:
            return 1.0
        if score < 90:
            return 1.2
        return 1.5

    def _probation_multiplier(self) -> float:
        """Probation süresi içinde ise 0.7, değilse 1.0."""
        from django.utils import timezone
        if self.probation_ends_at and self.probation_ends_at > timezone.now():
            return 0.7
        return 1.0

    @property
    def is_on_probation(self) -> bool:
        """Probation süresi hâlâ aktif mi (trust override hariç)."""
        from django.utils import timezone
        if self.is_trusted_override:
            return False
        return bool(
            self.probation_ends_at and self.probation_ends_at > timezone.now()
        )


class DailyChannelSnapshot(models.Model):
    """Kanal bazlı günlük snapshot — anomaly detection ve kalite trendi için.

    Her kanal için günde bir satır (`channel × date` benzersiz).
    `recalculate_channel_quality_scores` ve `detect_subscriber_anomalies`
    task'ları tarafından doldurulur. Geçmiş kayıtlar silinmez — audit
    amaçlıdır; uzun vadede partitioning veya TTL politikası eklenebilir.
    """

    channel = models.ForeignKey(
        TelegramChannel,
        on_delete=models.CASCADE,
        related_name="daily_snapshots",
    )
    date = models.DateField(db_index=True)

    subscriber_count = models.IntegerField()
    avg_views = models.IntegerField(default=0)

    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    valid_clicks = models.IntegerField(default=0)

    quality_score = models.PositiveSmallIntegerField(default=50)
    components = models.JSONField(
        default=dict,
        blank=True,
        help_text="Skorun alt bileşenleri — debug/audit için",
    )

    suspicious_growth_flag = models.BooleanField(default=False)
    growth_pct = models.DecimalField(
        max_digits=7, decimal_places=2, default=0,
        help_text="Önceki güne göre subscriber artış yüzdesi",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "daily_channel_snapshots"
        unique_together = [("channel", "date")]
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["channel", "-date"]),
            models.Index(fields=["suspicious_growth_flag", "-date"]),
        ]

    def __str__(self):
        return f"Snapshot {self.channel_id} @ {self.date}"
