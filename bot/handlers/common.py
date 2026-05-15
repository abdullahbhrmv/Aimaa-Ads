"""Umumiy komandalar: /start, /help, /language + asosiy menyu callback'lari."""

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.common import language_keyboard, main_menu_keyboard
from services.api_client import APIClient
from services.i18n import t

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Botni ishga tushirish — til tanlash bilan boshlash."""
    await message.answer(
        t("choose_language"),
        reply_markup=language_keyboard(),
    )


@router.callback_query(F.data.startswith("lang:"))
async def on_language_select(callback: CallbackQuery, state: FSMContext):
    """Til tanlash callback'i."""
    lang = callback.data.split(":")[1]
    await state.update_data(language=lang)

    api = APIClient()
    await api.register_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username or "",
        language=lang,
    )

    await callback.message.edit_text(
        t("welcome", lang),
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "uz")
    await message.answer(t("help", lang))


@router.message(Command("language"))
async def cmd_language(message: Message):
    await message.answer(
        t("choose_language"),
        reply_markup=language_keyboard(),
    )


# ─── Asosiy menyu callback'lari ───


@router.callback_query(F.data == "menu:register")
async def on_menu_register(callback: CallbackQuery, state: FSMContext):
    """Asosiy menyudan 'Kanal qo'shish' bosilganda."""
    from handlers.publisher import cmd_register
    await callback.answer()
    await cmd_register(callback.message, state)


@router.callback_query(F.data == "menu:stats")
async def on_menu_stats(callback: CallbackQuery, state: FSMContext):
    """Asosiy menyudan 'Statistika' bosilganda."""
    from handlers.publisher import cmd_stats
    await callback.answer()
    # callback.message is a Message from bot, so we need from_user from callback
    data = await state.get_data()
    lang = data.get("language", "uz")

    api = APIClient()
    stats = await api.get_publisher_stats(callback.from_user.id)

    text = t("stats_title", lang,
        total_channels=stats.get("total_channels", 0),
        total_impressions=f"{stats.get('total_impressions', 0):,}",
        total_clicks=f"{stats.get('total_clicks', 0):,}",
        total_earnings=f"{stats.get('total_earnings', 0):,.0f}",
        balance=f"{stats.get('balance', 0):,.0f}",
    )
    await callback.message.answer(text)


@router.callback_query(F.data == "menu:balance")
async def on_menu_balance(callback: CallbackQuery, state: FSMContext):
    """Asosiy menyudan 'Balans' bosilganda."""
    await callback.answer()
    data = await state.get_data()
    lang = data.get("language", "uz")

    api = APIClient()
    balance_info = await api.get_publisher_balance(callback.from_user.id)

    text = t("balance_title", lang,
        available=f"{balance_info.get('available', 0):,.0f}",
        pending=f"{balance_info.get('pending', 0):,.0f}",
    )
    await callback.message.answer(text)


@router.callback_query(F.data == "menu:settings")
async def on_menu_settings(callback: CallbackQuery, state: FSMContext):
    """Asosiy menyudan 'Sozlamalar' bosilganda."""
    from handlers.publisher import cmd_settings
    await callback.answer()
    await cmd_settings(callback.message, state, callback.from_user.id)
