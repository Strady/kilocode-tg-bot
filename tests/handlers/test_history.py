"""Coverage for the /history command, history pagination and helper edge cases.

These exercise the parts of ``handlers/chat.py`` and ``handlers/common.py`` that
the main chat-stream tests don't reach: rendering a history page, next/prev
pagination callbacks, the tool-part text renderer, text truncation and the
``reply_text`` / ``call_kilo`` fallback branches.
"""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot
from kilocode_client import Kilo
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_callback, make_message, records


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]


async def test_history_no_active_session_shows_hint(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import on_history

    message = make_message(bot, text="/history")
    await on_history(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
    assert any("Нет активной сессии" in s for s in _texts(bot))
    assert not fake_kilo.called("list_messages")


async def test_history_empty_session(bot: Bot, fake_kilo: FakeKilo, store: Any) -> None:
    from kilocode_tg_bot.handlers.chat import on_history

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    message = make_message(bot, text="/history")
    await on_history(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
    assert any("Сообщений в сессии нет" in s for s in _texts(bot))


async def test_history_renders_messages_as_text(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import on_history

    fake_kilo.seed_session("s1", "demo")
    fake_kilo.seed_message("s1", "user", "m1", "hello")
    fake_kilo.seed_message("s1", "assistant", "m2", "hi there")
    await store.set_active(42, "s1")
    message = make_message(bot, text="/history")
    await on_history(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
    joined = "\n".join(_texts(bot))
    assert "История сессии" in joined
    assert "hello" in joined and "hi there" in joined
    assert "user" in joined and "assistant" in joined


async def test_history_pagination_next_and_prev(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import on_history_nav
    from kilocode_tg_bot.keyboards.inline import HistoryNavCD

    fake_kilo.seed_session("s1", "demo")
    # 7 messages -> 2 pages (page size 5)
    for i in range(7):
        fake_kilo.seed_message("s1", "user", f"m{i}", f"msg {i}")
    await store.set_active(42, "s1")

    msg = make_message(bot, message_id=10, text="_")
    # first page shows the older 5; navigate "next" to the tail
    cd = HistoryNavCD(session_id="s1", offset=0, direction="next")
    cb = make_callback(bot, data=cd.pack(), message=msg)
    await on_history_nav(cb, callback_data=cd, kilo=cast(Kilo, fake_kilo), settings=_settings())
    next_joined = "\n".join(_texts(bot))
    assert "msg 5" in next_joined and "msg 6" in next_joined

    # navigate "prev" back to the head
    cd_prev = HistoryNavCD(session_id="s1", offset=5, direction="prev")
    cb_prev = make_callback(bot, data=cd_prev.pack(), message=msg)
    await on_history_nav(
        cb_prev, callback_data=cd_prev, kilo=cast(Kilo, fake_kilo), settings=_settings()
    )
    prev_joined = "\n".join(_texts(bot))
    assert "msg 0" in prev_joined and "msg 1" in prev_joined


async def test_history_nav_with_no_message_answers_quietly(
    bot: Bot, fake_kilo: FakeKilo
) -> None:
    from aiogram.types import CallbackQuery, User
    from kilocode_tg_bot.handlers.chat import on_history_nav
    from kilocode_tg_bot.keyboards.inline import HistoryNavCD

    fake_kilo.seed_session("s1", "demo")
    fake_kilo.seed_message("s1", "user", "m1", "hello")
    cb = CallbackQuery(
        id="cq-x",
        from_user=User(id=42, is_bot=False, first_name="Owner", username="owner"),
        chat_instance="ci1",
        data="shist:0:next",
        message=None,  # callback arrived with no editable message
    )
    cd = HistoryNavCD(session_id="s1", offset=0, direction="next")
    # passes through the `callback.message is None` early return without crashing
    await on_history_nav(cb, callback_data=cd, kilo=cast(Kilo, fake_kilo), settings=_settings())


def test_message_text_renders_tool_parts() -> None:
    from kilocode_tg_bot.handlers.chat import _message_text

    class _State:
        status = "completed"

    class _Info:
        id = "m1"
        role = "assistant"

    class _Part:
        type = "tool"
        tool = "/read"
        state = _State()

    class _Msg:
        info = _Info()
        parts = [_Part()]

    rendered = _message_text(_Msg())
    assert "[tool completed] /read" in rendered


def test_message_text_empty_parts() -> None:
    from kilocode_tg_bot.handlers.chat import _message_text

    class _NoParts:
        parts = []

    assert _message_text(_NoParts()) == "(нет текста)"


def test_cap_truncates_long_text() -> None:
    from kilocode_tg_bot.handlers.chat import _cap

    short = "short"
    assert _cap(short) == short
    long_text = "x" * 5000
    capped = _cap(long_text)
    assert len(capped) <= 4000
    assert capped.endswith("…")


def _settings() -> Any:
    from kilocode_tg_bot.config import Settings

    return Settings(
        telegram_bot_token="123456:TEST-TOKEN",
        telegram_allowed_user_id=42,
    )
