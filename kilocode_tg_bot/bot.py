"""Bot entry point: build Dispatcher, register routers/middlewares, run polling."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from kilocode_tg_bot.config import load_settings
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
from kilocode_tg_bot.services import kilo as kilo_service
from kilocode_tg_bot.services.telegram_session import build_session
from kilocode_tg_bot.state.session_store import SessionStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RESTART_COMMANDS = {"/new", "/sessions", "/model", "/agent"}


def build_dispatcher(settings) -> tuple[Bot, Dispatcher, SessionStore]:
    """Construct the full app graph for tests and the CLI runner."""
    bot = Bot(
        token=settings.telegram_bot_token,
        session=build_session(settings),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    store = SessionStore(settings.session_store_path)
    kilo = kilo_service.get_client(settings)

    dp.startup.register(_startup(store))
    dp.shutdown.register(_shutdown(store))

    # Order matters: auth must reject foreign updates before any other logic.
    dp.update.outer_middleware(AuthMiddleware(settings.telegram_allowed_user_id))
    dp.update.outer_middleware(ContextMiddleware(settings, store, kilo))

    for module in (start, sessions, chat, permissions, model_agent, tools, export_import, misc):
        dp.include_router(module.router)

    return bot, dp, store


def _startup(store: SessionStore):
    async def _on_startup(dispatcher: Dispatcher) -> None:
        await store.open()
        logger.info("SessionStore opened")

    return _on_startup


def _shutdown(store: SessionStore):
    async def _on_shutdown(dispatcher: Dispatcher) -> None:
        await kilo_service.close_client()
        await store.close()
        logger.info("Kilo client closed; SessionStore closed")

    return _on_shutdown


async def main() -> None:
    settings = load_settings()
    settings.require_token()
    bot, dp, store = build_dispatcher(settings)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        with suppress(Exception):
            await store.close()
            await kilo_service.close_client()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
