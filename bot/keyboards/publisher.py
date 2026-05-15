from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from services.api_client import APIClient


async def category_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    """API'den kategorileri çekip keyboard oluştur."""
    api = APIClient()
    categories = await api.get_categories()

    buttons = []
    for cat in categories:
        name = cat["name_uz"] if lang == "uz" else cat["name_ru"]
        buttons.append([
            InlineKeyboardButton(
                text=f"{cat['icon']} {name}",
                callback_data=f"cat:{cat['id']}",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def channel_settings_keyboard(channel_id: int, lang: str = "uz") -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⏰ Reklama vaqtini sozlash",
                callback_data=f"ch_time:{channel_id}"
            )],
            [InlineKeyboardButton(
                text="📊 Kunlik reklama limiti",
                callback_data=f"ch_limit:{channel_id}"
            )],
            [InlineKeyboardButton(
                text="💰 Minimal CPM",
                callback_data=f"ch_cpm:{channel_id}"
            )],
            [InlineKeyboardButton(
                text="⏸ Reklamani to'xtatish",
                callback_data=f"ch_pause:{channel_id}"
            )],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⏰ Настроить время рекламы",
                callback_data=f"ch_time:{channel_id}"
            )],
            [InlineKeyboardButton(
                text="📊 Лимит рекламы в день",
                callback_data=f"ch_limit:{channel_id}"
            )],
            [InlineKeyboardButton(
                text="💰 Минимальный CPM",
                callback_data=f"ch_cpm:{channel_id}"
            )],
            [InlineKeyboardButton(
                text="⏸ Приостановить рекламу",
                callback_data=f"ch_pause:{channel_id}"
            )],
        ])


def channels_list_keyboard(channels: list, lang: str = "uz") -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {ch['title']}",
                callback_data=f"ch_detail:{ch['id']}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
