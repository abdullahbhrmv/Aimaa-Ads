"""
Pixel attribution Celery task'ları (FAZ 5 Adım 2).

- `attribute_pending_conversions`: 5 dakikada bir çalışır, henüz
  attribute edilmemiş (attribution_attempted_at IS NULL) ConversionEvent'leri
  1000'erlik batch'lerle işler.

- 30 günden eski unattributed event'ler "expired" sayılır: sessizce
  `attribution_attempted_at=now()` set edilir (kayıp kabul edilir).
  Bu sayede sonsuz retry yok, DB indexleri eski satırları taramaz.

- `select_for_update(skip_locked=True)` ile iki worker aynı event'i
  almayınca race yok. `Conversion.event` OneToOne DB katmanında ikinci
  savunma hattı.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from pixel.attribution import attribute_event
from pixel.models import ConversionEvent

logger = logging.getLogger(__name__)


# Her task run'ında kaç event işlenir. Büyütmek worker memory'yi etkiler.
BATCH_SIZE = 1000

# Unattributed event'ler bu süreyi geçtiyse "expired" olarak işaretlenir,
# bir daha attribution denenmez. Kayıp kabul.
UNATTRIBUTED_MAX_AGE_DAYS = 30


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    task_reject_on_worker_lost=True,
    soft_time_limit=240,
    time_limit=300,
)
def attribute_pending_conversions(self):
    """Attribute edilmemiş ConversionEvent'leri batch olarak işler.

    Dönüş payload'ı kısa rapor:
      - picked: bu run'da ele alınan event sayısı
      - attributed: Conversion üretilen sayı
      - unmatched: attempted ama match bulunamayan sayı
      - expired_marked: 30+ gün eski olup "expired" işaretlenen sayı
    """
    now = timezone.now()
    cutoff = now - timedelta(days=UNATTRIBUTED_MAX_AGE_DAYS)

    # Önce 30+ gün eski unattributed event'leri kapat (tek query).
    expired_marked = ConversionEvent.objects.filter(
        attribution_attempted_at__isnull=True,
        created_at__lt=cutoff,
    ).update(attribution_attempted_at=now)

    # Sıradaki batch — eski ama cutoff içinde.
    due_ids = list(
        ConversionEvent.objects.filter(
            attribution_attempted_at__isnull=True,
            created_at__gte=cutoff,
        )
        .order_by("created_at")
        .values_list("id", flat=True)[:BATCH_SIZE]
    )

    attributed = 0
    unmatched = 0

    for event_id in due_ids:
        try:
            with transaction.atomic():
                event = (
                    ConversionEvent.objects
                    .select_for_update(skip_locked=True)
                    .select_related("pixel")
                    .filter(id=event_id, attribution_attempted_at__isnull=True)
                    .first()
                )
                if event is None:
                    # Başka worker aldı ya da bu arada işaretlendi.
                    continue
                conversion = attribute_event(event)
                if conversion is not None:
                    attributed += 1
                else:
                    unmatched += 1
        except Exception as exc:  # pragma: no cover — yukarı exception kanalı
            logger.exception(
                "Attribution failed for event %s: %s", event_id, exc,
            )

    return {
        "picked": len(due_ids),
        "attributed": attributed,
        "unmatched": unmatched,
        "expired_marked": expired_marked,
    }
