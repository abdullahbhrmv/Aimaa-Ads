# Generated manually for FAZ 2 — mevcut kampanyaları moderation pipeline'a yerleştir.
#
# UYARI: Uygulamadan önce staging üzerinde preview, ardından DB yedeği alın.
#
# Sınıflandırma:
#   - status IN ('approved','active','paused','completed') → moderation_status='auto_approved'
#   - status='rejected'                                    → moderation_status='rejected'
#   - diğer her durum                                      → moderation_status='pending'
#
# `moderated_at` ve `moderated_by` backfill edilmiyor — geçmiş kayıtlar için
# kim ne zaman modere etti bilgisi yok. Yeni kampanyalar moderasyon
# task'ından geçince bu alanlar dolar.
#
# Reverse: noop (veri kaybı riskine karşı).

from django.db import migrations


def backfill_moderation_status(apps, schema_editor):
    Campaign = apps.get_model('ads', 'Campaign')

    already_reviewed_statuses = ['approved', 'active', 'paused', 'completed']

    Campaign.objects.filter(status__in=already_reviewed_statuses).update(
        moderation_status='auto_approved'
    )
    Campaign.objects.filter(status='rejected').update(
        moderation_status='rejected'
    )
    # status='pending' ve 'draft' zaten default 'pending' ile uyumlu.


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0012_adplacement_publisher_action'),
    ]

    operations = [
        migrations.RunPython(backfill_moderation_status, reverse_noop),
    ]
