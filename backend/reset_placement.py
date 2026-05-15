#!/usr/bin/env python
"""
Placement'ı sıfırla - yeni format testleri için
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from ads.models import AdPlacement
from django.utils import timezone

print("🔄 Placement sıfırlanıyor...")
print("=" * 50)

# Placement #2'yi al
try:
    placement = AdPlacement.objects.get(id=2)

    print(f"📍 Placement #{placement.id}")
    print(f"   Eski status: {placement.status}")
    print(f"   Eski sent_at: {placement.sent_at}")

    # Sıfırla
    placement.status = 'scheduled'
    placement.sent_at = None
    placement.scheduled_at = timezone.now()  # Hemen gönder
    placement.telegram_message_id = None
    placement.save()

    print(f"\n✅ YENİ DURUM:")
    print(f"   Status: {placement.status}")
    print(f"   Sent: {placement.sent_at}")
    print(f"   Scheduled: {placement.scheduled_at}")
    print(f"\n🎉 Placement sıfırlandı! Artık yeni formatla tekrar gönderilebilir.")

except AdPlacement.DoesNotExist:
    print("❌ Placement #2 bulunamadı!")
