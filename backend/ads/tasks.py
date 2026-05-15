"""
Periyodik görevler — Celery ile çalışır.

Finansal kritik task'lar iki aşamalıdır:
1. `deliver_scheduled_ads` — planlanmış placement'ları Telegram'a gönderir.
2. `delete_expired_ads` — süresi dolmuş placement'ları tespit eder ve
   her biri için bağımsız bir `_settle_placement` sub-task'ı fırlatır.
3. `_settle_placement` — TEK placement'ın billing'ini ve silinmesini
   idempotent şekilde yürütür. `select_for_update(skip_locked=True)` ve
   `billed_at IS NULL` guard'ı ile çift faturalama imkânsızdır.

Billing sırası: **önce bill et, sonra Telegram'dan sil.** Bu sayede
Telegram delete başarısız olsa bile gelir kaydı sağlam kalır (zararsız
olarak reklam kanalda biraz daha görünür, deletion bir sonraki koşuda
yeniden denenir).
"""

import logging
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ads.models import Ad, AdPlacement, Campaign
from ads.services import AdDeliveryService
from analytics.models import DailyStats
from channels_app.models import TelegramChannel

logger = logging.getLogger(__name__)


# --- Ortak Celery task retry/timeout politikaları ---------------------------
# `acks_late=True` + `task_reject_on_worker_lost=True`: worker'ın ortadan
# kaybolması durumunda mesaj kuyrukta kalır ve yeniden teslim edilir — bu
# yüzden task'ların kendi içinde idempotent olması gerekir.
_CRITICAL_TASK_KWARGS = dict(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    task_reject_on_worker_lost=True,
    soft_time_limit=240,
    time_limit=300,
)


@shared_task(**_CRITICAL_TASK_KWARGS)
def deliver_scheduled_ads(self):
    """Planlanmış reklamları Telegram'a gönder.

    Her placement için `select_for_update(skip_locked=True)` kullanılır;
    eşzamanlı iki worker aynı placement'ı almayacağı için çift gönderim
    imkânsızdır. Başarısız bir placement diğerlerini etkilemez.
    """
    from ads.telegram_client import TelegramAdSender

    now = timezone.now()
    due_ids = list(
        AdPlacement.objects.filter(
            status=AdPlacement.Status.SCHEDULED,
            scheduled_at__lte=now,
            ad__campaign__status="active",
        )
        .exclude(publisher_action=AdPlacement.PublisherAction.REJECTED)
        .values_list("id", flat=True)
    )

    if not due_ids:
        return {"picked": 0}

    sender = TelegramAdSender()
    sent = 0
    failed = 0

    for placement_id in due_ids:
        try:
            with transaction.atomic():
                placement = (
                    AdPlacement.objects.select_for_update(skip_locked=True)
                    .select_related("ad", "channel", "ad__campaign")
                    .filter(
                        id=placement_id,
                        status=AdPlacement.Status.SCHEDULED,
                        scheduled_at__lte=now,
                    )
                    .exclude(publisher_action=AdPlacement.PublisherAction.REJECTED)
                    .first()
                )
                if placement is None:
                    # Başka bir worker aldı veya bu arada durum değişti.
                    continue

                try:
                    message_id = sender.send_ad(
                        chat_id=placement.channel.telegram_chat_id,
                        ad=placement.ad,
                        placement_id=placement.id,
                        channel_language=placement.channel.language,
                    )
                    placement.telegram_message_id = message_id
                    placement.status = AdPlacement.Status.SENT
                    placement.sent_at = timezone.now()
                    placement.save(
                        update_fields=[
                            "telegram_message_id",
                            "status",
                            "sent_at",
                        ]
                    )
                    sent += 1
                except Exception as exc:
                    placement.status = AdPlacement.Status.FAILED
                    placement.save(update_fields=["status"])
                    failed += 1
                    logger.error(
                        "Ad delivery failed for placement %s: %s",
                        placement.id,
                        exc,
                    )
        except Exception as exc:  # pragma: no cover — DB lock hatası gibi üst düzey sorunlar
            logger.exception(
                "Unexpected error while delivering placement %s: %s",
                placement_id,
                exc,
            )
            failed += 1

    return {"picked": len(due_ids), "sent": sent, "failed": failed}


