"""
AimaaPixel modelleri (FAZ 5).

Tasarım:

- `PixelInstallation` — advertiser başına bir pixel config. `pixel_id` UUID,
  embed snippet'inde görünür; `allowed_domains` whitelist wildcard destekler
  (*.example.com). `debug_mode` SDK'nın console.log davranışını açar ve
  localhost origin'ini kabul eder.
- `ConversionEvent` — her pixel çağrısının ham kaydı. Browser (client) ve
  Conversions API (server-side) aynı modele yazar; `event_source` ayırır.
  Dedup `(pixel, event_id)` unique constraint'i üzerinden.
- `Conversion` — attribution'ı başarılı olmuş ConversionEvent'in business
  anlamlı kaydı. Sadece `PixelInstallation.attribution_events` listesindeki
  event'ler için üretilir (ör. Purchase/Lead, PageView için DEĞİL).
  `attribution_path` FAZ 5.5 multi-touch için placeholder — şimdilik boş.

Privacy:
- IP ve user-agent asla raw saklanmaz — FAZ 3 `FRAUD_IP_SALT` ile hash'lenir.
- Advanced matching alanları (`em_hash`, `ph_hash`, `external_id_hash`)
  SDK tarafında SHA-256'lanır; backend plain PII kabul etmez.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


# --- allowed_domains validation ---------------------------------------------
# Domain formatı: opsiyonel "*." wildcard + lowercase alnum + en az bir nokta.
# Örnek geçerli: "example.com", "*.shop.example.com", "api.example.co.uk"
# Örnek geçersiz: "HTTP://example.com", "*.*.example.com", "example",
#                 "-foo.com", "foo_bar.com"
_DOMAIN_RE = re.compile(r"^(\*\.)?[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")
_MAX_DOMAIN_LENGTH = 253
_MAX_DOMAIN_ENTRIES = 20


def validate_allowed_domains(value):
    """`PixelInstallation.allowed_domains` için liste-seviyesi validator.

    - En fazla 20 entry
    - Her entry max 253 karakter
    - Her entry `_DOMAIN_RE` regex'ine uysun
    """
    if not isinstance(value, list):
        raise ValidationError("allowed_domains bir liste olmalı")
    if len(value) > _MAX_DOMAIN_ENTRIES:
        raise ValidationError(
            f"En fazla {_MAX_DOMAIN_ENTRIES} domain eklenebilir (girilen: {len(value)})"
        )
    for entry in value:
        if not isinstance(entry, str):
            raise ValidationError(f"Domain string olmalı: {entry!r}")
        if len(entry) > _MAX_DOMAIN_LENGTH:
            raise ValidationError(
                f"Domain {_MAX_DOMAIN_LENGTH} karakteri aşıyor: {entry!r}"
            )
        if not _DOMAIN_RE.match(entry):
            raise ValidationError(
                f"Geçersiz domain formatı: {entry!r} "
                f"(beklenen: örn. example.com veya *.example.com)"
            )


class PixelInstallation(models.Model):
    """Reklamveren başına pixel konfigürasyonu."""

    advertiser = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pixel_installation",
    )
    # Embed snippet'inde görünen public kimlik — UUID4.
    pixel_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)

    # CORS / event whitelist için izinli origin listesi.
    # Format: "example.com" tam eşleşme veya "*.example.com" wildcard.
    # `debug_mode=True` ise ayrıca localhost ve 127.0.0.1 kabul edilir.
    # Form/clean() validation `validate_allowed_domains` tarafından yapılır.
    allowed_domains = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_allowed_domains],
        help_text=(
            "Kabul edilen origin'ler. Wildcard: *.example.com. "
            "Max 20 entry, her biri max 253 karakter."
        ),
    )

    enabled = models.BooleanField(default=True, db_index=True)
    debug_mode = models.BooleanField(
        default=False,
        help_text="SDK console.log açık + localhost origin kabul edilir",
    )

    # Hangi event'ler Conversion satırı üretir? Diğer event'ler (PageView vs.)
    # sadece ConversionEvent olarak kaydedilir, attribution'a girmez.
    attribution_events = models.JSONField(
        default=list,
        blank=True,
        help_text='Örn: ["Purchase", "Lead", "CompleteRegistration"]',
    )

    # Attribution window — advertiser bazında override edilebilir.
    click_window_days = models.PositiveSmallIntegerField(default=7)
    view_window_days = models.PositiveSmallIntegerField(default=1)

    # Advanced matching (em/ph/external_id) kapalıysa pixel bu alanları
    # kabul etmez — GDPR uyumluluğu için opt-in.
    advanced_matching_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pixel_installations"

    def __str__(self):
        return f"Pixel {self.pixel_id} ({self.advertiser.username})"

    def clean(self):
        """Admin formlarında + full_clean() çağrılarında validator zinciri.

        `validators=[...]` tek başına JSONField içeriği için yetmez — field
        seviyesi validator'ı `full_clean()` üzerinden çalışır. Burada da
        aynı fonksiyonu manuel çağırarak programatik `.save()` öncesi
        `.full_clean()` alışkanlığı olan yerlerin de korumasını sağlarız.
        Servis katmanındaki CRUD buna ek olarak explicit validate etmeli.
        """
        super().clean()
        validate_allowed_domains(self.allowed_domains or [])


class ConversionEvent(models.Model):
    """Pixel'den gelen ham event — attribute edilmese bile saklanır."""

    class Source(models.TextChoices):
        BROWSER = "browser", "Tarayıcı (JS SDK)"
        SERVER = "server", "Server-side Conversions API"

    pixel = models.ForeignKey(
        PixelInstallation,
        on_delete=models.CASCADE,
        related_name="events",
    )
    # Event adı — Meta Pixel konvansiyonu: PageView, Purchase, Lead, ...
    # veya trackCustom() ile gelen serbest isim. Whitelist `services.py`'da.
    event_name = models.CharField(max_length=64, db_index=True)

    # Client + server dedup için. SDK `crypto.randomUUID()` üretir ve hem
    # browser hem server-side post'unda aynı id kullanılır.
    event_id = models.UUIDField(db_index=True)

    event_source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.BROWSER,
    )

    # Landing URL + referrer — UTM'ler ayrıca structured field'larda da.
    url = models.TextField(blank=True, default="")
    referrer = models.TextField(blank=True, default="")

    # Fraud correlation — FAZ 3 hash algoritmasıyla uyumlu.
    user_agent_hash = models.CharField(max_length=64, blank=True, default="")
    ip_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ip_subnet_hash = models.CharField(max_length=64, blank=True, default="")

    # Click ID — redirect endpoint'in cookie veya query param olarak
    # döktüğü ClickEvent.id. Attribution'ın deterministic yolu.
    click_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    # UTM params — structured. Ham URL de `url` field'ında var.
    utm_source = models.CharField(max_length=100, blank=True, default="")
    utm_medium = models.CharField(max_length=100, blank=True, default="")
    utm_campaign = models.CharField(max_length=100, blank=True, default="", db_index=True)
    utm_content = models.CharField(max_length=100, blank=True, default="")
    utm_term = models.CharField(max_length=100, blank=True, default="")

    # Event değeri (Purchase, Lead için). Opsiyonel.
    value = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
    )
    currency = models.CharField(max_length=3, blank=True, default="")

    # Advanced matching — SDK hash'li yollar, backend plain kabul etmez.
    # em_hash index Meta.indexes'de partial (boş değerler hariç).
    # Tüm hash alanları: CharField(64) + blank + default="" — NULL KULLANILMAZ
    # (None vs "" ikiliği debug kabusu; empty string = "değer yok" sinyali).
    em_hash = models.CharField(max_length=64, blank=True, default="")
    ph_hash = models.CharField(max_length=64, blank=True, default="")
    fn_hash = models.CharField(max_length=64, blank=True, default="")
    ln_hash = models.CharField(max_length=64, blank=True, default="")
    external_id_hash = models.CharField(max_length=64, blank=True, default="")

    # trackCustom ek parametreleri.
    raw_params = models.JSONField(default=dict, blank=True)

    # Attribution durumu — hiç denenmediyse NULL. Denenmiş ama
    # match bulunamamışsa NOT NULL ama ilgili Conversion yok. Bu sayede
    # attribution task eski event'lere sonsuza dek dönüp durmaz.
    attribution_attempted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "conversion_events"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["pixel", "event_id"],
                name="unique_pixel_event_id",
            ),
        ]
        indexes = [
            models.Index(fields=["pixel", "event_name", "-created_at"]),
            models.Index(fields=["attribution_attempted_at"]),
            # Partial — sadece em_hash set olan satırları indexle. Cross-device
            # attribution lookup'ta (FAZ 5.5) kullanılacak.
            models.Index(
                fields=["em_hash", "-created_at"],
                condition=~models.Q(em_hash=""),
                name="conv_ev_em_hash_partial",
            ),
        ]

    def __str__(self):
        return f"{self.event_name} @ pixel={self.pixel_id} id={self.event_id}"


