"""Handler-level tests for session commands: /new /sessions /switch /rename /delete /fork.

Delete is a two-step, confirmation-guarded flow: nothing is deleted until the
"yes" button is pressed, and the "no" button must not call ``session.delete``.
"""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot
from kilocode_client import Kilo
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_callback, make_message, records

ACTIVE = "session-01"


def _config() -> Any:
    from kilocode_tg_bot.config import Settings

    return Settings(telegram_bot_token="123456:TEST-TOKEN", telegram_allowed_user_id=42)


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]


def _edits(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "editMessageText"]


async def test_new_creates_and_activates(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_new

    message = make_message(bot, text="/new my project")
    await on_new(
        message,
        command=make_command("my project", "new"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
    )
    calls = fake_kilo.calls_for("session.create")
    assert calls and calls[0].args == ("my project",)
    assert await store.get_active(42) is not None
    assert any("Создана сессия" in s for s in _texts(bot))


async def test_new_without_title_creates(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_new

    message = make_message(bot, text="/new")
    await on_new(
        message,
        command=make_command(None, "new"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
    )
    assert fake_kilo.called("session.create")
    # default title "untitled" came through; the session is active
    assert await store.get_active(42) is not None


async def test_sessions_lists_and_offers_choice(
    bot: Bot, fake_kilo: FakeKilo, settings: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_sessions

    fake_kilo.seed_session("s1", "alpha")
    fake_kilo.seed_session("s2", "beta")
    message = make_message(bot, text="/sessions")
    await on_sessions(message, kilo=cast(Kilo, fake_kilo), settings=settings)
    text = "\n".join(_texts(bot))
    assert "alpha" in text and "beta" in text


async def test_sessions_offers_keyboard_with_set_buttons(
    bot: Bot, fake_kilo: FakeKilo, settings: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_sessions
    from kilocode_tg_bot.keyboards.inline import SessionSelectCD

    fake_kilo.seed_session("s1", "alpha")
    message = make_message(bot, text="/sessions")
    await on_sessions(message, kilo=cast(Kilo, fake_kilo), settings=settings)
    # second sendMessage carried the keyboard markup
    send = [c for c in records(bot).calls if c.method == "sendMessage"]
    kb = send[-1].data.get("reply_markup") if send else None
    packed = SessionSelectCD(action="set", session_id="s1").pack()
    assert kb and packed in str(kb)


async def test_pick_sets_active_session(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_pick
    from kilocode_tg_bot.keyboards.inline import SessionSelectCD

    fake_kilo.seed_session("s1", "alpha")
    cd = SessionSelectCD(action="set", session_id="s1")
    callback = make_callback(bot, data=cd.pack())
    await on_pick(callback, callback_data=cd, store=store)
    assert await store.get_active(42) == "s1"


async def test_switch_is_alias_of_sessions(
    bot: Bot, fake_kilo: FakeKilo, settings: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_sessions

    fake_kilo.seed_session("s1", "alpha")
    message = make_message(bot, text="/switch")
    await on_sessions(message, kilo=cast(Kilo, fake_kilo), settings=settings)
    assert any("Доступно сессий" in s for s in _texts(bot))


async def test_rename_active_session(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_rename

    fake_kilo.seed_session(ACTIVE, "old")
    await store.set_active(42, ACTIVE)
    message = make_message(bot, text="/rename new title")
    await on_rename(
        message,
        command=make_command("new title", "rename"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
    )
    assert fake_kilo.called("session.rename")
    assert any("Переименовано" in s and "new title" in s for s in _texts(bot))


async def test_rename_requires_title(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_rename

    await store.set_active(42, ACTIVE)
    message = make_message(bot, text="/rename")
    await on_rename(
        message,
        command=make_command(None, "rename"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
    )
    assert not fake_kilo.called("session.rename")
    assert any("Использование" in s for s in _texts(bot))


async def test_delete_asks_for_confirmation_and_does_not_delete(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_delete

    fake_kilo.seed_session(ACTIVE, "t")
    await store.set_active(42, ACTIVE)
    message = make_message(bot, text="/delete")
    await on_delete(message, kilo=cast(Kilo, fake_kilo), store=store)
    assert not fake_kilo.called("session.delete")
    sent = "\n".join(_texts(bot))
    assert "Удалить активную сессию" in sent


async def test_delete_confirm_yes_deletes_and_clears(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_delete_confirm
    from kilocode_tg_bot.keyboards.inline import DeleteConfirmCD

    fake_kilo.seed_session(ACTIVE, "t")
    await store.set_active(42, ACTIVE)
    cd = DeleteConfirmCD(action="yes", session_id=ACTIVE)
    callback = make_callback(bot, data=cd.pack())
    await on_delete_confirm(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo), store=store)
    assert fake_kilo.called("session.delete")
    assert await store.get_active(42) is None
    assert any("удалена" in s for s in _edits(bot))


async def test_delete_confirm_no_does_not_delete(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_delete_confirm
    from kilocode_tg_bot.keyboards.inline import DeleteConfirmCD

    fake_kilo.seed_session(ACTIVE, "t")
    await store.set_active(42, ACTIVE)
    cd = DeleteConfirmCD(action="no", session_id=ACTIVE)
    callback = make_callback(bot, data=cd.pack())
    await on_delete_confirm(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo), store=store)
    assert not fake_kilo.called("session.delete")
    assert await store.get_active(42) == ACTIVE
    assert any("отменено" in s.lower() for s in _edits(bot))


async def test_fork_with_message_id(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_fork

    fake_kilo.seed_session(ACTIVE, "orig")
    await store.set_active(42, ACTIVE)
    message = make_message(bot, text="/fork some-msg-1")
    await on_fork(
        message,
        command=make_command("some-msg-1", "fork"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
    )
    calls = fake_kilo.calls_for("session.fork")
    assert calls and calls[0].kwargs.get("message_id") == "some-msg-1"
    assert any("Форк создан" in s for s in _texts(bot))


async def test_fork_without_message_id(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_fork

    fake_kilo.seed_session(ACTIVE, "orig")
    await store.set_active(42, ACTIVE)
    message = make_message(bot, text="/fork")
    await on_fork(
        message,
        command=make_command(None, "fork"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
    )
    calls = fake_kilo.calls_for("session.fork")
    assert calls and calls[0].kwargs.get("message_id") is None
    assert any("Форк создан" in s for s in _texts(bot))


async def test_fork_requires_active_session(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_fork

    message = make_message(bot, text="/fork")
    await on_fork(
        message,
        command=make_command(None, "fork"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
    )
    assert not fake_kilo.called("session.fork")
    assert any("Нет активной сессии" in s for s in _texts(bot))