@shared_task(**_CRITICAL_TASK_KWARGS)
def delete_expired_ads(self):
    """Süresi dolan placement'ları tespit eder ve her biri için settle task'ı fırlatır.

    İmza korunur — mevcut Celery beat zamanlaması dokunulmaz. İç mantık
    artık dispatcher niteliğindedir; asıl billing + silme işi
    `_settle_placement` sub-task'ında yürütülür ve her biri bağımsız
    idempotent bir transaction'dır.
    """
    now = timezone.now()

    # DB-side filter: status='sent', henüz faturalanmamış, süresi dolmuş.
    # sent_at + delete_after_hours <= now koşulunu uygulamak için
    # ExpressionWrapper kullanmak yerine Python tarafında chunklıyoruz;
    # delete_after_hours değerleri IntegerField olduğundan DB'de interval
    # aritmetiği taşınabilir değil.
    candidates = AdPlacement.objects.filter(
        status=AdPlacement.Status.SENT,
        billed_at__isnull=True,
        sent_at__isnull=False,
    ).values_list("id", "sent_at", "delete_after_hours")

    dispatched = 0
    for placement_id, sent_at, delete_after_hours in candidates:
        expiry = sent_at + timedelta(hours=delete_after_hours or 24)
        if expiry <= now:
            _settle_placement.delay(placement_id)
            dispatched += 1

    return {"dispatched": dispatched}


@shared_task(**_CRITICAL_TASK_KWARGS)
def _settle_placement(self, placement_id: int):
    """Tek bir placement için billing + silme işlemini idempotent yürüt.

    Aşama 1 (transaction içinde, row lock ile):
      - Placement'ı `select_for_update(skip_locked=True)` ile kilitle.
      - `billed_at IS NOT NULL` ise atla (idempotency guard).
      - Maliyeti hesapla, `Campaign.spent` ve `TelegramChannel.earnings`'ı
        `F()` ifadeleriyle atomik şekilde artır.
      - `billed_at = now`, `billing_status = billed|skipped` set et.
    Aşama 2 (transaction dışında):
      - Telegram'dan mesajı sil. Başarısızlık zararsızdır — billing
        zaten commit edilmiş; bir sonraki koşuda deletion yeniden denenir.
    """
    from ads.telegram_client import TelegramAdSender

    settlement_info = None

    with transaction.atomic():
        placement = (
            AdPlacement.objects.select_for_update(skip_locked=True)
            .select_related("ad", "ad__campaign", "channel")
            .filter(id=placement_id)
            .first()
        )

        if placement is None:
            logger.warning("Settlement skipped: placement %s not found", placement_id)
            return {"status": "not_found"}

        # Idempotency guard — en kritik check.
        if placement.billed_at is not None:
            logger.info(
                "Settlement skipped: placement %s already billed at %s",
                placement.id,
                placement.billed_at,
            )
            return {"status": "already_billed"}

        # Sadece "sent" durumundaki placement'lar faturalanabilir.
        if placement.status != AdPlacement.Status.SENT:
            logger.info(
                "Settlement skipped: placement %s in status=%s (expected sent)",
                placement.id,
                placement.status,
            )
            return {"status": "not_sent"}

        costs = AdDeliveryService.calculate_placement_cost(placement)
        total_cost: Decimal = costs["total_cost"]
        publisher_revenue: Decimal = costs["publisher_revenue"]

        now = timezone.now()
        placement.cost = total_cost
        placement.publisher_revenue = publisher_revenue
        placement.billed_at = now
        placement.billing_status = (
            AdPlacement.BillingStatus.BILLED
            if total_cost > 0
            else AdPlacement.BillingStatus.SKIPPED
        )
        placement.save(
            update_fields=[
                "cost",
                "publisher_revenue",
                "billed_at",
                "billing_status",
            ]
        )

        # F() ile atomik artışlar — read-modify-write yerine DB-side update.
        # Bu denormalize alanlar dashboard + backward-compat için; source of
        # truth FAZ 4a itibarıyla `payments.UserBalance` oldu.
        if total_cost > 0:
            Campaign.objects.filter(id=placement.ad.campaign_id).update(
                spent=F("spent") + total_cost
            )
            TelegramChannel.objects.filter(id=placement.channel_id).update(
                total_earnings=F("total_earnings") + publisher_revenue,
                pending_earnings=F("pending_earnings") + publisher_revenue,
            )

            # Balance system entegrasyonu (FAZ 4a):
            # - Advertiser: frozen → spent (Transaction.AD_SPEND)
            # - Publisher:  balance += revenue (Transaction.AD_EARNING)
            # Payments app yoksa (ör. test izolasyonu) sessizce atla —
            # denormalize alanlar yine doğru güncellenir.
            try:
                from payments.services import credit_publisher, spend_from_frozen
                spend_from_frozen(placement, total_cost)
                credit_publisher(placement, publisher_revenue)
            except Exception as exc:
                logger.exception(
                    "Balance update failed for placement %s (denormalized fields "
                    "updated, wallet out of sync): %s",
                    placement.id, exc,
                )

        settlement_info = {
            "placement_id": placement.id,
            "chat_id": placement.channel.telegram_chat_id,
            "message_id": placement.telegram_message_id,
            "cost": str(total_cost),
        }

    # Aşama 2 — lock bırakıldıktan SONRA Telegram delete.
    # Başarısızlık billing'i etkilemez; bir sonraki `delete_expired_ads`
    # koşusu bu placement'ı artık billed_at NOT NULL gördüğü için
    # settle'a yollamaz, ancak...
    # TODO (Phase 2+): billed olup status='sent' kalan kayıtlar için ayrı
    # cleanup task'ı. Şimdilik tek-atımlık deletion yeterli.
    if settlement_info and settlement_info["message_id"]:
        sender = TelegramAdSender()
        try:
            sender.delete_message(
                chat_id=settlement_info["chat_id"],
                message_id=settlement_info["message_id"],
            )
            AdPlacement.objects.filter(id=settlement_info["placement_id"]).update(
                status=AdPlacement.Status.DELETED
            )
        except Exception as exc:
            logger.warning(
                "Telegram delete failed for placement %s (billing preserved): %s",
                settlement_info["placement_id"],
                exc,
            )

    return {"status": "billed", **(settlement_info or {})}


