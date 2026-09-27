"""Smoke test that the application graph assembles without errors."""

from __future__ import annotations

import pytest
from kilocode_tg_bot.bot import build_dispatcher
from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.handlers import chat, sessions


@pytest.mark.asyncio
async def test_dispatcher_assembles():
    settings = Settings(
        telegram_bot_token="123456:TESTTOKEN",
        telegram_allowed_user_id=42,
        kilo_server_url="http://127.0.0.1:4096",
        _env_file=None,
    )
    bot, dp, store = build_dispatcher(settings)
    try:
        await store.open()
        names = {r.name for r in dp.sub_routers}
        expected = {
            "start",
            "sessions",
            "chat",
            "permissions",
            "model_agent",
            "tools",
            "export_import",
            "misc",
        }
        assert names >= expected
        # The router wiring works: chat handler is the streaming path.
        assert chat.router is not None
        assert sessions.router is not None
    finally:
        await store.close()
        await bot.session.close()


def test_settings_require_owner():
    with pytest.raises(ValueError):
        Settings(_env_file=None)
