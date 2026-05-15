"""Kanal egasi komandlari: kanal ro'yxatdan o'tkazish, boshqarish, daromad."""

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards.publisher import (
    category_keyboard,
    channel_settings_keyboard,
    channels_list_keyboard,
)
from services.api_client import APIClient
from services.i18n import t

router = Router()


class RegisterChannel(StatesGroup):
    waiting_for_channel = State()
    waiting_for_category = State()


# ─── Kanal ro'yxatdan o'tkazish ───


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "uz")
    await message.answer(t("register_prompt", lang))
    await state.set_state(RegisterChannel.waiting_for_channel)


@router.message(RegisterChannel.waiting_for_channel, F.forward_from_chat)
async def on_channel_forward(message: Message, state: FSMContext, bot: Bot):
    """Forward qilingan xabardan kanal ma'lumotini olish."""
    chat = message.forward_from_chat
    data = await state.get_data()
    lang = data.get("language", "uz")

    if chat.type not in ("channel",):
        await message.answer(t("not_a_channel", lang))
        return

    try:
        member = await bot.get_chat_member(chat.id, bot.id)
        if member.status not in ("administrator", "creator"):
            await message.answer(t("bot_not_admin", lang))
            return
    except Exception:
        await message.answer(t("bot_no_access", lang))
        return

    chat_info = await bot.get_chat(chat.id)
    member_count = await bot.get_chat_member_count(chat.id)

    await state.update_data(
        channel_id=chat.id,
        channel_title=chat_info.title,
        channel_username=chat_info.username or "",
        channel_description=chat_info.description or "",
        subscriber_count=member_count,
    )

    await message.answer(
        f"✅ <b>{chat_info.title}</b>\n"
        f"👥 {member_count:,} obunachi\n\n"
        f"{t('choose_category', lang)}",
        reply_markup=await category_keyboard(lang),
    )
    await state.set_state(RegisterChannel.waiting_for_category)


@router.callback_query(RegisterChannel.waiting_for_category, F.data.startswith("cat:"))
async def on_category_select(callback: CallbackQuery, state: FSMContext):
    """Kategoriya tanlangandan keyin kanalni ro'yxatdan o'tkazish."""
    category_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    lang = data.get("language", "uz")

    api = APIClient()
    result = await api.register_channel(
        owner_telegram_id=callback.from_user.id,
        telegram_chat_id=data["channel_id"],
        title=data["channel_title"],
        username=data["channel_username"],
        description=data["channel_description"],
        subscriber_count=data["subscriber_count"],
        category_id=category_id,
        language=lang,
    )

    if result.get("success"):
        text = t("channel_registered", lang, title=data["channel_title"])
    else:
        text = t("error_generic", lang, error=result.get("error", "Noma'lum xatolik"))

    await callback.message.edit_text(text)
    await state.clear()
    await callback.answer()


# ─── Kanal ro'yxati ───


@router.message(Command("channels"))
async def cmd_channels(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "uz")

    api = APIClient()
    channels = await api.get_user_channels(message.from_user.id)

    if not channels:
        await message.answer(t("no_channels", lang))
        return

    text = t("my_channels", lang)
    for ch in channels:
        status_emoji = {"approved": "✅", "pending": "⏳", "rejected": "❌"}.get(
            ch["status"], "❓"
        )
        text += t("channel_info", lang,
            status_emoji=status_emoji,
            title=ch["title"],
            subscribers=f"{ch['subscriber_count']:,}",
            earnings=f"{ch.get('total_earnings', 0):,.0f}",
        )

    await message.answer(text)


# ─── Statistika ───


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "uz")

    api = APIClient()
    stats = await api.get_publisher_stats(message.from_user.id)

    text = t("stats_title", lang,
        total_channels=stats.get("total_channels", 0),
        total_impressions=f"{stats.get('total_impressions', 0):,}",
        total_clicks=f"{stats.get('total_clicks', 0):,}",
        total_earnings=f"{stats.get('total_earnings', 0):,.0f}",
        balance=f"{stats.get('balance', 0):,.0f}",
    )
    await message.answer(text)


# ─── Balans ───


@router.message(Command("balance"))
async def cmd_balance(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "uz")

    api = APIClient()
    balance_info = await api.get_publisher_balance(message.from_user.id)

    text = t("balance_title", lang,
        available=f"{balance_info.get('available', 0):,.0f}",
        pending=f"{balance_info.get('pending', 0):,.0f}",
    )
    await message.answer(text)


# ─── Sozlamalar ───


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext, telegram_user_id: int | None = None):
    """Kanal sozlamalari — kanalni tanlash."""
    data = await state.get_data()
    lang = data.get("language", "uz")
    user_id = telegram_user_id or message.from_user.id

    api = APIClient()
    channels = await api.get_user_channels(user_id)

    if not channels:
        await message.answer(t("settings_no_channels", lang))
        return

    await message.answer(
        t("settings_choose_channel", lang),
        reply_markup=channels_list_keyboard(channels, lang),
    )


@router.callback_query(F.data.startswith("ch_detail:"))
async def on_channel_detail(callback: CallbackQuery, state: FSMContext):
    """Kanal tanlanganda sozlamalar klaviaturasini ko'rsatish."""
    channel_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    lang = data.get("language", "uz")

    await callback.message.edit_reply_markup(
        reply_markup=channel_settings_keyboard(channel_id, lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ch_time:"))
async def on_channel_time(callback: CallbackQuery, state: FSMContext):
    """Reklama vaqtini sozlash — placeholder."""
    data = await state.get_data()
    lang = data.get("language", "uz")
    text = ("⏰ Reklama vaqtini sozlash funksiyasi tez orada ishga tushiriladi!"
            if lang == "uz" else
            "⏰ Функция настройки времени рекламы скоро будет доступна!")
    await callback.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("ch_limit:"))
async def on_channel_limit(callback: CallbackQuery, state: FSMContext):
    """Kunlik reklama limiti — placeholder."""
    data = await state.get_data()
    lang = data.get("language", "uz")
    text = ("📊 Kunlik limit sozlash funksiyasi tez orada ishga tushiriladi!"
            if lang == "uz" else
            "📊 Функция настройки дневного лимита скоро будет доступна!")
    await callback.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("ch_cpm:"))
async def on_channel_cpm(callback: CallbackQuery, state: FSMContext):
    """Minimal CPM — placeholder."""
    data = await state.get_data()
    lang = data.get("language", "uz")
    text = ("💰 Minimal CPM sozlash funksiyasi tez orada ishga tushiriladi!"
            if lang == "uz" else
            "💰 Функция настройки минимального CPM скоро будет доступна!")
    await callback.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("ch_pause:"))
async def on_channel_pause(callback: CallbackQuery, state: FSMContext):
    """Reklamani to'xtatish — placeholder."""
    data = await state.get_data()
    lang = data.get("language", "uz")
    text = ("⏸ To'xtatish funksiyasi tez orada ishga tushiriladi!"
            if lang == "uz" else
            "⏸ Функция приостановки скоро будет доступна!")
    await callback.answer(text, show_alert=True)


# ─── Payout ───


@router.message(Command("payout"))
async def cmd_payout(message: Message, state: FSMContext):
    """Pul yechib olish — placeholder."""
    data = await state.get_data()
    lang = data.get("language", "uz")

    api = APIClient()
    balance_info = await api.get_publisher_balance(message.from_user.id)
    available = balance_info.get("available", 0)

    text = t("payout_title", lang, available=f"{available:,.0f}")

    if available < 50000:
        text += t("payout_insufficient", lang)
    else:
        text += t("payout_coming_soon", lang)

    await message.answer(text)
