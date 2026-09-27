"""Permission requests: reply Once/Always/Reject, list pending, allow-all."""

from __future__ import annotations

import html

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from kilocode_client import Kilo

from kilocode_tg_bot.handlers.common import call_kilo, editable_message
from kilocode_tg_bot.keyboards.inline import PermissionReplyCD, permission_keyboard

router = Router(name="permissions")


@router.callback_query(PermissionReplyCD.filter())
async def on_permission_reply(
    callback: CallbackQuery, callback_data: PermissionReplyCD, kilo: Kilo
) -> None:
    msg = editable_message(callback)
    if msg is None:
        await callback.answer("Сообщение недоступно")
        return
    ok = await call_kilo(
        lambda: kilo.permission.reply(callback_data.request_id, callback_data.reply),
        msg,
    )
    label = {"once": "Once", "always": "Always", "reject": "Reject"}.get(
        callback_data.reply, callback_data.reply
    )
    if ok is None:
        return
    await callback.answer(f"Ответ: {html.escape(label)}")
    try:
        await msg.edit_text(f"🔐 Разрешение отвечено: {label}.", reply_markup=None)
    except Exception:  # noqa: BLE001 - message may already be edited
        pass


@router.message(Command("permissions"))
async def on_permissions(message: Message, kilo: Kilo) -> None:
    pending = await call_kilo(lambda: kilo.permission.list_pending(), message)
    if pending is None:
        return
    if not pending:
        await message.answer("Ожидающих запросов на разрешение нет.")
        return
    count = 0
    for item in pending:
        request_id = item.get("id") if isinstance(item, dict) else None
        if not request_id:
            continue
        permission = (
            item.get("permission") if isinstance(item, dict) else getattr(item, "permission", None)
        )
        text = (
            f"🔐 Запрос разрешения (id `{request_id}`)"
            + (f"\nДействие: {permission}" if permission else "")
            + (f"\nКаналы: {', '.join(item.get('patterns', []))}" if isinstance(item, dict) else "")
        )
        await message.answer(text, reply_markup=permission_keyboard(request_id))
        count += 1
    if count == 0:
        await message.answer("Ожидающих запросов нет.")


@router.message(Command("allow_all"))
async def on_allow_all(message: Message, command: CommandObject, kilo: Kilo) -> None:
    arg = (command.args or "").strip().lower()
    if arg in ("on", "1", "yes", "да", "true"):
        enable = True
    elif arg in ("off", "0", "no", "нет", "false"):
        enable = False
    else:
        await message.answer("Использование: /allow_all <on|off>")
        return
    ok = await call_kilo(lambda: kilo.permission.allow_everything(enable), message)
    if ok is None:
        return
    state = "включено" if enable else "выключено"
    await message.answer(f"⚠️ Разрешить все запросы автоматически: {state}.")


__all__ = ["router"]
