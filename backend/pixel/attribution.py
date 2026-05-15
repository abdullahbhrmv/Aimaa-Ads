"""
Conversion attribution motoru (FAZ 5 Adım 2).

`attribute_event(event)` tek bir ConversionEvent'i aşağıdaki **deterministik**
öncelik sırasıyla eşleştirmeye çalışır:

  1. `click_id` — event.click_id set ise, ClickEvent PK üzerinden lookup.
     Window içindeyse eşleşme, değilse fallback'e düşer.
  2. `utm_campaign` — slug formatı `<campaign_id>-<slug>`; en son window içi
     ClickEvent seçilir (last-touch).
  3. **(FAZ 5.5)** `em_hash` cross-device — bu sürümde BİLİNÇLİ OLARAK atlanır.

İlk eşleşen kazanır, fallback başka stratejiye geçmez. `touch_method` enum
hangi stratejinin tuttuğunu kaydeder — raporlar bundan faydalanır.

Attribution window: `PixelInstallation.click_window_days` (default 7).
Event'in kendi `created_at`'inden geriye doğru.

Her çağrı sonunda `event.attribution_attempted_at = now()` set edilir —
sonsuz retry döngüsüne girmeyelim.

Race:
- `Conversion` model'inde `event` OneToOneField. Aynı event için iki worker
  yarışırsa ikincisinin `IntegrityError` alması normal; mevcut Conversion
  döndürülür.
- Celery task katmanı `select_for_update(skip_locked=True)` ile olasılığı
  baştan düşürüyor; bu burada ikinci savunma hattı.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from analytics.models import ClickEvent
from pixel.models import Conversion, ConversionEvent

logger = logging.getLogger(__name__)


def _parse_utm_campaign_id(utm_campaign: str) -> int | None:
    """`<campaign_id>-<slug>` → campaign_id. Parse edemezse None."""
    if not utm_campaign:
        return None
    head = utm_campaign.split("-", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def _delay_seconds(event: ConversionEvent, click: ClickEvent) -> int:
    return max(0, int((event.created_at - click.created_at).total_seconds()))


def _mark_attempted(event: ConversionEvent) -> None:
    event.attribution_attempted_at = timezone.now()
    event.save(update_fields=["attribution_attempted_at"])


def attribute_event(event: ConversionEvent) -> Conversion | None:
    """Bir ConversionEvent için attribution dener. Her koşulda
    `attribution_attempted_at` set eder."""

    pixel = event.pixel
    # Sadece attribution_events listesindeki event'ler Conversion üretir.
    # PageView gibi "non-outcome" event'ler için no-op.
    if event.event_name not in (pixel.attribution_events or []):
        _mark_attempted(event)
        return None

    window_days = pixel.click_window_days or 7
    window_start = event.created_at - timedelta(days=window_days)

    # --- 1. click_id — deterministic ---
    if event.click_id:
        try:
            click = ClickEvent.objects.select_related(
                "placement", "placement__ad", "placement__ad__campaign"
            ).get(id=event.click_id)
            if click.created_at >= window_start and click.created_at <= event.created_at:
                conv = _create_conversion(
                    event=event,
                    click=click,
                    touch_method=Conversion.TouchMethod.CLICK_ID,
                )
                _mark_attempted(event)
                return conv
        except ClickEvent.DoesNotExist:
            pass

    # --- 2. utm_campaign — last-touch within window ---
    campaign_id = _parse_utm_campaign_id(event.utm_campaign)
    if campaign_id is not None:
        latest = (
            ClickEvent.objects
            .filter(
                placement__ad__campaign_id=campaign_id,
                created_at__gte=window_start,
                created_at__lte=event.created_at,
            )
            .select_related("placement", "placement__ad", "placement__ad__campaign")
            .order_by("-created_at")
            .first()
        )
        if latest is not None:
            conv = _create_conversion(
                event=event,
                click=latest,
                touch_method=Conversion.TouchMethod.UTM,
            )
            _mark_attempted(event)
            return conv

    # --- 3. Advanced matching — FAZ 5.5 ---
    # `em_hash` lookup burada yapılacak. Şimdi skip.

    _mark_attempted(event)
    return None


def _create_conversion(
    event: ConversionEvent,
    click: ClickEvent,
    touch_method: str,
) -> Conversion:
    """Event + click eşleşmesinden Conversion yarat. Idempotent — aynı event
    için ikinci çağrı OneToOne constraint'i tetiklerse mevcut kayıt döner."""

    placement = click.placement
    campaign = placement.ad.campaign if placement and placement.ad else None

    try:
        with transaction.atomic():
            return Conversion.objects.create(
                event=event,
                campaign=campaign,
                placement=placement,
                click_event=click,
                attribution_type=Conversion.AttributionType.CLICK,
                touch_method=touch_method,
                attribution_delay_seconds=_delay_seconds(event, click),
                attributed_value=event.value or Decimal("0"),
                currency=event.currency or "UZS",
            )
    except IntegrityError:
        # Race: başka worker aynı event için Conversion yaratmış.
        logger.info(
            "Conversion race on event=%s — returning existing", event.id,
        )
        return Conversion.objects.get(event=event)