@shared_task
def aggregate_daily_stats():
    """Günlük istatistikleri özetle."""
    yesterday = timezone.now().date() - timezone.timedelta(days=1)

    placements = AdPlacement.objects.filter(
        scheduled_at__date=yesterday,
        status__in=["sent", "deleted"],
    ).select_related("ad__campaign", "channel")

    stats_map = {}
    for p in placements:
        key = (yesterday, p.ad.campaign_id, p.channel_id)
        if key not in stats_map:
            stats_map[key] = {
                "impressions": 0,
                "clicks": 0,
                "spent": Decimal("0"),
                "revenue": Decimal("0"),
            }
        stats_map[key]["impressions"] += p.impressions
        stats_map[key]["clicks"] += p.clicks
        stats_map[key]["spent"] += p.cost
        stats_map[key]["revenue"] += p.publisher_revenue

    for (date, campaign_id, channel_id), data in stats_map.items():
        DailyStats.objects.update_or_create(
            date=date,
            campaign_id=campaign_id,
            channel_id=channel_id,
            defaults=data,
        )


@shared_task
def check_campaign_budgets():
    """Bütçesi tükenen veya süresi dolan kampanyaları otomatik tamamla.

    Complete olurken kalan frozen budget iade edilir (FAZ 4a).
    """
    # Payments app henüz migrate edilmediyse graceful fallback.
    try:
        from payments.services import refund_unspent_campaign
    except ImportError:
        refund_unspent_campaign = None

    active_campaigns = Campaign.objects.filter(status="active")
    for campaign in active_campaigns:
        completed = False
        if campaign.is_budget_exhausted:
            campaign.status = Campaign.Status.COMPLETED
            campaign.save(update_fields=["status"])
            completed = True
        elif campaign.end_date and campaign.end_date <= timezone.now():
            campaign.status = Campaign.Status.COMPLETED
            campaign.save(update_fields=["status"])
            completed = True

        if completed and refund_unspent_campaign is not None:
            try:
                refund_unspent_campaign(campaign)
            except Exception as exc:
                logger.exception(
                    "Refund failed for completed campaign %s: %s",
                    campaign.id, exc,
                )


# ----------------------------------------------------------------------------
# Moderasyon pipeline (FAZ 2)
# ----------------------------------------------------------------------------


