"""Dispatcher-level routing (level 2): feed raw updates and assert the right
handler ran and produced the right outgoing Telegram call, all on FakeKilo."""

from __future__ import annotations

import asyncio
from typing import Any

from aiogram import Bot, Dispatcher
from tests.fakes.fake_telegram import make_raw_callback_update, make_raw_message_update

OWNER = 42


def _feed(dp: Dispatcher, bot: Bot, update: dict[str, Any]) -> Any:
    return asyncio.run(dp.feed_raw_update(bot=bot, update=update))


def _sent(rec: Any) -> list[str]:
    return [c.text() for c in rec.method_calls("sendMessage")]


def _edit(rec: Any) -> list[str]:
    return [c.text() for c in rec.method_calls("editMessageText")]


def _joined(*chunks: list[str]) -> str:
    return "\n".join(c for chunk in chunks for c in chunk)


def test_new_router_creates_and_activates(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/new Demo"))
    assert fake_kilo.called("session.create")
    assert "Создана сессия" in _joined(_sent(rec))


def test_sessions_router_lists(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    fake_kilo.seed_session("s-default", "My Session")
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/sessions"))
    sent = _joined(_sent(rec))
    assert "Доступно сессий: 1" in sent
    assert "My Session" in sent


def test_chat_router_streams(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any, store: Any
) -> None:
    bot, dp, rec = dispatcher
    fake_kilo.seed_session("s-chat", "demo")
    asyncio.run(store.set_active(OWNER, "s-chat"))
    from tests.fakes import events

    asyncio.run(
        fake_kilo.set_stream_events(
            "s-chat", [events.text_delta("s-chat", "Привет"), events.turn_close("s-chat")]
        )
    )
    # keep the stream open past subscribe_settle so send_prompt_async fires
    fake_kilo.event_delay = 0.3
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="hello"))
    assert fake_kilo.called("send_prompt_async")
    assert _edit(rec) != [] or "Привет" in _joined(_sent(rec))


def test_permissions_router_allow_all(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/allow_all on"))
    assert fake_kilo.called("permission.allow_everything")
    assert any("включено" in s for s in _sent(rec))


def test_tools_router_run(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any, store: Any
) -> None:
    bot, dp, rec = dispatcher
    fake_kilo.seed_session("s-tool", "demo")
    asyncio.run(store.set_active(OWNER, "s-tool"))
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/run /help"))
    assert fake_kilo.called("run_command")


def test_health_router(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/health"))
    assert fake_kilo.called("health")
    assert any("Сервер Kilo отвечает" in s for s in _sent(rec))


def test_help_router_lists_commands(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/help"))
    sent = _joined(_sent(rec))
    assert "/new" in sent and "/health" in sent and "/context" in sent
    # a known command must not be misreported as unknown
    assert "Неизвестная команда" not in sent


def test_unknown_command_router_answers(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/zzz_not_a_command"))
    sent = _joined(_sent(rec))
    assert "Неизвестная команда /zzz_not_a_command" in sent
    assert fake_kilo.calls == []  # no server interaction for an unknown command


def test_known_command_not_swallowed_by_unknown_router(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    # the unknown-command fallback must not eat a real command (/cancel has no deps)
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/cancel"))
    sent = _joined(_sent(rec))
    assert "Неизвестная команда" not in sent


def test_foreign_user_never_reaches_any_handler(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=999, text="/new Foreign"))
    _feed(dp, bot, make_raw_message_update(user_id=999, text="/health"))
    _feed(dp, bot, make_raw_callback_update(user_id=999, data="sdel:yes:s1"))
    # nothing reached a handler and nothing was sent back
    assert fake_kilo.calls == []
    assert rec.method_calls("sendMessage") == []


def test_callback_routing_delete_confirm(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any
) -> None:
    bot, dp, rec = dispatcher
    fake_kilo.seed_session("s-del", "t")
    _feed(dp, bot, make_raw_callback_update(user_id=OWNER, data="sdel:yes:s-del"))
    assert fake_kilo.called("session.delete")
