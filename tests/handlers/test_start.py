"""Handler-level tests for the ``/start`` greeting."""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot
from kilocode_client import Kilo, SessionInfo
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_message, records


async def test_start_shows_command_list(bot: Bot, fake_kilo: Any, store: Any) -> None:
    from kilocode_tg_bot.handlers.start import on_start

    message = make_message(bot, text="/start")
    await on_start(
        message,
        kilo=cast(Kilo, fake_kilo),
        store=store,
        settings=_settings(),
    )
    sent = _texts(bot)
    assert any("Доступные команды" in s for s in sent)


async def test_start_reports_no_active_session(
    bot: Bot, fake_kilo: Any, store: Any
) -> None:
    from kilocode_tg_bot.handlers.start import on_start

    message = make_message(bot, text="/start")
    await on_start(
        message,
        kilo=cast(Kilo, fake_kilo),
        store=store,
        settings=_settings(),
    )
    assert any("не выбрана" in s for s in _texts(bot))


async def test_start_shows_active_session_title(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.start import on_start

    session: SessionInfo = fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, session.id, session.title)

    message = make_message(bot, text="/start")
    await on_start(
        message,
        kilo=cast(Kilo, fake_kilo),
        store=store,
        settings=_settings(),
    )
    assert any("Активная сессия" in s and "demo" in s for s in _texts(bot))


def _settings() -> Any:
    from kilocode_tg_bot.config import Settings

    return Settings(telegram_bot_token="123456:TEST-TOKEN", telegram_allowed_user_id=42)


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]
