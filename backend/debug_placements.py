#!/usr/bin/env python
"""
Placement durumlarını kontrol et
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from ads.models import Campaign, Ad, AdPlacement
from django.utils import timezone

print("🔍 Kampanya ve Placement Durumları")
print("=" * 60)

# Tüm kampanyaları listele
campaigns = Campaign.objects.all()
print(f"\n📊 Toplam {campaigns.count()} kampanya bulundu:\n")

for c in campaigns:
    print(f"ID: {c.id} | {c.name}")
    print(f"   Status: {c.status}")
    print(f"   Advertiser: {c.advertiser.username}")
    print(f"   Budget: {c.budget} UZS / Spent: {c.spent} UZS")
    print(f"   Start: {c.start_date}")
    print(f"   End: {c.end_date}")

    # Reklamları
    ads = c.ads.all()
    print(f"   📢 {ads.count()} reklam:")
    for ad in ads:
        print(f"      - Ad #{ad.id}: {ad.ad_type} | Active: {ad.is_active}")

    # Placement'ları
    placements = AdPlacement.objects.filter(ad__campaign=c)
    print(f"   📍 {placements.count()} placement:")
    for p in placements:
        print(f"      - Placement #{p.id}")
        print(f"        Status: {p.status}")
        print(f"        Ad: #{p.ad.id}")
        print(f"        Channel: {p.channel.title}")
        print(f"        Scheduled: {p.scheduled_at}")
        print(f"        Sent: {p.sent_at}")
        now = timezone.now()
        if p.scheduled_at:
            if p.scheduled_at <= now:
                print(f"        ⏰ Zamanı gelmiş! (şimdi: {now})")
            else:
                print(f"        ⏳ Henüz zamanı gelmemiş (şimdi: {now})")

    print()

# Şimdi deliver_scheduled_ads'ın ne arayacağını göster
print("=" * 60)
print("🎯 deliver_scheduled_ads şunu arayacak:")
print("   - Status: PENDING")
print("   - Campaign status: ACTIVE")
print("   - scheduled_at <= ŞİMDİ")
print()

pending = AdPlacement.objects.filter(
    status='pending',
    ad__campaign__status='active',
    scheduled_at__lte=timezone.now()
)
print(f"✅ Gönderilmeye hazır: {pending.count()} placement")
for p in pending:
    print(f"   - Placement #{p.id} → {p.channel.title}")
