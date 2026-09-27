"""Fixtures for integration tests against a real ``kilo serve``.

These tests are marked ``live`` and run only when a Kilo headless server is
reachable. Reading ``KILO_SERVER_URL``/``KILO_SERVER_USERNAME``/``KILO_SERVER_PASSWORD``
from the environment, they build a real :class:`kilocode_client.Kilo`, probe
``health()``, and skip the whole module if the server is down. Telegram remains
fully mocked (recording session) — only the Kilo dependency is real, so the whole
chain middleware → handler → real client → real server is exercised.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from kilocode_client import Kilo
from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.handlers import (
    chat,
    export_import,
    misc,
    model_agent,
    permissions,
    sessions,
    start,
    tools,
)
from kilocode_tg_bot.middlewares.auth import AuthMiddleware
from kilocode_tg_bot.middlewares.context import ContextMiddleware
from kilocode_tg_bot.state.session_store import SessionStore

LIVE_OWNER_ID = 42

SERVER_URL = os.getenv("KILO_SERVER_URL", "http://127.0.0.1:4096")
SERVER_USERNAME = os.getenv("KILO_SERVER_USERNAME") or None
SERVER_PASSWORD = os.getenv("KILO_SERVER_PASSWORD") or None


async def _server_available(client: Kilo) -> bool:
    try:
        await client.health()
        return True
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


@pytest.fixture(scope="function")
async def real_kilo() -> AsyncGenerator[Kilo, None]:
    """A real :class:`Kilo` client, or skip-all if the server is unreachable.

    Function-scoped on purpose: a persistent Kilo connection would otherwise bind
    HTTP primitives to one event loop while pytest-asyncio gives each test its
    own loop (``RuntimeError: bound to a different event loop``). Recreating the
    client per test keeps everything on the test's own loop.
    """
    client = Kilo(
        base_url=SERVER_URL,
        username=SERVER_USERNAME,
        password=SERVER_PASSWORD,
    )
    if not await _server_available(client):
        await client.close()
        pytest.skip(
            f"Kilo server not reachable at {SERVER_URL}; "
            "start it with: kilo serve --port 4096 (live tests skipped)"
        )
    yield client
    await client.close()


@pytest.fixture
async def live_store(tmp_path) -> AsyncGenerator[SessionStore, None]:
    store = SessionStore(str(tmp_path / "live.db"))
    await store.open()
    yield store
    await store.close()


@pytest.fixture
async def live_dispatcher(
    real_kilo: Kilo, live_store: SessionStore
) -> AsyncGenerator[tuple[Bot, Dispatcher, Any, Any], None]:
    """Bot+Dispatcher wired with the real Kilo (Telegram still mocked)."""
    from kilocode_tg_bot.handlers import (
        misc as _misc,  # noqa: F401  (router reset in root conftest)
    )

    dp = Dispatcher(storage=MemoryStorage())
    settings = Settings(
        telegram_bot_token="123456:TEST-TOKEN",
        telegram_allowed_user_id=LIVE_OWNER_ID,
        kilo_server_url=SERVER_URL,
    )

    from tests.fakes.fake_telegram import RecordingSession, make_bot

    rec = RecordingSession()
    bot = make_bot(rec)
    dp.update.outer_middleware(AuthMiddleware(LIVE_OWNER_ID))
    dp.update.outer_middleware(ContextMiddleware(settings, live_store, real_kilo, bot))
    for module in (start, sessions, chat, permissions, model_agent, tools, export_import, misc):
        dp.include_router(module.router)

    yield bot, dp, rec, live_store


async def feed(dp: Dispatcher, bot: Bot, update: dict[str, Any]) -> Any:
    """Run a raw update through the real dispatcher on the caller's event loop.

    Must be awaited from the same (pytest-asyncio) loop the Kilo client lives on;
    do not wrap it in ``asyncio.run`` or the shared real client will trip a
    "bound to a different event loop" error.
    """
    return await dp.feed_raw_update(bot=bot, update=update)