@shared_task
def scan_campaign_creatives(campaign_id: int):
    """Kampanyanın tüm reklam kreatiflerini moderasyon taramasından geçir.

    Akış:
      1. Her Ad için `scan_text(text_uz)` ve `scan_text(text_ru)` çağrılır
         (boş olmayanlar için). Görsel varsa `scan_image` yer tutucusu.
      2. Tüm sonuçlar `combined_result` ile birleştirilir.
      3. Severity'ye göre `campaign.moderation_status` set edilir:
           - clean / low / matched-yok → auto_approved
           - medium, high             → flagged (admin review)
           - critical                 → rejected + status=rejected, rejection_reason doldurulur
      4. Bayraklar `moderation_flags`, detay `moderation_notes` alanına
         audit amaçlı yazılır.

    Bu task advertiser campaign submit ettiğinde ve ad güncellendiğinde
    fırlatılır. Business status (`status`) otomatik `active`'e GEÇMEZ —
    admin son onayı vermek zorundadır; bu davranış korunur.
    """
    from ads.moderation import combined_result, scan_image, scan_text

    try:
        campaign = Campaign.objects.select_related("advertiser").get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning("scan_campaign_creatives: campaign %s not found", campaign_id)
        return {"status": "not_found"}

    ads = list(campaign.ads.all())
    if not ads:
        # Henüz kreatif yok — moderation_status pending kalsın, scan tetikleyicisi
        # ad create sırasında tekrar çağırılacak.
        return {"status": "no_ads"}

    results = []
    for ad in ads:
        if ad.text_uz:
            results.append(scan_text(ad.text_uz, language="uz"))
        if ad.text_ru:
            results.append(scan_text(ad.text_ru, language="ru"))
        if ad.image:
            results.append(scan_image(ad.image.url if ad.image else ""))

    combined = combined_result(results)

    update_fields = ["moderation_status", "moderation_flags", "moderation_notes"]
    campaign.moderation_flags = combined.flags
    campaign.moderation_notes = _format_moderation_notes(combined)

    if combined.severity == "critical":
        campaign.moderation_status = Campaign.ModerationStatus.REJECTED
        campaign.status = Campaign.Status.REJECTED
        campaign.rejection_reason = (
            f"Otomatik moderasyon: yasaklı içerik tespit edildi "
            f"({', '.join(combined.flags)})"
        )
        update_fields += ["status", "rejection_reason"]
    elif combined.requires_human_review or combined.flags:
        campaign.moderation_status = Campaign.ModerationStatus.FLAGGED
    else:
        campaign.moderation_status = Campaign.ModerationStatus.AUTO_APPROVED

    campaign.save(update_fields=update_fields)

    return {
        "campaign_id": campaign.id,
        "moderation_status": campaign.moderation_status,
        "severity": combined.severity,
        "flags": combined.flags,
    }


def _format_moderation_notes(result) -> str:
    """İnsan okunur özet üret — moderation_notes alanına yazılır."""
    if not result.matched_terms:
        return "Otomatik tarama: temiz."
    lines = [f"Otomatik tarama severity={result.severity}"]
    for m in result.matched_terms[:20]:  # çok uzun kalmasın
        fuzzy = " (fuzzy)" if m.fuzzy else ""
        lines.append(
            f"  - [{m.category}/{m.severity}/{m.language}] {m.pattern}{fuzzy}"
        )
    if len(result.matched_terms) > 20:
        lines.append(f"  ... +{len(result.matched_terms) - 20} daha")
    return "\n".join(lines)


# Maximum reassignment denemesi — sonsuz döngüye karşı guard.
MAX_REASSIGNMENT_ATTEMPTS = 3


