"""
Reklam Dağıtım Servisi
======================
Kampanya hedefleme kriterlerine göre uygun kanalları eşleştirir
ve reklam yerleştirmelerini planlar.
"""

import logging
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.db.models import Q, F, Count

from channels_app.models import TelegramChannel
from .models import Campaign, Ad, AdPlacement

logger = logging.getLogger(__name__)

# İki ondalık basamağa quantize — UZS tutarlar için tam hassasiyet.
_MONEY_QUANT = Decimal("0.01")


def _quantize_money(value: Decimal) -> Decimal:
    """Parasal bir Decimal değerini iki ondalığa yuvarla (ROUND_HALF_UP)."""
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


class AdDeliveryService:
    """Reklam eşleştirme ve dağıtım motoru."""

    @staticmethod
    def find_matching_channels(campaign: Campaign) -> list[TelegramChannel]:
        """Kampanya kriterlerine uyan kanalları bul."""
        channels = TelegramChannel.objects.filter(
            status="approved",
            is_active=True,
            bot_added=True,
        )

        # Kategori filtresi
        if campaign.target_categories.exists():
            channels = channels.filter(
                category__in=campaign.target_categories.all()
            )

        # Dil filtresi
        if campaign.target_languages:
            channels = channels.filter(
                Q(language__in=campaign.target_languages) |
                Q(language="mixed")
            )

        # Minimum abone filtresi
        if campaign.min_subscribers > 0:
            channels = channels.filter(
                subscriber_count__gte=campaign.min_subscribers
            )

        # CPM uygunluğu — teklif kanalın minimum CPM'inden düşük olmamalı
        channels = channels.filter(min_cpm__lte=campaign.bid_amount)

        # Bugün zaten çok reklam almış kanalları çıkar
        today = timezone.now().date()
        channels = channels.annotate(
            today_ads=Count(
                "ad_placements",
                filter=Q(ad_placements__scheduled_at__date=today),
            )
        ).filter(today_ads__lt=F("max_ads_per_day"))

        return list(channels)

    @staticmethod
    def schedule_campaign(campaign: Campaign):
        """Kampanya için reklam yerleştirmelerini planla."""
        channels = AdDeliveryService.find_matching_channels(campaign)

        if not channels:
            return []

        ads = list(campaign.ads.filter(is_active=True))
        if not ads:
            return []

        placements = []
        now = timezone.now()
        remaining = campaign.remaining_budget

        target_category_ids = (
            set(campaign.target_categories.values_list("id", flat=True))
            if campaign.target_categories.exists()
            else None
        )

        for channel in channels:
            if remaining <= 0:
                break

            # Kategori uyumu çift kontrolü — `find_matching_channels` zaten
            # filter uyguluyor, ancak buradan yakalanan mismatch advertiser'ın
            # yanlış kategori seçtiğine işaret eder. Log + skip.
            if target_category_ids is not None and channel.category_id not in target_category_ids:
                logger.warning(
                    "Category mismatch for campaign %s — skipping channel %s (channel_cat=%s targets=%s)",
                    campaign.id,
                    channel.id,
                    channel.category_id,
                    sorted(target_category_ids),
                )
                continue

            # Her kanal için en uygun reklamı seç (round-robin)
            ad = ads[len(placements) % len(ads)]

            # Tahmini maliyet hesapla — Decimal aritmetiği.
            estimated_cost = (
                Decimal(channel.avg_views) / Decimal(1000)
            ) * campaign.bid_amount

            if estimated_cost > remaining:
                continue

            # Uygun saatte planla
            scheduled_time = AdDeliveryService._next_available_slot(channel, now)

            placement = AdPlacement.objects.create(
                ad=ad,
                channel=channel,
                scheduled_at=scheduled_time,
                delete_after_hours=24,
            )
            placements.append(placement)
            remaining -= estimated_cost

        return placements

    @staticmethod
    def _next_available_slot(channel: TelegramChannel, after: timezone.datetime):
        """Kanal için bir sonraki uygun reklam saatini bul."""
        slot = after + timedelta(minutes=30)

        # Kanalın reklam saatleri içinde olmalı
        if slot.hour < channel.ad_hours_start:
            slot = slot.replace(
                hour=channel.ad_hours_start, minute=0, second=0
            )
        elif slot.hour >= channel.ad_hours_end:
            slot = (slot + timedelta(days=1)).replace(
                hour=channel.ad_hours_start, minute=0, second=0
            )

        return slot

    @staticmethod
    def calculate_placement_cost(placement: AdPlacement) -> dict:
        """Yerleştirme maliyetini hesapla ve gelir dağılımı yap.

        Tüm aritmetik `Decimal` üzerinde yapılır — float yuvarlama hatası
        milyonlarca placement üzerinde birikerek finansal sapmaya yol açar.
        Dönen değerler iki ondalık basamağa quantize edilmiş `Decimal`'dır;
        platform_fee + publisher_revenue == total_cost invariantı korunur.
        """
        from django.conf import settings

        campaign = placement.ad.campaign
        bid_amount = campaign.bid_amount  # zaten Decimal
        impressions = placement.impressions
        # CPC billing — fraud filtresinden geçen click sayısı kullanılır.
        # `valid_clicks` alanı 0 ise (FAZ 3 öncesi veri veya hiç doğrulama
        # yapılmamış placement), raw `clicks`'e düşeriz. Bu fallback sayesinde
        # eski placement'lar migration sonrası da doğru ücretlendirilir.
        billable_clicks = placement.valid_clicks or placement.clicks

        if campaign.billing_type == "cpm":
            # CPM = 1000 gösterim başına bid_amount
            cost = (Decimal(impressions) / Decimal(1000)) * bid_amount
        else:  # cpc
            cost = Decimal(billable_clicks) * bid_amount

        # Komisyon oranını Decimal'a taşırken string köprüsü — float hassasiyet kaybını önler.
        commission_rate = Decimal(str(settings.PLATFORM_COMMISSION_RATE))

        total_cost = _quantize_money(cost)
        platform_fee = _quantize_money(total_cost * commission_rate)
        # Publisher payını total'den çıkararak hesapla — yuvarlamadan sonra
        # fee + revenue == total invariantı garantilenir.
        publisher_revenue = _quantize_money(total_cost - platform_fee)

        return {
            "total_cost": total_cost,
            "platform_fee": platform_fee,
            "publisher_revenue": publisher_revenue,
        }
