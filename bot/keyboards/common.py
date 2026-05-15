from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        ]
    ])


def main_menu_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanal qo'shish", callback_data="menu:register")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="menu:stats")],
            [InlineKeyboardButton(text="💰 Balans", callback_data="menu:balance")],
            [InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="menu:settings")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Добавить канал", callback_data="menu:register")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
            [InlineKeyboardButton(text="💰 Баланс", callback_data="menu:balance")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")],
        ])
