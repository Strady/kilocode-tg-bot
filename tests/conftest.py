"""Shared pytest fixtures for offline (levels 1-3) bot tests.

Everything here is network-free: no real ``api.telegram.org`` and no real
``kilo serve``. The Telegram transport is a :class:`RecordingSession` and the
Kilo dependency is a :class:`FakeKilo`, so `pytest -m "not live"` runs in a clean
CI environment.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

OWNER_ID = 42


@pytest.fixture(autouse=True)
def _reset_routers() -> None:
    """Detach the shared handler routers before each test.

    The handler ``Router`` objects are module singletons; once ``include_router``
    attaches one to a ``Dispatcher`` it cannot be attached again. Resetting the
    internal ``_parent_router`` lets each test build a fresh dispatcher without
    "Router is already attached" errors.
    """
    for module in (start, sessions, chat, permissions, model_agent, tools, export_import, misc):
        router = getattr(module, "router", None)
        if router is not None:
            router._parent_router = None


@pytest.fixture
def settings() -> Settings:
    return Settings(
        telegram_bot_token="123456:TEST-TOKEN",
        telegram_allowed_user_id=OWNER_ID,
        kilo_server_url="http://127.0.0.1:4096",
        session_store_path=":memory:",
    )


@pytest.fixture
async def store(tmp_path: Path) -> AsyncGenerator[SessionStore, None]:
    db_path = str(tmp_path / "state.db")
    store = SessionStore(db_path)
    await store.open()
    yield store
    await store.close()


@pytest.fixture
def fake_kilo():
    from tests.fakes.fake_kilo import FakeKilo

    return FakeKilo()


@pytest.fixture
def bot() -> Bot:
    from tests.fakes.fake_telegram import make_bot

    return make_bot()


def _build_dispatcher(
    settings: Settings, store: SessionStore, kilo: Any
) -> tuple[Bot, Dispatcher, Any]:
    from tests.fakes.fake_telegram import RecordingSession, make_bot

    rec = RecordingSession()
    bot = make_bot(rec)
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(AuthMiddleware(settings.telegram_allowed_user_id))
    dp.update.outer_middleware(ContextMiddleware(settings, store, kilo))
    for module in (start, sessions, chat, permissions, model_agent, tools, export_import, misc):
        dp.include_router(module.router)
    return bot, dp, rec


@pytest.fixture
def dispatcher(
    settings: Settings, store: SessionStore, fake_kilo: Any
) -> tuple[Bot, Dispatcher, Any]:
    return _build_dispatcher(settings, store, fake_kilo)


@pytest.fixture
def make_message(bot: Bot) -> Callable[..., Message]:
    from tests.fakes.fake_telegram import make_message as _make_message

    def wrapper(**kwargs: Any) -> Message:
        kwargs.setdefault("bot", bot)
        return _make_message(**kwargs)

    return wrapper


@pytest.fixture
def make_callback(bot: Bot) -> Callable[..., CallbackQuery]:
    from tests.fakes.fake_telegram import make_callback as _make_callback

    def wrapper(**kwargs: Any) -> CallbackQuery:
        kwargs.setdefault("bot", bot)
        return _make_callback(**kwargs)

    return wrapper


@pytest.fixture
async def active_store(store: SessionStore) -> AsyncGenerator[tuple[SessionStore, str], None]:
    """A store pre-populated with an active session id, plus that session id."""
    await store.set_active(OWNER_ID, "session-01")
    yield store, "session-01"


@pytest.fixture
def make_command() -> Callable[..., Any]:
    from aiogram.filters import CommandObject

    def wrapper(args: str | None = None, command: str = "") -> Any:
        return CommandObject(command=command, args=args)

    return wrapper


@pytest.fixture
def fsm() -> Any:
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=200, user_id=42))


# -- re-exports for downstream convenience --------------------------------------


__all__ = [
    "OWNER_ID",
    "settings",
    "store",
    "fake_kilo",
    "bot",
    "dispatcher",
    "make_message",
    "make_callback",
    "active_store",
    "make_command",
    "fsm",
]
