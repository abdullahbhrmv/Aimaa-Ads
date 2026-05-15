"""
factory_boy fabrikaları — test verisi üretimi.

Kullanım:
    placement = AdPlacementFactory(
        ad__campaign__bid_amount=Decimal("5000"),
        channel__telegram_chat_id=-100500,
    )
"""

from __future__ import annotations

from decimal import Decimal

import factory
from django.utils import timezone

from ads.models import Ad, AdPlacement, Campaign
from analytics.models import ClickEvent
from channels_app.models import Category, DailyChannelSnapshot, TelegramChannel
from core.models import PayoutRequest, User
from payments.models import Invoice, Transaction, UserBalance
from pixel.models import ConversionEvent, PixelInstallation


class AdvertiserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"advertiser_{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.test")
    role = User.Role.ADVERTISER
    company_name = factory.LazyAttribute(lambda o: f"Co {o.username}")
    balance = Decimal("1000000.00")


class PublisherFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"publisher_{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.test")
    role = User.Role.PUBLISHER
    telegram_id = factory.Sequence(lambda n: 1000000 + n)


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category
        django_get_or_create = ("slug",)

    name_uz = factory.Sequence(lambda n: f"Kategoriya {n}")
    name_ru = factory.Sequence(lambda n: f"Категория {n}")
    slug = factory.Sequence(lambda n: f"cat-{n}")
    icon = "📁"
    is_active = True


class TelegramChannelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TelegramChannel

    owner = factory.SubFactory(PublisherFactory)
    category = factory.SubFactory(CategoryFactory)
    telegram_chat_id = factory.Sequence(lambda n: -1001000000 - n)
    username = factory.Sequence(lambda n: f"channel_{n}")
    title = factory.LazyAttribute(lambda o: f"Channel {o.username}")
    language = "uz"
    subscriber_count = 5000
    avg_views = 2000
    status = TelegramChannel.Status.APPROVED
    is_active = True
    bot_added = True
    min_cpm = Decimal("5000.00")
    max_ads_per_day = 3
    ad_hours_start = 0  # test'lerde 24/7 erişim
    ad_hours_end = 24
    total_earnings = Decimal("0")
    pending_earnings = Decimal("0")


class CampaignFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Campaign

    advertiser = factory.SubFactory(AdvertiserFactory)
    name = factory.Sequence(lambda n: f"Campaign {n}")
    status = Campaign.Status.ACTIVE
    billing_type = Campaign.BillingType.CPM
    budget = Decimal("100000.00")
    daily_budget = Decimal("0")
    bid_amount = Decimal("5000.00")
    spent = Decimal("0")
    target_languages = factory.LazyFunction(list)


class AdFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ad

    campaign = factory.SubFactory(CampaignFactory)
    ad_type = Ad.AdType.TEXT
    text_uz = "Reklam matni"
    text_ru = ""
    is_active = True


class AdPlacementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AdPlacement

    ad = factory.SubFactory(AdFactory)
    channel = factory.SubFactory(TelegramChannelFactory)
    status = AdPlacement.Status.SCHEDULED
    billing_status = AdPlacement.BillingStatus.PENDING
    scheduled_at = factory.LazyFunction(timezone.now)
    delete_after_hours = 24
    impressions = 0
    clicks = 0
    # valid_clicks default olarak clicks ile aynı — eski billing test'leri
    # fraud filtresi olmadan da çalışmaya devam eder (fallback mantığı).
    valid_clicks = factory.LazyAttribute(lambda o: o.clicks)
    cost = Decimal("0")
    publisher_revenue = Decimal("0")


class DailyChannelSnapshotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DailyChannelSnapshot

    channel = factory.SubFactory(TelegramChannelFactory)
    date = factory.LazyFunction(lambda: timezone.now().date())
    subscriber_count = 5000
    avg_views = 2000
    quality_score = 50


class ClickEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClickEvent

    placement = factory.SubFactory(AdPlacementFactory)
    ip_hash = factory.Sequence(lambda n: f"ip-hash-{n:064d}"[:64])
    ip_subnet_hash = factory.Sequence(lambda n: f"subnet-hash-{n:058d}"[:64])
    user_agent_hash = factory.Sequence(lambda n: f"ua-hash-{n:060d}"[:64])
    is_suspicious = False
    suspicion_reasons = factory.LazyFunction(list)


# --- FAZ 4a factory'leri -----------------------------------------------------


class UserBalanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserBalance
        django_get_or_create = ("user",)

    user = factory.SubFactory(AdvertiserFactory)
    balance = Decimal("1000000.00")
    frozen_amount = Decimal("0")
    currency = "UZS"


class TransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Transaction

    user = factory.SubFactory(AdvertiserFactory)
    type = Transaction.Type.DEPOSIT
    status = Transaction.Status.COMPLETED
    amount = Decimal("100000.00")
    provider = Transaction.Provider.INTERNAL
    provider_ref = ""
    description = "Test transaction"


class PayoutRequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PayoutRequest

    user = factory.SubFactory(PublisherFactory)
    amount = Decimal("100000.00")
    status = PayoutRequest.Status.PENDING
    provider = PayoutRequest.Provider.MANUAL
    provider_account = ""


class InvoiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Invoice

    user = factory.SubFactory(AdvertiserFactory)
    invoice_number = factory.Sequence(lambda n: f"INV-{n:06d}")
    net_amount = Decimal("100000.00")
    kdv_amount = Decimal("12000.00")
    gross_amount = Decimal("112000.00")
    currency = "UZS"
    status = Invoice.Status.DRAFT
    provider = "manual"


# --- FAZ 5 factory'leri ------------------------------------------------------


class PixelInstallationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PixelInstallation
        django_get_or_create = ("advertiser",)

    advertiser = factory.SubFactory(AdvertiserFactory)
    enabled = True
    debug_mode = False
    # Test default — Purchase/Lead attribution'a girer, PageView değil.
    attribution_events = factory.LazyFunction(
        lambda: ["Purchase", "Lead", "CompleteRegistration"]
    )
    allowed_domains = factory.LazyFunction(
        lambda: ["example.com", "*.example.com"]
    )
    click_window_days = 7
    view_window_days = 1
    advanced_matching_enabled = True


class ConversionEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ConversionEvent

    pixel = factory.SubFactory(PixelInstallationFactory)
    event_name = "Purchase"
    event_id = factory.LazyFunction(lambda: __import__("uuid").uuid4())
    event_source = ConversionEvent.Source.BROWSER
    url = "https://example.com/thanks"
    value = Decimal("50000.00")
    currency = "UZS"
