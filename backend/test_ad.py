#!/usr/bin/env python
"""
Reklam gönderimini direkt test et (Celery olmadan)
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from ads.tasks import deliver_scheduled_ads

print("🚀 Reklam gönderimi başlıyor...")
print("=" * 50)

# Task'ı direkt çağır (Celery olmadan)
result = deliver_scheduled_ads()

print("=" * 50)
print("✅ Tamamlandı!")
print(f"Sonuç: {result}")
