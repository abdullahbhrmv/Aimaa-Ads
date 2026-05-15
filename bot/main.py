"""
AimaaAds Telegram Bot
====================
Kanal boshqaruvi, reklama tarqatish va ta'sir kuzatish.
"""

import asyncio
import logging
from os import getenv
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from handlers import publisher, common, inline
from middlewares.i18n import I18nMiddleware
from services.api_client import close_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN muhit o'zgaruvchisi kerak!")


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Middleware
    dp.message.middleware(I18nMiddleware())

    # Router'larni ro'yxatdan o'tkazish
    dp.include_router(common.router)
    dp.include_router(publisher.router)
    dp.include_router(inline.router)

    logger.info("AimaaAds Bot ishga tushirilmoqda...")
    try:
        await dp.start_polling(bot)
    finally:
        # Shared httpx clientni yopish
        await close_client()
        logger.info("AimaaAds Bot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())
