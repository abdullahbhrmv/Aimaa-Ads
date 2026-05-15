"""Dil desteği middleware — kullanıcı diline göre mesajları çevirir."""

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message


class I18nMiddleware(BaseMiddleware):
    """Kullanıcı dil tercihini FSM state'ten alır."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # FSM state'ten dil bilgisini al
        state = data.get("state")
        if state:
            state_data = await state.get_data()
            data["lang"] = state_data.get("language", "uz")
        else:
            data["lang"] = "uz"

        return await handler(event, data)
