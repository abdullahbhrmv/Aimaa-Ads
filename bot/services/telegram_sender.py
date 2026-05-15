"""
Telegram Ad Sender — Celery task'lari tomonidan ishlatiladi.
Reklamlarni kanallarga jo'natadi va o'chiradi.
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

PLATFORM_BOT_USERNAME = os.getenv("PLATFORM_BOT_USERNAME", "aimaa_ads_bot")


class TelegramAdSender:
    """Telegram Bot API orqali reklama jo'natish."""

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def _request(self, method: str, data: dict) -> dict:
        """Sinxron HTTP so'rov (Celery task'lari uchun)."""
        response = httpx.post(f"{self.base_url}/{method}", json=data, timeout=30)
        result = response.json()
        if not result.get("ok"):
            raise Exception(f"Telegram API xatosi: {result}")
        return result.get("result", {})

    def send_ad(self, chat_id: int, ad, placement_id: int, channel_language: str = "uz") -> int:
        """Reklamni kanalga jo'natish, message_id qaytaradi.

        Args:
            chat_id: Telegram kanal ID
            ad: Ad model obyekti
            placement_id: AdPlacement ID
            channel_language: Kanal tili ("uz" yoki "ru")
        """
        # Inline klaviatura yaratish
        keyboard = None
        if ad.button_text and ad.button_url:
            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": ad.button_text,
                            "url": ad.button_url,
                        }
                    ],
                    [
                        {
                            "text": "📊",
                            "callback_data": f"ad_click:{placement_id}",
                        }
                    ],
                ]
            }

        # Kanal tiliga ko'ra matnni tanlash
        if channel_language == "ru" and ad.text_ru:
            text = ad.text_ru
        else:
            text = ad.text_uz

        text += f"\n\n<i>Reklama | @{PLATFORM_BOT_USERNAME}</i>"

        if ad.ad_type == "image" and ad.image:
            result = self._request("sendPhoto", {
                "chat_id": chat_id,
                "photo": ad.image.url,
                "caption": text,
                "parse_mode": "HTML",
                "reply_markup": keyboard,
            })
        elif ad.ad_type == "video" and ad.video:
            result = self._request("sendVideo", {
                "chat_id": chat_id,
                "video": ad.video.url,
                "caption": text,
                "parse_mode": "HTML",
                "reply_markup": keyboard,
            })
        else:
            result = self._request("sendMessage", {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": keyboard,
            })

        return result.get("message_id")

    def delete_message(self, chat_id: int, message_id: int) -> bool:
        """Muddati tugagan reklamni o'chirish."""
        try:
            self._request("deleteMessage", {
                "chat_id": chat_id,
                "message_id": message_id,
            })
            return True
        except Exception as e:
            logger.warning("Xabarni o'chirishda xatolik: chat=%s msg=%s: %s", chat_id, message_id, e)
            return False

    def get_chat_info(self, chat_id: int) -> dict:
        """Kanal ma'lumotlarini olish."""
        result = self._request("getChat", {"chat_id": chat_id})
        member_count = self._request(
            "getChatMemberCount", {"chat_id": chat_id}
        )
        result["member_count"] = member_count
        return result
