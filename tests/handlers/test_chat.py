"""Handler-level tests for the chat/streaming path and the Stop button."""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot
from kilocode_client import Kilo
from tests.fakes import events
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_callback, make_message, records


def _settings() -> Any:
    from kilocode_tg_bot.config import Settings

    return Settings(
        telegram_bot_token="123456:TEST-TOKEN",
        telegram_allowed_user_id=42,
        telegram_edit_throttle_seconds=0.0,
    )


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]


def _edits(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "editMessageText"]


async def test_chat_no_active_session_shows_hint(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import on_chat

    message = make_message(bot, text="hello")
    await on_chat(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
    assert any("Нет активной сессии" in s for s in _texts(bot))
    assert not fake_kilo.called("send_prompt_async")


async def test_chat_streams_text_into_edits(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import on_chat

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    await fake_kilo.set_stream_events(
        "s1",
        [
            events.text_delta("s1", "Hello "),
            events.text_delta("s1", "world"),
            events.turn_close("s1"),
        ],
    )
    fake_kilo.event_delay = 0.001

    message = make_message(bot, text="hi")
    await on_chat(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())

    sends = _texts(bot)
    edits = _edits(bot)
    # status message + stream placeholder got sent
    assert any("Отправляю" in s for s in sends)
    # the final text made it into edits (full concatenation)
    assert any("Hello world" in e for e in edits)
    # at least the placeholder was edited
    assert len(edits) >= 1


async def test_chat_streams_markdown_as_html(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import on_chat

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    await fake_kilo.set_stream_events(
        "s1",
        [
            events.text_delta("s1", "**done** `ok`"),
            events.turn_close("s1"),
        ],
    )
    fake_kilo.event_delay = 0.001

    message = make_message(bot, text="go")
    await on_chat(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())

    edit_calls = records(bot).method_calls("editMessageText")
    # the streamed rich text is sent with parse_mode=HTML
    assert edit_calls, "expected streamed edits"
    assert all(c.data.get("parse_mode") == "HTML" for c in edit_calls)
    # and the final message contains HTML tags for the markdown constructs
    assert any("<b>done</b> <code>ok</code>" in c.text() for c in edit_calls)


async def test_chat_tool_call_surface_separate_message(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import on_chat

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    await fake_kilo.set_stream_events(
        "s1",
        [
            events.tool_event("s1", "read", {"file": "/tmp/a"}),
            events.text_delta("s1", "result"),
            events.turn_close("s1"),
        ],
    )
    fake_kilo.event_delay = 0.001
    message = make_message(bot, text="do it")
    await on_chat(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
    assert any("🔧" in s and "read" in s for s in _texts(bot))


async def test_chat_permission_triggers_keyboard_and_reply(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import on_chat
    from kilocode_tg_bot.handlers.permissions import on_permission_reply
    from kilocode_tg_bot.keyboards.inline import PermissionReplyCD

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    await fake_kilo.set_stream_events(
        "s1", [events.permission_event("s1", "req-3", "write"), events.turn_close("s1")]
    )
    fake_kilo.event_delay = 0.001

    message = make_message(bot, text="go")
    await on_chat(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
    assert any("Требуется разрешение" in s for s in _texts(bot))

    # Press "once" on the resulting permission message
    cd = PermissionReplyCD(request_id="req-3", reply="once")
    msg = make_message(bot, message_id=123, text="🔐 Требуется разрешение:")
    callback = make_callback(bot, data=cd.pack(), message=msg)
    await on_permission_reply(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo))
    replies = fake_kilo.calls_for("permission.reply")
    assert replies and replies[0].args == ("req-3", "once")


async def test_stop_button_interrupts_running_stream(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import controller, on_stop

    fake_kilo.seed_session("s1", "demo")
    handle = controller.start("s1")
    try:
        message = make_message(bot, message_id=123, text="_")
        callback = make_callback(bot, data="stop_run:s1", message=message)
        await on_stop(callback, kilo=cast(Kilo, fake_kilo))
        assert fake_kilo.called("interrupt")
        assert handle.cancelled is True
    finally:
        controller.finish("s1", handle)


async def test_stop_button_noop_when_not_running(
    bot: Bot, fake_kilo: FakeKilo
) -> None:
    from kilocode_tg_bot.handlers.chat import on_stop

    fake_kilo.seed_session("s2", "t")
    message = make_message(bot, message_id=123, text="_")
    callback = make_callback(bot, data="stop_run:s2", message=message)
    await on_stop(callback, kilo=cast(Kilo, fake_kilo))
    assert not fake_kilo.called("interrupt")


async def test_chat_unexpected_error_reports_friendly_message(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import on_chat

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    # force the stream to raise an unexpected error
    fake_kilo.fail("stream_session_events", RuntimeError("boom"))

    message = make_message(bot, text="hello")
    await on_chat(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
    # handled errors are reported, never propagated to the caller
    assert any("Ошибка при обработке запроса" in s for s in _texts(bot))


async def test_chat_rejects_concurrent_run_in_same_session(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.chat import controller, on_chat

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    handle = controller.start("s1")
    try:
        message = make_message(bot, text="hello")
        await on_chat(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_settings())
        assert any("уже идёт генерация" in s for s in _texts(bot))
        assert not fake_kilo.called("stream_session_events")
    finally:
        controller.finish("s1", handle)


async def test_stop_button_without_session_id_answers_error(
    bot: Bot, fake_kilo: FakeKilo
) -> None:
    from kilocode_tg_bot.handlers.chat import on_stop

    message = make_message(bot, message_id=123, text="_")
    callback = make_callback(bot, data="stop_run", message=message)
    await on_stop(callback, kilo=cast(Kilo, fake_kilo))
    # no session id -> the handler replies without calling the server
    assert not fake_kilo.called("interrupt")


async def test_run_controller_stop_and_get(bot: Bot, fake_kilo: FakeKilo) -> None:
    from kilocode_tg_bot.handlers.chat import controller

    assert controller.stop("missing") is False
    fake_kilo.seed_session("s9", "t")
    handle = controller.start("s9")
    try:
        assert controller.is_running("s9") is True
        assert controller.get("s9") is handle
        assert controller.stop("s9") is True
        assert handle.cancelled is True
        # stop() marks the handle; is_running stays true until finish() releases it
        assert controller.is_running("s9") is True
    finally:
        controller.finish("s9", handle)
        assert controller.is_running("s9") is False
