"""Keep a pinned message in the chat that reflects the active Kilo session.

The bot pins a short status message ("current session: <title>") so the owner can
always see, at a glance, which session they are working in. Whenever the active
session changes (created, switched, renamed, forked or deleted) the pinned message
is edited in place or (re)pinned as needed.

To survive restarts and avoid re-pinning a fresh message every time, the location
of the pinned message is recorded per user in :class:`SessionStore`. The next
refresh simply edits that message instead of pinning again.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from kilocode_client import SessionInfo

from kilocode_tg_bot.state.session_store import SessionStore

logger = logging.getLogger(__name__)


def session_pin_text(session: SessionInfo) -> str:
    """Return the plain-text body of the pinned active-session message."""
    title = session.title or session.id
    agent = session.agent or "-"
    model = session.model.id if session.model else "-"
    return (
        f"🔒 Текущая сессия: {title}\n"
        f"id: {session.id} · агент: {agent} · модель: {model}"
    )


async def _unpin_existing(bot: Bot, store: SessionStore, user_id: int) -> None:
    pin = await store.get_pin(user_id)
    if pin is None:
        return
    chat_id, message_id = pin
    try:
        await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:  # noqa: PERF203 - pin already gone; keep going
        pass
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:  # noqa: PERF203 - message already gone
        pass
    await store.clear_pin(user_id)


async def _ping_pin(
    bot: Bot,
    store: SessionStore,
    user_id: int,
    chat_id: int,
    session: SessionInfo,
) -> None:
    text = session_pin_text(session)
    pin = await store.get_pin(user_id)
    if pin is not None:
        existing_chat, existing_id = pin
        try:
            await bot.edit_message_text(
                text=text, chat_id=existing_chat, message_id=existing_id
            )
            return
        except TelegramBadRequest:
            pass
    sent = await bot.send_message(chat_id, text)
    try:
        await bot.pin_chat_message(chat_id, sent.message_id, disable_notification=True)
    except TelegramBadRequest:  # noqa: PERF203 - bot may lack pin rights
        logger.warning("Could not pin session message: bot may lack rights")
    await store.set_pin(user_id, chat_id, sent.message_id)


async def refresh_session_pin(
    bot: Bot,
    store: SessionStore,
    kilo: Any,
    user_id: int,
    chat_id: int | None,
) -> None:
    """Bring the pinned active-session message in line with the store.

    If no active session exists (or it can no longer be resolved) any existing pin
    is removed. Otherwise the pin is created or updated. ``kilo`` is the opaque
    injected client (real or test fake); errors are logged, never raised.
    """
    try:
        session_id = await store.get_active(user_id)
        if not session_id or chat_id is None:
            await _unpin_existing(bot, store, user_id)
            return
        session = await kilo.session.get(session_id)
        await _ping_pin(bot, store, user_id, chat_id, session)
    except Exception:  # noqa: BLE001 - pin upkeep must never crash a handler
        logger.exception("Failed to refresh pinned session message")
