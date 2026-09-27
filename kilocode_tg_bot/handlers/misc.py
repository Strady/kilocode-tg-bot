"""Miscellaneous: server health and FSM/stream reset (cancel)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from kilocode_client import Kilo

router = Router(name="misc")


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


__all__ = ["router"]