@shared_task
def reassign_rejected_placement(placement_id: int):
    """Yayıncı tarafından reddedilen placement için yeni bir kanal bul.

    Akış:
      1. Orijinal placement'ı yükle; `publisher_action == REJECTED` değilse
         no-op (idempotency).
      2. `reassignment_count >= MAX_REASSIGNMENT_ATTEMPTS` ise vazgeç ve logla.
      3. `find_matching_channels`'tan reddeden kanalı çıkar, sıradaki uygun
         kanalı seç. Uygun kanal yoksa vazgeç.
      4. Yeni placement oluştur — `reassignment_count` artmış olarak.
    """
    try:
        original = (
            AdPlacement.objects.select_related("ad", "ad__campaign", "channel")
            .get(id=placement_id)
        )
    except AdPlacement.DoesNotExist:
        logger.warning(
            "reassign_rejected_placement: placement %s not found", placement_id
        )
        return {"status": "not_found"}

    if original.publisher_action != AdPlacement.PublisherAction.REJECTED:
        return {"status": "not_rejected"}

    if original.reassignment_count >= MAX_REASSIGNMENT_ATTEMPTS:
        logger.warning(
            "reassign_rejected_placement: placement %s exceeded max attempts",
            placement_id,
        )
        return {"status": "max_attempts_reached"}

    campaign = original.ad.campaign
    if campaign.status != Campaign.Status.ACTIVE:
        return {"status": "campaign_not_active"}

    # Uygun kanallar — red eden kanalı ve daha önce bu ad için reddetmiş
    # kanalları çıkar.
    candidates = AdDeliveryService.find_matching_channels(campaign)
    previously_rejected_channel_ids = set(
        AdPlacement.objects.filter(
            ad=original.ad,
            publisher_action=AdPlacement.PublisherAction.REJECTED,
        ).values_list("channel_id", flat=True)
    )
    candidates = [
        c for c in candidates
        if c.id != original.channel_id
        and c.id not in previously_rejected_channel_ids
    ]

    if not candidates:
        logger.info(
            "reassign_rejected_placement: no remaining channels for placement %s",
            placement_id,
        )
        return {"status": "no_channels"}

    # İlk uygun kanal (find_matching_channels zaten ordering uyguluyor).
    new_channel = candidates[0]

    # Yeni scheduled_at — şimdi + 30 dk; unique_together çakışmasına karşı
    # mikrosaniye farkı yeterli olmaz, placement_id temelli küçük ofset ekliyoruz.
    new_scheduled = timezone.now() + timedelta(minutes=30) + timedelta(
        seconds=placement_id % 60
    )

    new_placement = AdPlacement.objects.create(
        ad=original.ad,
        channel=new_channel,
        scheduled_at=new_scheduled,
        delete_after_hours=original.delete_after_hours,
        reassignment_count=original.reassignment_count + 1,
    )

    logger.info(
        "Reassigned placement %s → new placement %s on channel %s (attempt %s)",
        placement_id,
        new_placement.id,
        new_channel.id,
        new_placement.reassignment_count,
    )

    return {
        "status": "reassigned",
        "original_id": placement_id,
        "new_placement_id": new_placement.id,
        "new_channel_id": new_channel.id,
        "attempt": new_placement.reassignment_count,
    }


# ----------------------------------------------------------------------------


@shared_task
def update_channel_stats():
    """Kanal abone ve görüntülenme istatistiklerini güncelle."""
    from ads.telegram_client import TelegramAdSender

    channels = TelegramChannel.objects.filter(
        status="approved", is_active=True, bot_added=True
    )

    sender = TelegramAdSender()
    for channel in channels:
        try:
            info = sender.get_chat_info(channel.telegram_chat_id)
            channel.subscriber_count = info.get("member_count", channel.subscriber_count)
            channel.save(update_fields=["subscriber_count"])
        except Exception as e:
            logger.warning("Failed to update stats for channel %s: %s", channel.id, e)


# ----------------------------------------------------------------------------
# Kalite skorlama, anomaly detection, IP cluster fraud (FAZ 3)
# ----------------------------------------------------------------------------


@shared_task
def recalculate_channel_quality_scores():
    """Tüm onaylı kanallar için kalite skorunu yeniden hesapla.

    Her kanal için:
      1. `calculate_quality_score` bileşenleri hesaplar.
      2. Denormalize alanlar (`quality_score`, `engagement_rate`, ...) update.
      3. O güne ait `DailyChannelSnapshot` oluştur veya güncelle.

    Nightly beat schedule tarafından çağrılır. Büyük ölçekte bu task
    chunk'lanabilir; şu an kanal sayısı yönetilebilir seviyede.
    """
    from channels_app.models import DailyChannelSnapshot
    from channels_app.quality import calculate_quality_score

    today = timezone.now().date()
    channels = TelegramChannel.objects.filter(status="approved", is_active=True)
    updated = 0

    for channel in channels.iterator(chunk_size=200):
        components = calculate_quality_score(channel)

        # Kanalın denormalize alanlarını güncelle.
        TelegramChannel.objects.filter(id=channel.id).update(
            quality_score=components.final_score,
            engagement_rate=components.engagement_rate,
            ad_completion_rate=components.ad_completion_rate,
            avg_ctr=components.avg_ctr,
            quality_updated_at=timezone.now(),
        )

        # Snapshot — günlük tek satır, upsert.
        DailyChannelSnapshot.objects.update_or_create(
            channel=channel,
            date=today,
            defaults={
                "subscriber_count": channel.subscriber_count,
                "avg_views": channel.avg_views,
                "sent_count": components.sent_count,
                "failed_count": components.failed_count,
                "impressions": components.impressions,
                "valid_clicks": components.valid_clicks,
                "quality_score": components.final_score,
                "components": components.to_dict(),
            },
        )
        updated += 1

    return {"updated": updated}


