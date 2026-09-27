"""Session management: create, list/switch, rename, delete (with confirm), fork."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from kilocode_client import Kilo
from kilocode_client.models import SessionInfo

from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.handlers.common import call_kilo, editable_message
from kilocode_tg_bot.keyboards.inline import (
    DeleteConfirmCD,
    SessionSelectCD,
    sessions_keyboard,
)
from kilocode_tg_bot.services.session_pin import refresh_session_pin
from kilocode_tg_bot.state.session_store import SessionStore

router = Router(name="sessions")


def _sid(s: SessionInfo) -> str:
    return s.id


def _title(s: SessionInfo) -> str | None:
    return s.title


def _stamp(s: SessionInfo) -> str:
    try:
        return datetime.fromtimestamp(s.time.updated / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return ""


async def _list_and_offer(message: Message, kilo: Kilo, handler: str, settings: Settings) -> None:
    sessions = await call_kilo(lambda: kilo.session.list_sessions(), message)
    if sessions is None:
        return
    if not sessions:
        await message.answer("Сессий пока нет. Создайте через /new [title].")
        return
    lines = [f"Доступно сессий: {len(sessions)}."]
    for s in sessions:
        marker = f"{_stamp(s)} · {_title(s) or s.id}"
        lines.append(f"• `{s.id[:8]}` {marker}")
    text = "\n".join(lines)
    await message.answer(text)
    kb = sessions_keyboard(sessions, _sid, _title, with_delete=False)
    await message.answer("Выберите сессию:", reply_markup=kb)


@router.message(Command("new"))
async def on_new(
    message: Message,
    command: CommandObject,
    kilo: Kilo,
    store: SessionStore,
    bot: Bot,
) -> None:
    title = command.args or None
    session = await call_kilo(lambda: kilo.session.create(title=title), message)
    if session is None:
        return
    user_id = message.from_user.id if message.from_user else 0
    await store.set_active(user_id, session.id, session.title)
    await refresh_session_pin(bot, store, kilo, user_id, message.chat.id)
    await message.answer(
        f"✅ Создана сессия `{session.id[:8]}` → активна. Title: {session.title!r}"
    )


@router.message(Command("sessions", "switch"))
async def on_sessions(message: Message, kilo: Kilo, settings: Settings) -> None:
    await _list_and_offer(message, kilo, "sessions", settings)


@router.callback_query(SessionSelectCD.filter(F.action == "set"))
async def on_pick(
    callback: CallbackQuery,
    callback_data: SessionSelectCD,
    store: SessionStore,
    bot: Bot,
    kilo: Kilo,
) -> None:
    user_id = callback.from_user.id
    await store.set_active(user_id, callback_data.session_id)
    msg = editable_message(callback)
    chat_id = msg.chat.id if msg is not None else None
    await refresh_session_pin(bot, store, kilo, user_id, chat_id)
    await callback.answer("Активная сессия обновлена")
    if msg is not None:
        await msg.edit_text(f"✅ Активная сессия: `{callback_data.session_id}`", reply_markup=None)


@router.message(Command("delete"))
async def on_delete(message: Message, kilo: Kilo, store: SessionStore) -> None:
    user_id = message.from_user.id if message.from_user else 0
    active_id = await store.get_active(user_id)
    if not active_id:
        await message.answer("Нет активной сессии для удаления.")
        return
    await message.answer(
        f"Удалить активную сессию `{active_id[:8]}`? Это действие необратимо.",
        reply_markup=delete_confirm(active_id),
    )


def delete_confirm(session_id: str) -> Any:
    from kilocode_tg_bot.keyboards.inline import confirm_keyboard

    return confirm_keyboard(
        DeleteConfirmCD(action="yes", session_id=session_id),
        DeleteConfirmCD(action="no", session_id=session_id),
        yes_text="❗ Удалить",
        no_text="Отмена",
    )


@router.callback_query(DeleteConfirmCD.filter())
async def on_delete_confirm(
    callback: CallbackQuery,
    callback_data: DeleteConfirmCD,
    kilo: Kilo,
    store: SessionStore,
    bot: Bot,
) -> None:
    user_id = callback.from_user.id
    msg = editable_message(callback)
    if callback_data.action == "no":
        await callback.answer("Отменено")
        if msg is not None:
            await msg.edit_text("Удаление отменено.")
        return
    if msg is None:
        await callback.answer("Сообщение недоступно")
        return
    ok = await call_kilo(lambda: kilo.session.delete(callback_data.session_id), msg)
    if ok is None:
        return
    current = await store.get_active(user_id)
    if current == callback_data.session_id:
        await store.clear(user_id)
        await refresh_session_pin(bot, store, kilo, user_id, msg.chat.id)
    await callback.answer("Сессия удалена")
    await msg.edit_text(f"🗑 Сессия `{callback_data.session_id[:8]}` удалена.")


@router.message(Command("rename"))
async def on_rename(
    message: Message,
    command: CommandObject,
    kilo: Kilo,
    store: SessionStore,
    bot: Bot,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    title = (command.args or "").strip()
    if not title:
        await message.answer("Использование: /rename <новое название>")
        return
    active_id = await store.get_active(user_id)
    if not active_id:
        await message.answer("Нет активной сессии.")
        return
    updated = await call_kilo(lambda: kilo.session.rename(active_id, title), message)
    if updated is None:
        return
    await store.set_active(user_id, active_id, updated.title)
    await refresh_session_pin(bot, store, kilo, user_id, message.chat.id)
    await message.answer(f"✅ Переименовано: `{updated.title}`")


@router.message(Command("fork"))
async def on_fork(
    message: Message,
    command: CommandObject,
    kilo: Kilo,
    store: SessionStore,
    bot: Bot,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    active_id = await store.get_active(user_id)
    if not active_id:
        await message.answer("Нет активной сессии.")
        return
    args = (command.args or "").strip()
    message_id = args or None
    new_session = await call_kilo(
        lambda: kilo.session.fork(active_id, message_id=message_id), message
    )
    if new_session is None:
        return
    await store.set_active(user_id, new_session.id, new_session.title)
    await refresh_session_pin(bot, store, kilo, user_id, message.chat.id)
    await message.answer(
        f"🪵 Форк создан: `{new_session.id[:8]}` → теперь активен."
        + (f" (на сообщении {message_id})" if message_id else "")
    )


__all__ = ["router"]
