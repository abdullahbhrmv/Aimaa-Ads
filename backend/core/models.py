from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Platform kullanıcısı — reklamveren, kanal sahibi veya admin olabilir.

    Permission Hierarchy:
    - is_superuser=True: Root admin (tam yetki, silinmez, her şeye erişir)
    - is_staff=True + role=ADMIN: Staff admin (kısıtlı yetkili, silinebilir)
    - role=ADVERTISER: Reklamveren (kampanya oluşturur)
    - role=PUBLISHER: Kanal sahibi (reklamları yayınlar)
    """

    class Role(models.TextChoices):
        ADVERTISER = "advertiser", "Reklamveren"
        PUBLISHER = "publisher", "Kanal Sahibi"
        ADMIN = "admin", "Admin"

    class Language(models.TextChoices):
        UZ = "uz", "O'zbekcha"
        RU = "ru", "Русский"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ADVERTISER)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.UZ)
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    telegram_username = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    company_name = models.CharField(max_length=255, blank=True, default="")
    company_description = models.TextField(blank=True, default="", help_text="Şirket hakkında kısa açıklama")
    website = models.URLField(blank=True, default="", help_text="Şirket web sitesi")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
        permissions = [
            ("can_moderate_channels", "Kanalları moderasyon yapabilir"),
            ("can_review_campaigns", "Kampanya inceleyebilir"),
            ("can_manage_users", "Kullanıcı yönetebilir"),
            ("can_view_revenue", "Gelir raporlarını görebilir"),
            ("can_manage_categories", "Kategorileri yönetebilir"),
            ("can_approve_payouts", "Ödeme taleplerini onaylayabilir"),
        ]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_root_admin(self):
        """Root admin kontrolü (superuser)."""
        return self.is_superuser

    @property
    def is_staff_admin(self):
        """Staff admin kontrolü (is_staff=True, role=ADMIN ama superuser değil)."""
        return self.is_staff and self.role == self.Role.ADMIN and not self.is_superuser

    @property
    def is_any_admin(self):
        """Herhangi bir admin tipi mi (root veya staff)."""
        return self.is_superuser or (self.is_staff and self.role == self.Role.ADMIN)


class PayoutRequest(models.Model):
    """Nashriyotchi pul yechib olish so'rovi.

    FAZ 4a'da genişletildi: provider (click/payme/manual) + provider-spesifik
    hesap bilgisi + provider'dan gelen status/ref. Otomatik API çağrıları
    FAZ 4b'de aktifleşecek; şu an sadece manuel admin onay akışı + Transaction
    kaydı (`payments.services.withdraw_for_payout`).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        PROCESSING = "processing", "Jarayonda"
        COMPLETED = "completed", "Bajarildi"
        REJECTED = "rejected", "Rad etildi"

    class Provider(models.TextChoices):
        CLICK = "click", "Click.uz"
        PAYME = "payme", "Payme"
        MANUAL = "manual", "Manuel"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payout_requests")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment_method = models.CharField(max_length=50, blank=True, default="")
    payment_details = models.JSONField(default=dict, blank=True)
    admin_note = models.TextField(blank=True, default="")

    # FAZ 4a yeni alanlar — payout otomasyonu iskelesi.
    provider = models.CharField(
        max_length=20, choices=Provider.choices, default=Provider.MANUAL,
        help_text="Ödeme provider'ı — FAZ 4b'de otomatik havale bu alana bakar",
    )
    provider_account = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Provider hedef hesabı (kart numarası veya telefon)",
    )
    provider_status = models.CharField(
        max_length=50, blank=True, default="",
        help_text="Provider'ın kendi status string'i (raw response)",
    )
    provider_ref = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Provider transaction ref'i — audit ve mutabakat için",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payout_requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payout #{self.pk} — {self.user.username} — {self.amount} UZS ({self.status})"
