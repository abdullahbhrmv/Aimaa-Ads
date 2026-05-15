from django.db import models
from django.conf import settings


class Campaign(models.Model):
    """Reklamveren kampanyası.

    `status` business state'tir (advertiser'ın gördüğü yaşam döngüsü);
    `moderation_status` ise otomatik tarama pipeline'ının durumudur.
    İki boyut ortogonaldir — `moderation_status='auto_approved'` olsa
    bile admin `status='active'`'e geçene kadar yayın başlamaz.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Taslak"
        PENDING = "pending", "Onay Bekliyor"
        APPROVED = "approved", "Onaylandı"
        ACTIVE = "active", "Aktif"
        PAUSED = "paused", "Duraklatıldı"
        COMPLETED = "completed", "Tamamlandı"
        REJECTED = "rejected", "Reddedildi"

    class BillingType(models.TextChoices):
        CPM = "cpm", "CPM (1000 Gösterim)"
        CPC = "cpc", "CPC (Tıklama Başı)"

    class ModerationStatus(models.TextChoices):
        PENDING = "pending", "Taranmadı"
        AUTO_APPROVED = "auto_approved", "Otomatik Onaylandı"
        FLAGGED = "flagged", "İşaretlendi"
        HUMAN_REVIEW = "human_review", "İnsan İncelemesi"
        REJECTED = "rejected", "Reddedildi"

    advertiser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="campaigns",
    )
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True, default="", help_text="Admin tarafından red edilme sebebi")

    # --- UTM otomasyonu (FAZ 5) ---------------------------------------------
    # `utm_auto_generate=True` ise `telegram_client.build_tracking_url` her
    # click redirect'te UTM param'larını target_url'e append eder.
    # Boş bırakılan alanlar otomatik doldurulur:
    #   source=aimaaads, medium=<billing_type>, campaign=<id>-<slug>, content=<ad_id>
    # Advertiser herhangi birini doldurup override edebilir.
    utm_auto_generate = models.BooleanField(default=True)
    utm_source = models.CharField(max_length=100, blank=True, default="")
    utm_medium = models.CharField(max_length=100, blank=True, default="")
    utm_campaign = models.CharField(max_length=100, blank=True, default="")
    utm_content_template = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Boş ise ad_id kullanılır — her ad için otomatik content üretimi",
    )

    # --- Moderasyon pipeline alanları (FAZ 2) ------------------------------
    moderation_status = models.CharField(
        max_length=20,
        choices=ModerationStatus.choices,
        default=ModerationStatus.PENDING,
        db_index=True,
    )
    moderation_flags = models.JSONField(
        default=list,
        blank=True,
        help_text="Moderasyon taramasından gelen kategori bayrakları (kumar, alkol, ...)",
    )
    moderation_notes = models.TextField(
        blank=True,
        default="",
        help_text="Moderatör notları — queue'dan yapılan onay/red sebepleri",
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="moderated_campaigns",
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    # Hedefleme
    target_categories = models.ManyToManyField(
        "channels_app.Category",
        blank=True,
        related_name="targeted_campaigns",
    )
    target_languages = models.JSONField(
        default=list,
        help_text='Hedef diller, örn: ["uz", "ru"]',
    )
    min_subscribers = models.IntegerField(default=0)

    # Bütçe
    billing_type = models.CharField(
        max_length=10, choices=BillingType.choices, default=BillingType.CPM
    )
    budget = models.DecimalField(max_digits=12, decimal_places=2)
    daily_budget = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bid_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="CPM veya CPC teklif tutarı (UZS)"
    )
    spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Zamanlama
    start_date = models.DateTimeField(null=True, blank=True, help_text="Boş bırakılırsa hemen başlar")
    end_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "campaigns"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.advertiser.company_name})"

    @property
    def remaining_budget(self):
        return self.budget - self.spent

    @property
    def is_budget_exhausted(self):
        return self.spent >= self.budget


class AdVariantExperiment(models.Model):
    """A/B test experiment — aynı kampanya altında çoklu Ad variant'ı yönetir (FAZ 5).

    Akış:
      1. Advertiser kampanyada 2+ Ad kreatifi oluşturur, hepsini `experiment`'e bağlar.
      2. `traffic_split` JSON'a göre `schedule_campaign` weighted random seçer.
      3. Nightly `pick_ab_winner` task:
         - Kriter CTR       → min_impressions + min_clicks kontrol
         - Kriter conv_rate → min_conversions kontrol
         - Min sample sağlandıysa, ek 24h peeking koruması bekler
         - Two-tailed Z-test p<0.05 → winner
         - max_experiment_days aşılırsa status=INCONCLUSIVE, 50/50 devam

    Winner seçilince `status=COMPLETED`, `traffic_split` %100 winner'a kayar,
    `winner_ad` set edilir, `decided_at` damgalanır.
    """

    class Status(models.TextChoices):
        RUNNING = "running", "Çalışıyor"
        COMPLETED = "completed", "Tamamlandı"
        INCONCLUSIVE = "inconclusive", "Sonuçsuz"
        PAUSED = "paused", "Durduruldu"

    class Criteria(models.TextChoices):
        CTR = "ctr", "CTR (Tıklama Oranı)"
        CONVERSION_RATE = "conversion_rate", "Conversion Oranı"
        CPA = "cpa", "CPA (Conversion Başına Maliyet)"

    # Kampanya başına çoklu experiment (geçmiş arşivlensin), ancak aynı anda
    # yalnızca BİR `status='running'` experiment olabilir — Meta.constraints
    # üzerindeki partial unique index bunu garantiler. Paralel experiment
    # (başlık + görsel aynı anda) ileride bu constraint'i `status IN (running, ...)`
    # olarak gevşetmekle mümkün.
    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, related_name="experiments",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RUNNING, db_index=True,
    )
    winner_criteria = models.CharField(
        max_length=20, choices=Criteria.choices, default=Criteria.CTR,
    )

    # traffic_split: {"ad_id": weight} — weight'ler toplamı 100 olmalı (service validate eder).
    # winner seçildikten sonra bu dict `{"winner_id": 100}`'a çevrilir.
    traffic_split = models.JSONField(default=dict, blank=True)

    # Winner criteria'ya göre hangi threshold'u kullanırız —
    # (criteria, field) eşlemesi servis katmanında.
    min_impressions_per_variant = models.IntegerField(default=2000)
    min_clicks_per_variant = models.IntegerField(default=40)
    min_conversions_per_variant = models.IntegerField(default=30)

    # Peeking koruması — min sample sağlandıktan sonra ek bekleme.
    peeking_wait_hours = models.PositiveSmallIntegerField(default=24)

    # Max koşma süresi — aşılırsa inconclusive.
    max_experiment_days = models.PositiveSmallIntegerField(default=30)

    # Min sample'a ulaşıldığı an — peeking_wait_hours ölçümü buradan başlar.
    min_sample_reached_at = models.DateTimeField(null=True, blank=True)

    # Winner
    winner_ad = models.ForeignKey(
        "ads.Ad",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="winner_of_experiments",
    )
    # Z-test sonucu — audit için saklanır.
    p_value = models.DecimalField(
        max_digits=10, decimal_places=8, null=True, blank=True,
    )
    decision_notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ad_variant_experiments"
        ordering = ["-created_at"]
        constraints = [
            # Kampanya başına aynı anda yalnızca bir RUNNING experiment olsun.
            # Geçmiş completed/inconclusive/paused satırları kısıt dışı —
            # arşiv olarak kalmaya devam eder.
            models.UniqueConstraint(
                fields=["campaign"],
                condition=models.Q(status="running"),
                name="unique_running_experiment_per_campaign",
            ),
        ]

    def __str__(self):
        return f"Experiment #{self.pk} campaign={self.campaign_id} ({self.status})"


class Ad(models.Model):
    """Tek bir reklam kreatifi."""

    class AdType(models.TextChoices):
        TEXT = "text", "Sadece Metin"
        IMAGE = "image", "Görsel + Metin"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="ads")

    # A/B test variant'ı (FAZ 5). Campaign'in deney'i varsa bu alan set edilir.
    # `schedule_campaign` `experiment.traffic_split`'e göre weighted seçim yapar.
    experiment = models.ForeignKey(
        AdVariantExperiment,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="variants",
    )

    ad_type = models.CharField(max_length=10, choices=AdType.choices, default=AdType.TEXT)
    text_uz = models.TextField(help_text="Reklam metni (Özbekçe)")
    text_ru = models.TextField(blank=True, default="", help_text="Reklam metni (Rusça)")
    image = models.ImageField(upload_to="ads/images/", null=True, blank=True)

    # CTA butonu
    button_text = models.CharField(max_length=50, blank=True, default="")
    button_url = models.URLField(blank=True, default="")

    # İstatistikler (denormalized for quick access)
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ads"

    def __str__(self):
        return f"Ad #{self.id} - {self.campaign.name}"

    @property
    def ctr(self):
        if self.impressions == 0:
            return 0
        return round((self.clicks / self.impressions) * 100, 2)


class AdPlacement(models.Model):
    """Bir reklamın belirli bir kanalda yayınlanma kaydı.

    Teslimat durumu (`status`) ve mali durum (`billing_status`) ortogonaldir:
    - `status`: mesajın Telegram üzerindeki yaşam döngüsü (scheduled/sent/failed/deleted)
    - `billing_status`: kampanya bütçesi ve yayıncı gelirinin hesaba yazılıp yazılmadığı
    Bu ayrım, mesaj silme başarısız olsa dahi billing'in idempotent kalmasını sağlar.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Planlandı"
        SENT = "sent", "Gönderildi"
        FAILED = "failed", "Başarısız"
        DELETED = "deleted", "Silindi"

    class BillingStatus(models.TextChoices):
        PENDING = "pending", "Beklemede"
        BILLED = "billed", "Faturalandı"
        FAILED = "failed", "Başarısız"
        SKIPPED = "skipped", "Atlandı"

    class PublisherAction(models.TextChoices):
        AUTO = "auto", "Otomatik"
        ACCEPTED = "accepted", "Yayıncı Onayladı"
        REJECTED = "rejected", "Yayıncı Reddetti"

    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="placements")
    channel = models.ForeignKey(
        "channels_app.TelegramChannel",
        on_delete=models.CASCADE,
        related_name="ad_placements",
    )
    telegram_message_id = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)

    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    # valid_clicks — fraud filtresinden geçen click sayısı (FAZ 3).
    # CPC billing bu alanı kullanır; `clicks` raw counter olarak kalır
    # ve audit amacıyla saklanır.
    valid_clicks = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    publisher_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    scheduled_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    delete_after_hours = models.IntegerField(default=24)

    # Billing idempotency — settlement transaction'ı tarafından set edilir.
    # `billed_at IS NOT NULL` olduğunda kampanya/kanal muhasebesi işlenmiş demektir,
    # aynı placement ikinci kez faturalanmaz.
    billed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    billing_status = models.CharField(
        max_length=20,
        choices=BillingStatus.choices,
        default=BillingStatus.PENDING,
        db_index=True,
    )

    # --- Yayıncı red/onay mekanizması (FAZ 2) ------------------------------
    # `deliver_scheduled_ads` dispatcher'ı `publisher_action != REJECTED`
    # koşuluyla filtreler; red edilen placement için `reassign_rejected_placement`
    # yeni bir kanal bulmaya çalışır. `reassignment_count` sonsuz döngüye karşı
    # güvenlik sayacıdır.
    publisher_action = models.CharField(
        max_length=20,
        choices=PublisherAction.choices,
        default=PublisherAction.AUTO,
        db_index=True,
    )
    publisher_rejection_reason = models.TextField(blank=True, default="")
    reassignment_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ad_placements"
        ordering = ["-scheduled_at"]
        unique_together = ["ad", "channel", "scheduled_at"]

    def __str__(self):
        return f"Placement: {self.ad} → {self.channel}"
