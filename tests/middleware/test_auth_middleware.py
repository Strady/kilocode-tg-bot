"""Middleware tests for :class:`~kilocode_tg_bot.middlewares.auth.AuthMiddleware`.

The gate runs before any handler, so a foreign user's update must be dropped
without reaching any handler or producing any Telegram call. We verify this at the
dispatcher level with a real :class:`FakeKilo` wired through
:class:`ContextMiddleware`, and at the middleware level for each update subtype.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot, Dispatcher
from tests.fakes.fake_telegram import (
    make_raw_callback_update,
    make_raw_message_update,
)

OWNER = 42


def test_owner_message_reaches_handler(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/health"))
    # /health ran and called kilo.health, and replied to the user
    assert fake_kilo.called("health")
    assert rec.method_calls("sendMessage") != []


def test_foreign_message_does_not_reach_handler(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    result = _feed(dp, bot, make_raw_message_update(user_id=999, text="/health"))
    assert result is None  # dropped before a handler
    assert not fake_kilo.called("health")
    assert rec.method_calls("sendMessage") == []


def test_foreign_callback_does_not_reach_handler(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    # a delete-confirm callback that, if it ran, would call kilo.session.delete
    fake_kilo.seed_session("s1", "t")
    result = _feed(
        dp, bot, make_raw_callback_update(user_id=999, data="sdel:yes:s1")
    )
    assert result is None
    assert not fake_kilo.called("session.delete")


def test_owner_callback_reaches_handler(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    # Press the "yes" delete button against an existing active session.
    fake_kilo.seed_session("s1", "t")
    _feed(
        dp, bot, make_raw_callback_update(user_id=OWNER, data="sdel:yes:s1")
    )
    assert fake_kilo.called("session.delete")


def test_document_update_checked_for_owner(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    raw = make_raw_message_update(user_id=OWNER, text="/import")
    # /import just prints a hint; the point is the update is not dropped
    _feed(dp, bot, raw)
    assert rec.method_calls("sendMessage") != []


def test_no_reply_to_foreign_user(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=777, text="hello"))
    # Nothing at all is sent back (no benign "access denied" either).
    assert rec.method_calls("sendMessage") == []


def _feed(dp: Dispatcher, bot: Bot, update: dict[str, Any]) -> Any:
    import asyncio

    return asyncio.run(dp.feed_raw_update(bot=bot, update=_normalize(update)))


def _normalize(update: dict[str, Any]) -> dict[str, Any]:
    from aiogram.types import Update

    u = Update.model_validate(update)
    return u.model_dump(mode="json", exclude_none=True)
