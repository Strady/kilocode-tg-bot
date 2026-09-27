"""Utility/agent tools: compact, context, todo, run, shell (confirmed), revert, unrevert."""

from __future__ import annotations

from typing import Any

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from kilocode_client import Kilo

from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.handlers.common import call_kilo, editable_message, reply_text
from kilocode_tg_bot.keyboards.inline import ShellConfirmCD, confirm_keyboard
from kilocode_tg_bot.state.session_store import SessionStore
from kilocode_tg_bot.state.states import ShellPendingStates

router = Router(name="tools")


async def _active_id(store: SessionStore, message: Message) -> str | None:
    user_id = message.from_user.id if message.from_user else 0
    return await store.get_active(user_id)


@router.message(Command("compact"))
async def on_compact(message: Message, kilo: Kilo, store: SessionStore, settings: Settings) -> None:
    session_id = await _active_id(store, message)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    await message.answer(f"🗜 Сжимаю контекст `{session_id[:8]}`...")
    try:
        await kilo.compact_v2(session_id)
    except Exception as exc:  # noqa: BLE001
        from kilocode_tg_bot.services.kilo import humanize_error

        if hasattr(exc, "status_code"):
            await message.answer(humanize_error(exc))
        else:
            await message.answer(f"Ошибка: {exc}")
        return
    await message.answer("✅ Контекст сжат.")


@router.message(Command("context"))
async def on_context(message: Message, kilo: Kilo, store: SessionStore, settings: Settings) -> None:
    session_id = await _active_id(store, message)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    ctx = await call_kilo(lambda: kilo.get_context(session_id), message)
    if ctx is None:
        return
    if not ctx:
        await message.answer("В активном контексте после последнего сжатия сообщений нет.")
        return
    text = "\n\n".join(f"[{getattr(m, 'type', '?')}]\n{_ctx_text(m)}" for m in ctx)
    await reply_text(message, text, settings)


def _ctx_text(msg: Any) -> str:
    mtype = getattr(msg, "type", "")
    if mtype == "user":
        return getattr(msg, "text", "") or ""
    if mtype == "assistant":
        content = getattr(msg, "content", None) or []
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                chunks.append(part.get("text", ""))
        return "\n".join(chunks) or "(ассистент без текста)"
    if mtype == "compaction":
        return "Компакция: " + (getattr(msg, "summary", "") or "")
    return getattr(msg, "text", "") or f"<{mtype}>"


@router.message(Command("todo"))
async def on_todo(message: Message, kilo: Kilo, store: SessionStore) -> None:
    session_id = await _active_id(store, message)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    todos = await call_kilo(lambda: kilo.get_todos(session_id), message)
    if todos is None:
        return
    if not todos:
        await message.answer("В активной сессии todo-список пуст.")
        return
    lines = []
    for t in todos:
        mark = "☑" if getattr(t, "status", "") in ("completed", "done") else "☐"
        lines.append(f"{mark} {getattr(t, 'content', '')}")
    await message.answer("\n".join(lines))


@router.message(Command("run"))
async def on_run(message: Message, command: CommandObject, kilo: Kilo, store: SessionStore) -> None:
    session_id = await _active_id(store, message)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    args = (command.args or "").strip()
    if not args:
        await message.answer("Использование: /run <slash-команда> [аргументы]")
        return
    parts = args.split(maxsplit=1)
    slash = parts[0].lstrip("/")
    arguments = parts[1] if len(parts) > 1 else ""
    msg = await call_kilo(lambda: kilo.run_command(session_id, slash, arguments), message)
    if msg is None:
        return
    await _fmt_message_result(message, msg)


@router.message(Command("shell"))
async def on_shell(
    message: Message,
    command: CommandObject,
    kilo: Kilo,
    store: SessionStore,
    state: FSMContext,
) -> None:
    session_id = await _active_id(store, message)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    args = (command.args or "").strip()
    if not args:
        await message.answer("Использование: /shell <команда> [аргументы]")
        return
    parts = args.split(maxsplit=1)
    cmd = parts[0]
    arguments = parts[1] if len(parts) > 1 else ""
    await state.set_state(ShellPendingStates.confirming)
    await state.update_data(session_id=session_id, command=cmd, arguments=arguments)
    await message.answer(
        f"⚠️ Выполнить shell-команду на машине?\n\n`{cmd} {arguments}`".strip(),
        parse_mode="MarkdownV2",
        reply_markup=confirm_keyboard(
            ShellConfirmCD(action="run"), ShellConfirmCD(action="cancel")
        ),
    )


@router.callback_query(ShellConfirmCD.filter())
async def on_shell_confirm(
    callback: CallbackQuery,
    callback_data: ShellConfirmCD,
    kilo: Kilo,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    session_id = data.get("session_id")
    msg = editable_message(callback)
    if callback_data.action == "cancel" or not session_id:
        await state.clear()
        await callback.answer("Отменено")
        if msg is not None:
            await msg.edit_text("Shell-команда отменена.")
        return
    cmd = data.get("command", "")
    arguments = data.get("arguments", "")
    await callback.answer("Выполняю...")
    if msg is not None:
        await msg.edit_text(f"⚙️ Выполняю `{cmd} {arguments}`...".strip())
    result = (
        await call_kilo(lambda: kilo.run_shell(session_id, cmd, arguments), msg)
        if msg is not None
        else None
    )
    await state.clear()
    if result is not None and msg is not None:
        await _fmt_message_result(msg, result)


@router.message(Command("revert"))
async def on_revert(
    message: Message, command: CommandObject, kilo: Kilo, store: SessionStore
) -> None:
    session_id = await _active_id(store, message)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    args = (command.args or "").strip().split()
    message_id = args[0] if args else None
    part_id = args[1] if len(args) > 1 else None
    if not message_id:
        last = await _last_assistant_id(kilo, session_id, message)
        if last is None:
            await message.answer("Не нашли сообщение для отката. Укажите: /revert <message_id>")
            return
        message_id = last
    result = await call_kilo(lambda: kilo.revert(session_id, message_id, part_id), message)
    if result is None:
        return
    await message.answer(f"↩️ Откат применён к сообщению `{message_id[:8]}`.")


@router.message(Command("unrevert"))
async def on_unrevert(message: Message, kilo: Kilo, store: SessionStore) -> None:
    session_id = await _active_id(store, message)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    result = await call_kilo(lambda: kilo.unrevert(session_id), message)
    if result is None:
        return
    await message.answer("↪️ Откат отменён (unrevert).")


async def _last_assistant_id(kilo: Kilo, session_id: str, message: Message) -> str | None:
    messages = await call_kilo(lambda: kilo.list_messages(session_id, limit=20), message)
    if not messages:
        return None
    for m in reversed(list(messages)):
        if getattr(getattr(m, "info", None), "role", "") == "assistant":
            return m.info.id
    return None


async def _fmt_message_result(message: Message, msg: Any) -> None:
    parts = getattr(msg, "parts", None) or []
    text = "".join(getattr(p, "text", "") for p in parts if getattr(p, "type", "") == "text")
    if not text:
        text = f"(готово, сообщений в ответе: {len(parts)})"
    await message.answer(text[:3900] if len(text) > 3900 else text)


__all__ = ["router"]
