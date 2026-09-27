"""Inject shared app dependencies into every handler's ``data``.

aiogram 3.x resolves handler parameters by name against the ``data`` dict the
middleware chain builds. This provider middleware puts ``settings``,
``store`` and ``kilo`` into that dict so any handler can simply declare them
as keyword parameters.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Update
from kilocode_client import Kilo

from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.state.session_store import SessionStore


class ContextMiddleware(BaseMiddleware):
    """Add shared ``settings``, ``store`` and ``kilo`` to handler data."""

    def __init__(self, settings: Settings, store: SessionStore, kilo: Kilo) -> None:
        self._settings = settings
        self._store = store
        self._kilo = kilo

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        data["settings"] = self._settings
        data["store"] = self._store
        data["kilo"] = self._kilo
        return await handler(event, data)
