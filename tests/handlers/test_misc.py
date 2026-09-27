"""Handler-level tests for /health and /cancel (FSM reset)."""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot
from kilocode_client import Kilo, KiloError
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_message, records


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]


async def test_health_ok(bot: Bot, fake_kilo: FakeKilo) -> None:
    from kilocode_tg_bot.handlers.misc import on_health

    message = make_message(bot, text="/health")
    await on_health(message, kilo=cast(Kilo, fake_kilo))
    assert fake_kilo.called("health")
    sent = "\n".join(_texts(bot))
    assert "Сервер Kilo отвечает" in sent
    assert "status: ok" in sent


async def test_health_unavailable_is_friendly(bot: Bot, fake_kilo: FakeKilo) -> None:
    from kilocode_tg_bot.handlers.misc import on_health

    fake_kilo.fail("health", KiloError(message="connection refused", status_code=None))
    message = make_message(bot, text="/health")
    await on_health(message, kilo=cast(Kilo, fake_kilo))
    sent = "\n".join(_texts(bot))
    assert "Сервер Kilo недоступен" in sent
    assert "connection refused" in sent


async def test_cancel_resets_fsm(bot: Bot, fake_kilo: FakeKilo, fsm: Any) -> None:
    from kilocode_tg_bot.handlers.misc import on_cancel
    from kilocode_tg_bot.state.states import ModelSelectStates

    await fsm.set_state(ModelSelectStates.choosing_provider)
    await fsm.update_data(session_id="s1")
    message = make_message(bot, text="/cancel")
    await on_cancel(message, state=fsm)
    assert await fsm.get_state() is None
    assert await fsm.get_data() == {}
    assert any("сброшено" in s for s in _texts(bot))


async def test_help_lists_commands(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.misc import on_help

    message = make_message(bot, text="/help")
    await on_help(message)
    sent = "\n".join(_texts(bot))
    for cmd in ("/help", "/new", "/sessions", "/model", "/agent", "/context", "/history"):
        assert cmd in sent


async def test_unknown_command_answers_friendly(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.misc import on_unknown_command

    message = make_message(bot, text="/definitely_not_a_command")
    await on_unknown_command(message)
    sent = "\n".join(_texts(bot))
    assert "Неизвестная команда /definitely_not_a_command" in sent
    assert "/help" in sent


async def test_unknown_command_preserves_arguments(bot: Bot) -> None:
    from kilocode_tg_bot.handlers.misc import on_unknown_command

    message = make_message(bot, text="/unknowncmd with args")
    await on_unknown_command(message)
    sent = "\n".join(_texts(bot))
    assert "Неизвестная команда /unknowncmd" in sent
