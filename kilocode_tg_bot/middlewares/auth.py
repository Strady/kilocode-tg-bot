"""Authorization middleware.

Guards every update so only ``TELEGRAM_ALLOWED_USER_ID`` reaches any handler.
Callbacks, inline queries, documents and ordinary messages all carry a
``from_user``; anything else is ignored. The middleware is registered first in
the router chain so denied updates never execute bot logic.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User

logger = logging.getLogger(__name__)


def _extract_user(update: Update) -> User | None:
    """Return the ``from_user`` for the update's concrete object, if present.

    Uses duck-typed attribute access rather than ``isinstance`` so the middleware
    is robust to the many update subtypes and trivially testable.
    """
    objects = (
        update.message,
        update.edited_message,
        update.channel_post,
        update.edited_channel_post,
        update.business_message,
        update.edited_business_message,
        update.callback_query,
        update.inline_query,
    )
    for obj in objects:
        user = getattr(obj, "from_user", None)
        if user is not None and getattr(user, "id", None) is not None:
            return user
    return None


class AuthMiddleware(BaseMiddleware):
    """Drop all updates that do not originate from the configured owner."""

    def __init__(self, allowed_user_id: int) -> None:
        self._allowed_user_id = allowed_user_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = _extract_user(cast(Update, event))
        if user is None or user.id != self._allowed_user_id:
            if user is not None:
                logger.warning(
                    "Blocked update from user id=%s (username=%s)", user.id, user.username
                )
            return None
        return await handler(event, data)
