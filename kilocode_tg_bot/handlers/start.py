"""``/start`` — greeting and current active session overview."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from kilocode_client import Kilo

from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.handlers.common import call_kilo
from kilocode_tg_bot.state.session_store import SessionStore

router = Router(name="start")


@router.message(CommandStart())
async def on_start(message: Message, kilo: Kilo, store: SessionStore, settings: Settings) -> None:
    user_id = message.from_user.id if message.from_user else 0
    active_id = await store.get_active(user_id)

    lines = [
        "👋 Привет! Это пульт для KiloCode-сервера.",
        "",
        "Доступные команды:",
        "/new [title] — новая сессия",
        "/sessions — список сессий",
        "/switch — выбрать активную сессию",
        "/model — сменить модель",
        "/agent — сменить агента",
        "/run <slash> — slash-команда",
        "/shell <cmd> — shell-команда (с подтверждением)",
        "/history — переписка активной сессии",
        "/export /import — экспорт/импорт сессии",
        "/permissions /allow_all — права доступа",
        "/health — статус сервера",
        "Просто напишите текст — он уйдёт в активную сессию.",
    ]

    if active_id:
        session = await call_kilo(lambda: kilo.session.get(active_id), message)
        title = session.title if session else None
        lines.insert(2, f"\nАктивная сессия: {title or active_id} (id {active_id}).")
    else:
        lines.insert(2, "\nАктивная сессия не выбрана.")

    await message.answer("\n".join(lines))


__all__ = ["router"]
