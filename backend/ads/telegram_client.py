"""
Telegram Ad Sender — Backend Celery task'ları tarafından kullanılır.
Bot servisinden bağımsız, doğrudan Telegram Bot API çağrıları yapar.
"""

import json
import logging
from urllib.parse import quote

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


def build_tracking_url(placement_id: int, target_url: str) -> str:
    """Button URL'i fraud-tracking redirect endpoint'ine çevir (FAZ 3).

    `settings.TRACKING_BASE_URL` set edilmemişse veya target_url boşsa,
    orijinal URL döner — geriye dönük uyumluluk ve dev environment.
    """
    from analytics.fraud import sign_tracking_token

    if not target_url:
        return target_url

    base = getattr(settings, "TRACKING_BASE_URL", "").rstrip("/")
    if not base:
        return target_url

    token = sign_tracking_token(placement_id, target_url)
    encoded = quote(target_url, safe="")
    return f"{base}/api/analytics/track/c/{placement_id}/{token}/?u={encoded}"


class TelegramAdSender:
    """Telegram Bot API aracılığıyla reklam gönderimi."""

    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def _request(self, method: str, data: dict) -> dict:
        """Senkron HTTP isteği (Celery task'ları için)."""
        response = httpx.post(
            f"{self.base_url}/{method}",
            json=data,
            timeout=30,
        )
        result = response.json()
        if not result.get("ok"):
            raise Exception(f"Telegram API error: {result}")
        return result.get("result", {})

    def send_ad(self, chat_id: int, ad, placement_id: int, channel_language: str = "uz") -> int:
        """
        Reklamı kanala gönder (forward yöntemiyle).
        1. Önce bot'un kanalına gönder
        2. Oradan target kanala forward et
        → Profesyonel görünüm: "Forwarded from AimaaAds Posts"
        """
        # Kanal diline göre metin seç
        text = ad.text_ru if channel_language == "ru" and ad.text_ru else ad.text_uz

        text += f"\n\n📍 <i>Reklama</i>"

        # Inline keyboard oluştur - CTA butonu + Reklamaveren Hakkında
        keyboard_buttons = []

        # Ana CTA butonu (varsa) — FAZ 3: URL tracking redirect'inden geçer.
        if ad.button_text and ad.button_url:
            tracked_url = build_tracking_url(placement_id, ad.button_url)
            keyboard_buttons.append([{"text": f"▶️ {ad.button_text}", "url": tracked_url}])

        # Reklamaveren Hakkında butonu (advertiser'ın website'i varsa)
        advertiser = ad.campaign.advertiser
        if advertiser.website:
            advertiser_label = "Reklamaveren Hakkında" if channel_language == "uz" else "О рекламодателе"
            keyboard_buttons.append([{"text": f"ℹ️ {advertiser_label}", "url": advertiser.website}])

        keyboard = {"inline_keyboard": keyboard_buttons} if keyboard_buttons else None

        # ADIM 1: Bot'un kanalına gönder
        ads_channel_id = settings.ADS_CHANNEL_ID
        if not ads_channel_id:
            raise Exception("ADS_CHANNEL_ID not configured in settings")

        params = {
            "chat_id": ads_channel_id,
            "parse_mode": "HTML",
        }
        if keyboard:
            params["reply_markup"] = keyboard

        # Medya tipine göre gönder
        if ad.ad_type == "image" and ad.image:
            # Image'ı file olarak gönder (URL değil, çünkü relative path Telegram kabul etmez)
            with open(ad.image.path, 'rb') as photo_file:
                files = {'photo': photo_file}
                # reply_markup'ı JSON string'e çevir (multipart/form-data için)
                data_params = {
                    'chat_id': params['chat_id'],
                    'parse_mode': params['parse_mode'],
                    'caption': text,
                }
                if keyboard:
                    data_params['reply_markup'] = json.dumps(keyboard)

                bot_message = httpx.post(
                    f"{self.base_url}/sendPhoto",
                    data=data_params,
                    files=files,
                    timeout=30,
                ).json()
                if not bot_message.get("ok"):
                    raise Exception(f"Telegram API error: {bot_message}")
                bot_message = bot_message.get("result", {})
        elif ad.ad_type == "video" and ad.video:
            # Video'yu file olarak gönder
            with open(ad.video.path, 'rb') as video_file:
                files = {'video': video_file}
                # reply_markup'ı JSON string'e çevir (multipart/form-data için)
                data_params = {
                    'chat_id': params['chat_id'],
                    'parse_mode': params['parse_mode'],
                    'caption': text,
                }
                if keyboard:
                    data_params['reply_markup'] = json.dumps(keyboard)

                bot_message = httpx.post(
                    f"{self.base_url}/sendVideo",
                    data=data_params,
                    files=files,
                    timeout=30,
                ).json()
                if not bot_message.get("ok"):
                    raise Exception(f"Telegram API error: {bot_message}")
                bot_message = bot_message.get("result", {})
        else:
            params["text"] = text
            bot_message = self._request("sendMessage", params)

        bot_message_id = bot_message.get("message_id")
        logger.info(f"Ad sent to bot channel: message_id={bot_message_id}")

        # ADIM 2: Bot kanalından target kanala forward et
        forward_result = self._request("forwardMessage", {
            "chat_id": chat_id,  # Target kanal
            "from_chat_id": ads_channel_id,  # Bot'un kanalı
            "message_id": bot_message_id,
        })

        forwarded_message_id = forward_result.get("message_id")
        logger.info(f"Ad forwarded to channel {chat_id}: message_id={forwarded_message_id}")

        return forwarded_message_id

    def delete_message(self, chat_id: int, message_id: int) -> bool:
        """Süresi dolan reklamı sil."""
        try:
            self._request("deleteMessage", {
                "chat_id": chat_id,
                "message_id": message_id,
            })
            return True
        except Exception:
            logger.warning("Failed to delete message %s from chat %s", message_id, chat_id)
            return False

    def get_chat_info(self, chat_id: int) -> dict:
        """Kanal bilgilerini çek."""
        result = self._request("getChat", {"chat_id": chat_id})
        member_count = self._request("getChatMemberCount", {"chat_id": chat_id})
        result["member_count"] = member_count
        return result
