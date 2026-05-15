#!/usr/bin/env python
"""
Bot'a forward edilen mesajdan kanal ID'sini al
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

import httpx
from django.conf import settings

token = settings.TELEGRAM_BOT_TOKEN
url = f'https://api.telegram.org/bot{token}/getUpdates'

print("🔍 Bot'a gelen son mesajları kontrol ediyorum...\n")

response = httpx.get(url, params={'offset': -10, 'limit': 10})
result = response.json()

if not result.get('ok'):
    print(f"❌ Hata: {result.get('description')}")
    exit(1)

updates = result.get('result', [])
if not updates:
    print("❌ Hiç mesaj bulunamadı!")
    print("💡 Kanaldan bot'a bir mesaj forward ettiğinden emin ol.")
    exit(1)

print(f"📨 {len(updates)} mesaj bulundu. Forward edilen kanalları arıyorum...\n")

found = False
for update in reversed(updates):  # En yeniden başla
    if 'message' in update:
        message = update['message']

        # Forward edilmiş kanal mesajı mı?
        if 'forward_from_chat' in message:
            chat = message['forward_from_chat']

            print(f"✅ Kanal Bulundu!")
            print(f"=" * 60)
            print(f"   İsim: {chat.get('title', 'Bilinmiyor')}")
            print(f"   Tip: {chat.get('type', 'Bilinmiyor')}")
            print(f"   ID: {chat['id']}")
            print(f"=" * 60)
            print(f"\n📝 Bu ID'yi backend/.env dosyasına ekle:")
            print(f"   ADS_CHANNEL_ID={chat['id']}")
            print()
            found = True
            break

if not found:
    print("❌ Forward edilmiş kanal mesajı bulunamadı!")
    print("\n💡 Şunu dene:")
    print("   1. Kanalından bot'a bir mesaj forward et")
    print("   2. Bu scripti tekrar çalıştır")
