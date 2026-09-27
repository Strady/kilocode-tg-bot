"""Miscellaneous: help, server health, FSM/stream reset (cancel), unknown commands."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from kilocode_client import Kilo

router = Router(name="misc")

HELP_TEXT = "\n".join(
    [
        "📚 Доступные команды:",
        "/help — этот список",
        "/new [title] — новая сессия",
        "/sessions /switch — список сессий / выбор активной",
        "/delete — удалить сессию",
        "/rename — переименовать сессию",
        "/fork — форк сессии",
        "/model — сменить модель",
        "/agent — сменить агента",
        "/context — контекст активной сессии",
        "/compact — сжать контекст",
        "/todo — todo-список сессии",
        "/run <slash> — slash-команда",
        "/shell <cmd> — shell-команда (с подтверждением)",
        "/history /messages — переписка сессии",
        "/export /import — экспорт/импорт сессии",
        "/permissions /allow_all — права доступа",
        "/health — статус сервера",
        "/cancel — сбросить состояние диалога",
        "",
        "Просто напишите текст — он уйдёт в активную сессию.",
    ]
)


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("health"))
async def on_health(message: Message, kilo: Kilo) -> None:
    try:
        status = await kilo.health()
    except Exception as exc:  # noqa: BLE001
        from kilocode_tg_bot.services.kilo import humanize_error

        await message.answer(f"⚠️ Сервер Kilo недоступен: {humanize_error(exc)}")
        return
    pieces = [f"{k}: {v}" for k, v in status.items()]
    await message.answer("✅ Сервер Kilo отвечает.\n" + "\n".join(pieces[:20]))


@router.message(Command("cancel"))
async def on_cancel(message: Message, state: FSMContext) -> None:
    if state is not None:
        await state.clear()
    await message.answer(
        "Состояние диалога сброшено. Активная генерация не остановлена, используйте ⏹ Stop."
    )


# Registered last so specific ./commands in this and earlier routers win; any
# remaining /-prefixed text that matched no handler is an unknown command.
@router.message(F.text.regexp(r"^/\S+"))
async def on_unknown_command(message: Message) -> None:
    name = message.text.split()[0] if message.text else "/?"
    await message.answer(
        f"❓ Неизвестная команда {name}. Введите /help, чтобы увидеть список доступных команд."
    )


__all__ = ["router", "HELP_TEXT"]
