"""Inject shared app dependencies into every handler's ``data``.

aiogram 3.x resolves handler parameters by name against the ``data`` dict the
middleware chain builds. This provider middleware puts ``settings``,
``store``, ``kilo`` and ``bot`` into that dict so any handler can simply declare
them as keyword parameters.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.state.session_store import SessionStore


class ContextMiddleware(BaseMiddleware):
    """Add shared ``settings``, ``store``, ``kilo`` and ``bot`` to handler data.

    ``kilo`` is an opaque injected dependency (the real :class:`Kilo` in
    production, a test fake elsewhere); the middleware never calls into it, so it
    is typed as ``Any`` to accept both.
    """

    def __init__(
        self, settings: Settings, store: SessionStore, kilo: Any, bot: Any
    ) -> None:
        self._settings = settings
        self._store = store
        self._kilo = kilo
        self._bot = bot

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["settings"] = self._settings
        data["store"] = self._store
        data["kilo"] = self._kilo
        data["bot"] = self._bot
        return await handler(event, data)
