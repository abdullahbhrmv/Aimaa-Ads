"""
API Client — Bot ile Django backend arasinda aloqa.
Shared httpx.AsyncClient ishlatadi (har so'rovda yangi client yaratmaydi).
"""

import os
import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

# Shared async client — modul darajasida
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Shared AsyncClient qaytaradi, agar yo'q bo'lsa yaratadi."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client():
    """Bot to'xtaganda clientni yopadi."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


class APIClient:
    """Django REST API bilan bog'lanuvchi HTTP client."""

    def __init__(self):
        self.base_url = os.getenv("BACKEND_API", "http://localhost:8000/api")
        self.bot_secret = os.getenv("BOT_SECRET", "bot-secret-key")
        self.headers = {
            "X-Bot-Secret": self.bot_secret,
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        client = _get_client()
        try:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                **kwargs,
            )
            if response.status_code >= 400:
                logger.warning("API %s %s → %s: %s", method, path, response.status_code, response.text[:200])
                return {"success": False, "error": response.text}
            return {"success": True, **response.json()}
        except httpx.HTTPError as e:
            logger.error("API so'rov xatosi: %s %s → %s", method, path, e)
            return {"success": False, "error": str(e)}

    # ─── Auth ───

    async def register_telegram_user(
        self, telegram_id: int, username: str, language: str
    ) -> dict:
        return await self._request("POST", "/auth/telegram-register/", json={
            "telegram_id": telegram_id,
            "username": username,
            "language": language,
        })

    # ─── Kanallar ───

    async def get_categories(self) -> list:
        result = await self._request("GET", "/channels/categories/")
        return result.get("results", []) if result.get("success") else []

    async def register_channel(
        self,
        owner_telegram_id: int,
        telegram_chat_id: int,
        title: str,
        username: str,
        description: str,
        subscriber_count: int,
        category_id: int,
        language: str,
    ) -> dict:
        return await self._request("POST", "/channels/", json={
            "owner_telegram_id": owner_telegram_id,
            "telegram_chat_id": telegram_chat_id,
            "title": title,
            "username": username,
            "description": description,
            "subscriber_count": subscriber_count,
            "category": category_id,
            "language": language,
        })

    async def get_user_channels(self, telegram_id: int) -> list:
        result = await self._request(
            "GET", f"/channels/?owner_telegram_id={telegram_id}"
        )
        return result.get("results", []) if result.get("success") else []

    # ─── Analitik ───

    async def track_event(
        self,
        placement_id: int,
        event_type: str,
        telegram_user_id: int | None = None,
    ) -> dict:
        return await self._request("POST", "/analytics/track/", json={
            "placement_id": placement_id,
            "event_type": event_type,
            "telegram_user_id": telegram_user_id,
        })

    # ─── Publisher Stats ───

    async def get_publisher_stats(self, telegram_id: int) -> dict:
        result = await self._request(
            "GET", f"/dashboard/stats/?telegram_id={telegram_id}"
        )
        return result if result.get("success") else {}

    async def get_publisher_balance(self, telegram_id: int) -> dict:
        result = await self._request(
            "GET", f"/channels/balance/?telegram_id={telegram_id}"
        )
        return result if result.get("success") else {}
