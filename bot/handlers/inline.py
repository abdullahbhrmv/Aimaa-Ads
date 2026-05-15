"""Reklam etkileşim takibi — inline buton tıklamaları."""

from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.api_client import APIClient

router = Router()


@router.callback_query(F.data.startswith("ad_click:"))
async def on_ad_click(callback: CallbackQuery):
    """Reklam butonuna tıklama olayını kaydet."""
    placement_id = callback.data.split(":")[1]

    api = APIClient()
    await api.track_event(
        placement_id=int(placement_id),
        event_type="button_click",
        telegram_user_id=callback.from_user.id,
    )

    await callback.answer()