class Conversion(models.Model):
    """Attribute edilmiş conversion — dashboard ROI ve funnel için kaynak."""

    class AttributionType(models.TextChoices):
        CLICK = "click", "Tıklama"
        VIEW = "view", "Görüntüleme"

    class TouchMethod(models.TextChoices):
        CLICK_ID = "click_id", "Click ID Cookie/QueryParam"
        UTM = "utm", "UTM Parametreleri"
        ADVANCED_MATCHING = "advanced_matching", "Advanced Matching"

    # Her ConversionEvent en fazla bir Conversion üretir (last-touch).
    # First-touch ayrı satır oluşturmaz — raporda ClickEvent zinciri üzerinden
    # dinamik hesaplanır (FAZ 5 karar D3).
    #
    # Race-condition notu (Adım 2 — attribution service):
    # `attribute_pending_conversions` task paralel worker'larda çalışabilir;
    # aynı event için iki worker eşzamanlı Conversion yaratmayı deneyebilir.
    # Çözüm: servis katmanında `get_or_create(event=...)` + `IntegrityError`
    # try/except. OneToOne unique constraint ikinci yaratmayı DB-level'da
    # reddeder; handler mevcut Conversion'ı döner.
    event = models.OneToOneField(
        ConversionEvent,
        on_delete=models.CASCADE,
        related_name="conversion",
    )

    campaign = models.ForeignKey(
        "ads.Campaign",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="conversions",
    )
    placement = models.ForeignKey(
        "ads.AdPlacement",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="conversions",
    )
    click_event = models.ForeignKey(
        "analytics.ClickEvent",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="conversions",
    )

    attribution_type = models.CharField(
        max_length=10, choices=AttributionType.choices, default=AttributionType.CLICK,
    )
    touch_method = models.CharField(
        max_length=32, choices=TouchMethod.choices, default=TouchMethod.CLICK_ID,
    )

    attributed_at = models.DateTimeField(auto_now_add=True)

    # Click zinciri delay'i — click'ten conversion'a geçen süre (saniye).
    # Analytics için: "conversion window ne kadar efektif?" sorusu.
    attribution_delay_seconds = models.BigIntegerField(null=True, blank=True)

    # Event.value'dan kopyalanır — conversion rapor agregasyonunu kolaylaştırır.
    attributed_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
    )
    currency = models.CharField(max_length=3, blank=True, default="UZS")

    # FAZ 5.5 multi-touch placeholder — şimdilik null. Örn:
    # [{"click_id": 12, "weight": 0.4, "type": "first"}, ...]
    attribution_path = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "conversions"
        ordering = ["-attributed_at"]
        indexes = [
            models.Index(fields=["campaign", "-attributed_at"]),
            models.Index(fields=["placement", "-attributed_at"]),
            models.Index(fields=["click_event"]),
        ]

    def __str__(self):
        return f"Conversion #{self.pk} → campaign={self.campaign_id}"
