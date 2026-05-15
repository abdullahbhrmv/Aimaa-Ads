#!/usr/bin/env python
"""
Bot kanalının ID'sini al
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

import httpx
from django.conf import settings

def get_channel_id(channel_username):
    """Kanal username'inden ID al (@AimaaAds → -1001234567890)"""
    token = settings.TELEGRAM_BOT_TOKEN

    # @'siz kullan
    if channel_username.startswith('@'):
        channel_username = channel_username[1:]

    url = f"https://api.telegram.org/bot{token}/getChat"
    response = httpx.get(url, params={"chat_id": f"@{channel_username}"})
    result = response.json()

    if result.get("ok"):
        chat = result["result"]
        print(f"✅ Kanal bulundu!")
        print(f"   İsim: {chat.get('title')}")
        print(f"   Username: @{chat.get('username', 'yok')}")
        print(f"   ID: {chat['id']}")
        print(f"\n📝 Bu ID'yi .env dosyasına ekle:")
        print(f"   ADS_CHANNEL_ID={chat['id']}")
        return chat['id']
    else:
        print(f"❌ Hata: {result.get('description')}")
        print(f"\n💡 Kontrol et:")
        print(f"   - Bot kanala admin olarak eklendi mi?")
        print(f"   - Username doğru mu? (@AimaaAds)")
        return None

if __name__ == "__main__":
    print("🔍 Bot kanalı ID'sini bulma\n")
    print("Kanal username'ini gir (örn: @AimaaAds veya AimaaAds):")
    username = input("> ").strip()

    get_channel_id(username)
