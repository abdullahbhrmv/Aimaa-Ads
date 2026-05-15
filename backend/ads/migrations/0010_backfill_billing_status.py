# Generated manually for FAZ 1 — mevcut AdPlacement kayıtlarının billing durumunu doldurur.
#
# UYARI: Bu migration idempotent değildir ve mevcut veriyi mali olarak sınıflandırır.
# Uygulamadan önce bir DB yedeği alın ve staging üzerinde önizleyin.
#
# Sınıflandırma mantığı:
#   - status='deleted' AND cost > 0        → billing_status='billed', billed_at = sent_at + delete_after_hours
#   - status='deleted' AND cost = 0        → billing_status='skipped', billed_at = COALESCE(sent_at, created_at)
#   - diğer her durum                      → billing_status='pending', billed_at = NULL
#
# `billed_at` için tam bir zaman damgası geçmişte yoktur; `sent_at + delete_after_hours`
# yaklaşık bir üst sınırdır. Kritik olan alan `billing_status` ile `billed_at IS NOT NULL`
# koşulunun doğru olmasıdır — böylece yeni `_settle_placement` task'ı geçmiş kayıtları
# ikinci kez faturalamaz.
#
# Reverse: noop. Geri alma, mali alanları yok edeceğinden kasıtlı olarak boş bırakıldı.

from datetime import timedelta

from django.db import migrations


def backfill_billing_status(apps, schema_editor):
    AdPlacement = apps.get_model('ads', 'AdPlacement')

    # Faturalanmış: silinmiş ve cost > 0
    for p in AdPlacement.objects.filter(status='deleted').iterator(chunk_size=500):
        if p.cost and p.cost > 0:
            reference_time = p.sent_at or p.created_at
            p.billed_at = reference_time + timedelta(hours=p.delete_after_hours or 24)
            p.billing_status = 'billed'
        else:
            p.billed_at = p.sent_at or p.created_at
            p.billing_status = 'skipped'
        p.save(update_fields=['billed_at', 'billing_status'])

    # Diğer tüm kayıtlar zaten default olarak billing_status='pending', billed_at=NULL durumunda.


def reverse_noop(apps, schema_editor):
    # Geriye dönüş mali durumu yok edeceğinden kasıtlı olarak boştur.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0009_adplacement_billing_fields'),
    ]

    operations = [
        migrations.RunPython(backfill_billing_status, reverse_noop),
    ]
