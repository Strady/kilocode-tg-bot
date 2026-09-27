"""Error-handling: Kilo failures (network/HTTP/stream-break) must produce a
friendly message and never crash the bot or escape the dispatcher."""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot, Dispatcher
from kilocode_client import Kilo, KiloError

from tests.fakes import events
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import (
    make_callback,
    make_message,
    make_raw_message_update,
    records,
)


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]


def _has_friendly(bot: Bot, *needles: str) -> bool:
    joined = "\n".join(_texts(bot))
    return all(n in joined for n in needles)


def _feed(dp: Dispatcher, bot: Bot, update: dict[str, Any]) -> Any:
    import asyncio

    return asyncio.run(dp.feed_raw_update(bot=bot, update=update))


def _settings() -> Any:
    from kilocode_tg_bot.config import Settings

    return Settings(
        telegram_bot_token="123456:TEST-TOKEN",
        telegram_allowed_user_id=42,
        telegram_edit_throttle_seconds=0.0,
    )


# -- /new ---------------------------------------------------------------------


async def test_new_http_error_is_friendly(bot: Bot, fake_kilo: FakeKilo, store: Any) -> None:
    from kilocode_tg_bot.handlers.sessions import on_new

    fake_kilo.fail("session.create", KiloError(message="server down", status_code=500))
    message = make_message(bot, text="/new test")
    await on_new(
        message,
        command=_command("test", "new"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
        bot=bot,
    )
    assert _has_friendly(bot, "Kilo server error", "server down", "HTTP 500")
    # a failed create must not become the active session
    assert await store.get_active(42) is None


async def test_new_network_error_is_friendly(bot: Bot, fake_kilo: FakeKilo, store: Any) -> None:
    from kilocode_tg_bot.handlers.sessions import on_new

    fake_kilo.fail("session.create", TimeoutError("connection timed out"))
    message = make_message(bot, text="/new")
    await on_new(
        message,
        command=_command(None, "new"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
        bot=bot,
    )
    # non-KiloError is still reported as a friendly message
    assert any("Unexpected error" in s for s in _texts(bot))


def test_new_error_via_dispatcher_does_not_crash(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    fake_kilo.fail("session.create", KiloError(message="boom", status_code=500))
    _feed(dp, bot, make_raw_message_update(user_id=42, text="/new x"))
    # the bot answered (not crashed) and both a send happened
    assert rec.method_calls("sendMessage") != []
    assert any("Kilo server error" in c.text() for c in rec.method_calls("sendMessage"))


# -- /model -------------------------------------------------------------------


async def test_model_provider_http_error_is_friendly(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.model_agent import on_model

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    fake_kilo.fail("list_providers", KiloError(message="bad gateway", status_code=502))
    message = make_message(bot, text="/model")
    await on_model(message, kilo=cast(Kilo, fake_kilo), state=fsm, store=store)
    assert _has_friendly(bot, "Kilo server error", "bad gateway")


# -- chat/prompt stream -------------------------------------------------------


async def test_chat_prompt_api_error_is_friendly(bot: Bot, fake_kilo: FakeKilo, store: Any) -> None:
    from kilocode_tg_bot.handlers.chat import on_chat

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    # send_prompt_async raises; the sender task's error must surface through
    # stream_prompt so the handler reports it (not swallow it).
    fake_kilo.fail("send_prompt_async", KiloError(message="prompt rejected", status_code=400))
    # keep the stream open past subscribe_settle so the send task actually runs
    await fake_kilo.set_stream_events(
        "s1", [events.text_delta("s1", "x"), events.turn_close("s1")]
    )
    fake_kilo.event_delay = 0.3
    message = make_message(bot, text="hello")
    await on_chat(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
    assert any("Ошибка при обработке запроса" in s for s in _texts(bot))


async def test_chat_stream_break_is_friendly(bot: Bot, fake_kilo: FakeKilo, store: Any) -> None:
    from kilocode_tg_bot.handlers.chat import on_chat

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    # the SSE stream breaks mid-run
    fake_kilo.fail("stream_session_events", KiloError(message="stream closed", status_code=500))
    message = make_message(bot, text="hello")
    await on_chat(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
    assert any("Ошибка при обработке запроса" in s for s in _texts(bot))


def test_chat_error_via_dispatcher_does_not_crash(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any, store: Any
) -> None:
    import asyncio

    asyncio.run(store.set_active(42, "s1"))
    fake_kilo.seed_session("s1", "demo")
    fake_kilo.fail("stream_session_events", KiloError(message="gone", status_code=500))
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=42, text="hello"))
    # a friendly message was delivered; the bot is still alive
    assert any("Ошибка при обработке запроса" in c.text() for c in rec.method_calls("sendMessage"))


# -- risky actions guarded ----------------------------------------------------


async def test_delete_confirm_error_does_not_clear_active(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.sessions import on_delete_confirm
    from kilocode_tg_bot.keyboards.inline import DeleteConfirmCD

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    fake_kilo.fail("session.delete", KiloError(message="forbidden", status_code=403))
    cd = DeleteConfirmCD(action="yes", session_id="s1")
    msg = make_message(bot, message_id=7, text="Удалить активную сессию?")
    callback = make_callback(bot, data=cd.pack(), message=msg)
    await on_delete_confirm(
        callback,
        callback_data=cd,
        kilo=cast(Kilo, fake_kilo),
        store=store,
        bot=bot,
    )
    assert _has_friendly(bot, "Kilo server error")
    # the active session is preserved because deletion failed
    assert await store.get_active(42) == "s1"


def _command(args: str | None, cmd: str) -> Any:
    from aiogram.filters import CommandObject

    return CommandObject(command=cmd, args=args)
