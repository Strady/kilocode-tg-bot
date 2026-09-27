"""Small helpers shared across the handler routers.

Every public handler eventually talks to Telegram, so a few common utility
functions keep them consistent: building safe text replies (falling back to a
``.txt`` file for oversized payloads), looking up the user's active session, and
wrapping Kilo calls so a raised exception becomes a friendly message instead of
crashing the bot.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from aiogram.types import BufferedInputFile, Message
from kilocode_client import KiloError, SessionInfo

from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.services.kilo import humanize_error
from kilocode_tg_bot.state.session_store import SessionStore

logger = logging.getLogger(__name__)

T = TypeVar("T")

_MAX_INLINE = 4096


def truncate(text: str, limit: int = _MAX_INLINE) -> str:
    """Trim to under Telegram's limit, appending an ellipsis."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


async def reply_text(
    message: Message,
    text: str,
    settings: Settings,
    *,
    reply: bool = True,
    parse_mode: str | None = None,
    **kwargs: Any,
) -> Message | None:
    """Reply with ``text``; if it is too large, ship it as a ``.txt`` file."""
    if len(text) > settings.message_file_threshold:
        data = BufferedInputFile(text.encode("utf-8"), filename="kilocode_output.txt")
        if reply:
            return await message.answer_document(data, reply_to_message_id=message.message_id)
        return await message.answer_document(data)
    method = message.reply if reply else message.answer
    if reply:
        kwargs["reply_to_message_id"] = message.message_id
    return await method(truncate(text), parse_mode=parse_mode, **kwargs)


async def call_kilo(fn: Callable[[], Awaitable[T]], message: Message) -> T | None:
    """Run a Kilo call, reporting any :class:`KiloError` as a reply."""
    try:
        return await fn()
    except KiloError as exc:
        await message.answer(humanize_error(exc))
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected kilocode error")
        await message.answer(f"Unexpected error: {exc}")
        return None


async def require_active_session(
    store: SessionStore, user_id: int, client: Any, message: Message
) -> SessionInfo | None:
    """Return the user's active Kilo session, or send a hint and ``None``."""
    session_id = await store.get_active(user_id)
    if not session_id:
        await message.answer(
            "Нет активной сессии. Создайте её через /new или выберите через /sessions."
        )
        return None
    try:
        return await client.session.get(session_id)
    except KiloError as exc:
        await message.answer(humanize_error(exc))
        return None


def current_user_id(data: dict[str, Any]) -> int | None:
    """Extract the owner's user id from aiogram handler ``data``."""
    user = data.get("event_from_user")
    return user.id if user is not None else None
