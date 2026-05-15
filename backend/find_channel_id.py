#!/usr/bin/env python
"""
Private kanal ID'sini bul - Kanala test mesajı göndererek
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

import httpx
from django.conf import settings

def send_test_message(chat_id):
    """Kanala test mesajı gönder ve ID'yi doğrula"""
    token = settings.TELEGRAM_BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    response = httpx.post(url, json={
        "chat_id": chat_id,
        "text": "🎉 AimaaAds Bot Kanalı Hazır!\n\nBu kanal reklam postlarını hazırlamak için kullanılacak.",
    })

    result = response.json()

    if result.get("ok"):
        message = result["result"]
        chat = message["chat"]
        print(f"✅ Başarılı! Test mesajı gönderildi.")
        print(f"\n📋 Kanal Bilgileri:")
        print(f"   İsim: {chat.get('title')}")
        print(f"   Tip: {chat.get('type')}")
        print(f"   ID: {chat['id']}")
        print(f"\n📝 Bu ID'yi .env dosyasına ekle:")
        print(f"   ADS_CHANNEL_ID={chat['id']}")
        return chat['id']
    else:
        error = result.get('description', 'Bilinmeyen hata')
        print(f"❌ Hata: {error}")

        if "bot was kicked" in error or "not found" in error:
            print(f"\n💡 Çözüm:")
            print(f"   1. Bot'u kanala admin olarak ekledin mi?")
            print(f"   2. Bot'a 'Post Messages' yetkisi verdin mi?")
        elif "chat not found" in error:
            print(f"\n💡 ID yanlış olabilir. Doğru formatta gir:")
            print(f"   Örnek: -1001234567890")

        return None

if __name__ == "__main__":
    print("🔍 Private Kanal ID'sini Bulma\n")
    print("Kanal ID'sini gir (bot kanalda admin olmalı):")
    print("Örnek: -1001234567890 veya -100...")
    print()
    chat_id = input("> ").strip()

    # Sayıya çevir
    try:
        chat_id = int(chat_id)
        send_test_message(chat_id)
    except ValueError:
        print("❌ Geçersiz ID formatı! Sayı olmalı (örn: -1001234567890)")
