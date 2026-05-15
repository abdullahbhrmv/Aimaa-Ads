"""
Ödeme ve bakiye modelleri (FAZ 4a).

Tasarım notları:

- `UserBalance` — hesap başına TEK satır (OneToOne). `balance` likit kullanılabilir
  bakiye, `frozen_amount` aktif kampanyalar için rezerve. Toplam varlık
  = balance + frozen_amount. Kritik: `balance` DAİMA `frozen`'ı hariç tutar.
- `Transaction` — tüm bakiye mutasyonları burada audit trail'lenir. Provider
  ödemeleri için `(provider, provider_ref)` unique constraint replay attack'ı
  önler.
- `User.balance` field'ı geriye dönük uyumluluk için denormalize mirror
  olarak korunur (`payments.services` her mutasyonda senkronize eder).
  FAZ 4b'de property'ye çevrilebilir.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class UserBalance(models.Model):
    """Kullanıcı cüzdanı — advertiser ve publisher için ayrı ayrı."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet",
    )
    # Likit bakiye — frozen HARİÇ. Kampanya onayında frozen'a taşınır.
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    # Aktif kampanyalar için rezerve edilmiş miktar.
    frozen_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="UZS")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_balances"

    def __str__(self):
        return f"{self.user.username}: {self.balance} + {self.frozen_amount} frozen"

    @property
    def total_assets(self) -> Decimal:
        """Likit + frozen toplamı — kullanıcının sistemdeki toplam parası."""
        return self.balance + self.frozen_amount


class Transaction(models.Model):
    """Bakiye mutasyon kaydı — tüm ödeme, kampanya ve payout akışları buraya düşer."""

    class Type(models.TextChoices):
        DEPOSIT = "deposit", "Bakiye Yükleme"
        WITHDRAW = "withdraw", "Çekim"
        AD_SPEND = "ad_spend", "Reklam Harcaması"
        AD_EARNING = "ad_earning", "Reklam Geliri"
        FREEZE = "freeze", "Bütçe Dondurma"
        REFUND = "refund", "Bütçe İadesi"
        ADJUSTMENT = "adjustment", "Manuel Düzeltme"

    class Status(models.TextChoices):
        PENDING = "pending", "Beklemede"
        COMPLETED = "completed", "Tamamlandı"
        FAILED = "failed", "Başarısız"
        CANCELLED = "cancelled", "İptal"

    class Provider(models.TextChoices):
        CLICK = "click", "Click.uz"
        PAYME = "payme", "Payme"
        MANUAL = "manual", "Manuel"
        INTERNAL = "internal", "Dahili"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.COMPLETED, db_index=True
    )
    # Tutar her zaman pozitif Decimal — işaret `type`'tan çıkarılır.
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    # Mutasyon sonrası snapshot — debug ve audit için.
    balance_after = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    frozen_after = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )

    provider = models.CharField(
        max_length=20, choices=Provider.choices, default=Provider.INTERNAL
    )
    # Provider tarafındaki benzersiz referans (click_trans_id, payme transaction_id, ...).
    # Boş olabilir (internal transaction'lar için).
    provider_ref = models.CharField(max_length=255, blank=True, default="")

    description = models.CharField(max_length=500, blank=True, default="")

    # Bağlantılı iş nesneleri — analytics ve trace için.
    related_campaign = models.ForeignKey(
        "ads.Campaign",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    related_placement = models.ForeignKey(
        "ads.AdPlacement",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    related_payout = models.ForeignKey(
        "core.PayoutRequest",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_transactions"
        ordering = ["-created_at"]
        constraints = [
            # Aynı (provider, provider_ref) iki kere gelmesin — replay attack'a karşı
            # koruma. Boş provider_ref'ler (internal transaction'lar) hariç tutulur.
            models.UniqueConstraint(
                fields=["provider", "provider_ref"],
                condition=~models.Q(provider_ref=""),
                name="unique_provider_ref_when_set",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["type", "status"]),
            models.Index(fields=["provider", "provider_ref"]),
        ]

    def __str__(self):
        return f"#{self.pk} {self.type} {self.amount} ({self.status})"


class Invoice(models.Model):
    """Advertiser deposit'i için e-fatura (KDV dahil).

    FAZ 4a'da Didox/Faktura.uz entegrasyonu yok — sadece iç kayıt + fatura
    numarası üretilir. Provider `manual` default'u, FAZ 4b'de değişir.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Taslak"
        ISSUED = "issued", "Düzenlendi"
        CANCELLED = "cancelled", "İptal"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    transaction = models.OneToOneField(
        Transaction,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="invoice",
    )
    invoice_number = models.CharField(max_length=50, unique=True)

    net_amount = models.DecimalField(max_digits=14, decimal_places=2)
    kdv_amount = models.DecimalField(max_digits=14, decimal_places=2)
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="UZS")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    provider = models.CharField(
        max_length=20,
        default="manual",
        help_text="didox, faktura, manual — FAZ 4b'de aktifleşir",
    )
    provider_ref = models.CharField(max_length=255, blank=True, default="")

    issued_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_invoices"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invoice {self.invoice_number} ({self.gross_amount} {self.currency})"


class PaymentAuditLog(models.Model):
    """Her webhook çağrısı ve kritik balance mutasyonu için audit satırı.

    Replay, fraud analizi ve destek kayıtları için immutable log. Prod'da
    retention politikası (örn. 1 yıl) eklenebilir.
    """

    event_type = models.CharField(max_length=50, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_audit_logs",
    )
    provider = models.CharField(max_length=20, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    signature_valid = models.BooleanField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    result = models.CharField(max_length=30, default="success")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "payment_audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]


class PaymentSettings(models.Model):
    """Platform iş kuralları singleton (secret'lar env'de tutulur)."""

    min_payout_amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=Decimal("50000"),
        help_text="Yayıncı çekim minimumu (UZS)",
    )
    platform_commission_rate = models.DecimalField(
        max_digits=5, decimal_places=4,
        default=Decimal("0.3000"),
        help_text="Platform komisyon oranı (0-1 arası)",
    )
    kdv_rate = models.DecimalField(
        max_digits=5, decimal_places=4,
        default=Decimal("0.1200"),
        help_text="QQS / KDV oranı (UZ %12)",
    )
    currency = models.CharField(max_length=3, default="UZS")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_settings"
        verbose_name_plural = "payment settings"

    def __str__(self):
        return f"PaymentSettings (commission={self.platform_commission_rate})"

    @classmethod
    def get_solo(cls) -> "PaymentSettings":
        """Singleton erişim — pk=1 satırını oluşturur ya da döner."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