@shared_task
def detect_subscriber_anomalies():
    """Ani subscriber artışı olan kanalları tespit et ve flag'le.

    Her onaylı kanal için bugün ve dün snapshot'ını karşılaştırır.
    Anomaly tespit edildiyse:
      - `TelegramChannel.suspicious_growth_flag = True`
      - `probation_ends_at = now + ANOMALY_PROBATION_DAYS` (probation'a geri al)
      - Bugünkü snapshot'a `suspicious_growth_flag=True` ve `growth_pct` yaz

    Snapshot yoksa (yeni kanal ilk gün), anomaly tespit edilemez — sessizce
    atlanır, bir sonraki gün karşılaştırma yapılabilir hale gelir.
    """
    from channels_app.models import DailyChannelSnapshot
    from channels_app.quality import (
        ANOMALY_PROBATION_DAYS,
        detect_growth_anomaly,
    )

    today = timezone.now().date()
    yesterday = today - timedelta(days=1)

    channels = TelegramChannel.objects.filter(status="approved", is_active=True)
    flagged = 0

    for channel in channels.iterator(chunk_size=200):
        # Bugünün snapshot'ı (en güncel subscriber_count'u içerir).
        today_snap, _ = DailyChannelSnapshot.objects.get_or_create(
            channel=channel,
            date=today,
            defaults={
                "subscriber_count": channel.subscriber_count,
                "avg_views": channel.avg_views,
                "quality_score": channel.quality_score,
            },
        )
        yesterday_snap = DailyChannelSnapshot.objects.filter(
            channel=channel, date=yesterday
        ).first()

        if not yesterday_snap:
            continue

        anomaly, pct = detect_growth_anomaly(
            yesterday_snap.subscriber_count,
            today_snap.subscriber_count,
        )

        today_snap.growth_pct = pct
        if anomaly and not channel.is_trusted_override:
            today_snap.suspicious_growth_flag = True
            today_snap.save(update_fields=["suspicious_growth_flag", "growth_pct"])

            TelegramChannel.objects.filter(id=channel.id).update(
                suspicious_growth_flag=True,
                probation_ends_at=timezone.now() + timedelta(
                    days=ANOMALY_PROBATION_DAYS
                ),
            )
            flagged += 1
            logger.warning(
                "Subscriber anomaly detected: channel=%s growth=%s%% "
                "(from %s to %s)",
                channel.id, pct,
                yesterday_snap.subscriber_count,
                today_snap.subscriber_count,
            )
        else:
            today_snap.save(update_fields=["growth_pct"])

    return {"flagged": flagged}


@shared_task
def detect_ip_cluster_fraud_task():
    """Nightly IP /24 cluster analizi — tüm onaylı kanalları tarar."""
    from analytics.fraud import detect_ip_cluster_fraud

    channels = TelegramChannel.objects.filter(status="approved", is_active=True)
    flagged = 0

    for channel in channels.iterator(chunk_size=200):
        if channel.is_trusted_override:
            continue
        result = detect_ip_cluster_fraud(channel)
        if result["flagged"] and not channel.ip_cluster_fraud_flag:
            TelegramChannel.objects.filter(id=channel.id).update(
                ip_cluster_fraud_flag=True
            )
            logger.warning(
                "IP cluster fraud: channel=%s top_subnet=%s%% (%s/%s clicks)",
                channel.id,
                result["top_subnet_pct"],
                result["top_subnet_clicks"],
                result["total_clicks"],
            )
            flagged += 1
        elif not result["flagged"] and channel.ip_cluster_fraud_flag:
            # Flag temizlensin mi? Şimdilik manuel admin kararına bırakıyoruz —
            # otomatik clear yanlış pozitifleri maskelemesin.
            pass

    return {"flagged": flagged}
