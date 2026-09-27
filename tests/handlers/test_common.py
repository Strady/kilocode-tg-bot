"""Unit tests for the shared handler helpers in ``handlers/common.py``.

Covers the branches the higher-level handler tests don't reach: large-message
``.txt`` fallback, the non-reply variant of :func:`reply_text`, generic-vs-typed
error handling in :func:`call_kilo`, the ``require_active_session`` error path and
the ``editable_message`` non-editable case.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import InaccessibleMessage
from kilocode_client import KiloError
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_callback, make_message, records


def _settings(threshold: int = 3900) -> Any:
    from kilocode_tg_bot.config import Settings

    return Settings(
        telegram_bot_token="123456:TEST-TOKEN",
        telegram_allowed_user_id=42,
        message_file_threshold=threshold,
    )


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]


def _docs(bot: Bot) -> list[dict[str, Any]]:
    return [c.data for c in records(bot).calls if c.method == "sendDocument"]


async def test_truncate(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.common import truncate

    assert truncate("short") == "short"
    long_text = "x" * 100
    truncated = truncate(long_text, limit=10)
    assert len(truncated) <= 10
    assert truncated.endswith("...")


async def test_reply_text_ships_large_text_as_document(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.common import reply_text

    message = make_message(bot, message_id=7, text="/x")
    result = await reply_text(
        message, "A" * 5000, _settings(threshold=100), reply=True
    )
    assert result is not None
    docs = _docs(bot)
    assert docs and "document" in docs[0]


async def test_reply_text_no_reply_branch(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.common import reply_text

    message = make_message(bot, message_id=7, text="/x")
    await reply_text(message, "plain response", _settings(), reply=False)
    assert any("plain response" in s for s in _texts(bot))


async def test_call_kilo_generic_exception_is_reported(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.common import call_kilo

    async def boom() -> int:
        raise ValueError("no")

    message = make_message(bot, message_id=7)
    result = await call_kilo(boom, message)
    assert result is None
    assert any("Unexpected error" in s for s in _texts(bot))


async def test_call_kilo_typed_error_is_humanized(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.common import call_kilo

    async def kilofail() -> int:
        raise KiloError(message="boom", status_code=500)

    message = make_message(bot, message_id=7)
    result = await call_kilo(kilofail, message)
    assert result is None
    assert any("Kilo server error" in s for s in _texts(bot))


async def test_call_kilo_success_returns_value(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.common import call_kilo

    async def ok() -> int:
        return 42

    message = make_message(bot, message_id=7)
    assert await call_kilo(ok, message) == 42


async def test_require_active_session_no_active(
    bot: Bot, store: Any
) -> None:
    from kilocode_tg_bot.handlers.common import require_active_session

    message = make_message(bot, message_id=7)
    result = await require_active_session(store, 42, FakeKilo(), message)
    assert result is None
    assert any("Нет активной сессии" in s for s in _texts(bot))


async def test_require_active_session_missing_on_server(bot: Bot, store: Any) -> None:
    from kilocode_tg_bot.handlers.common import require_active_session

    kilo = FakeKilo()
    kilo.seed_session("s1", "demo")
    await store.set_active(42, "does-not-exist")
    message = make_message(bot, message_id=7)
    result = await require_active_session(store, 42, kilo, message)
    assert result is None
    assert any("Kilo server error" in s for s in _texts(bot))


async def test_require_active_session_returns_session(
    bot: Bot, store: Any
) -> None:
    from kilocode_tg_bot.handlers.common import require_active_session

    kilo = FakeKilo()
    kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    message = make_message(bot, message_id=7)
    result = await require_active_session(store, 42, kilo, message)
    assert result is not None and result.id == "s1"


async def test_editable_message_returns_none_for_inaccessible(bot: Bot) -> None:
    from aiogram.types import CallbackQuery, Chat, Message, User
    from kilocode_tg_bot.handlers.common import editable_message

    inaccessible = InaccessibleMessage(chat=Chat(id=200, type="private"), message_id=5, date=0)
    callback = CallbackQuery(
        id="cq-in",
        from_user=User(id=42, is_bot=False, first_name="Owner", username="owner"),
        chat_instance="ci1",
        data="x",
        message=inaccessible,  # may be an InaccessibleMessage (frozen, set at construction)
    )
    assert not isinstance(callback.message, Message)
    assert editable_message(callback) is None


async def test_editable_message_returns_message_when_editable(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.common import editable_message

    msg = make_message(bot, message_id=5)
    callback = make_callback(bot, data="x", message=msg)
    assert editable_message(callback) is msg


async def test_current_user_id(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.common import current_user_id

    assert current_user_id({"event_from_user": None}) is None
