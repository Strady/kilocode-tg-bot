"""Plain-text chat → streaming prompt into the active Kilo session.

The chat handler is the heart of the bot: an ordinary message is sent to the
active session, text deltas stream back into a single Telegram message (throttled
by :class:`~kilocode_tg_bot.services.streaming.EditThrottler`), tool calls and
permission requests surface as separate messages/buttons, and a "⏹ Stop" button
interrupts the run.

Only one run may be active per session at a time; a ``RunController`` guards that
and routes the Stop button to the right interrupt call.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from kilocode_client import Kilo

from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.handlers.common import call_kilo, editable_message
from kilocode_tg_bot.keyboards.inline import (
    HistoryNavCD,
    history_pagination_keyboard,
    permission_keyboard,
)
from kilocode_tg_bot.services.streaming import stream_prompt

logger = logging.getLogger(__name__)

router = Router(name="chat")

STOP_PREFIX = "stop_run"

_HIST_PAGE = 5


class RunController:
    """In-memory tracking of in-progress prompt streams per session.

    Prevents two prompts running concurrently in the same session and lets the
    Stop button cancel the stream by interrupting the server run.
    """

    def __init__(self) -> None:
        self._active: dict[str, RunHandle] = {}

    def is_running(self, session_id: str) -> bool:
        return session_id in self._active

    def start(self, session_id: str) -> RunHandle:
        handle = RunHandle()
        self._active[session_id] = handle
        return handle

    def finish(self, session_id: str, handle: RunHandle) -> None:
        if self._active.get(session_id) is handle:
            self._active.pop(session_id, None)

    def get(self, session_id: str) -> RunHandle | None:
        return self._active.get(session_id)

    def stop(self, session_id: str) -> bool:
        handle = self._active.get(session_id)
        if handle is None:
            return False
        handle.cancel()
        return True


class RunHandle:
    """A flags object signalling an active run wants to stop."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


controller = RunController()


def stop_keyboard(session_id: str) -> Any:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⏹ Stop",
        callback_data=f"{STOP_PREFIX}:{session_id}",
    )
    return builder.as_markup()


@router.message(F.text, ~F.text.startswith("/"))
async def on_chat(message: Message, kilo: Kilo, store: Any, settings: Settings) -> None:
    user_id = message.from_user.id if message.from_user else 0
    session_id = await store.get_active(user_id)
    if not session_id:
        await message.answer("Нет активной сессии. /new или /sessions.")
        return
    prompt = message.text or ""
    if controller.is_running(session_id):
        await message.answer(
            "В этой сессии уже идёт генерация. Дождитесь её окончания или нажмите ⏹ Stop."
        )
        return

    handle = controller.start(session_id)
    try:
        await _run_stream(message, kilo, session_id, prompt, settings, handle)
    finally:
        controller.finish(session_id, handle)


async def _run_stream(
    message: Message,
    kilo: Kilo,
    session_id: str,
    prompt: str,
    settings: Settings,
    handle: RunHandle,
) -> None:
    status = await message.answer(f"⏳ Отправляю в `{session_id[:8]}`...")
    if status is None:
        return

    keyboard = stop_keyboard(session_id)
    stream_msg = await message.answer("_", reply_markup=keyboard)
    if stream_msg is None:
        return

    async def flush(text: str) -> None:
        if handle.cancelled:
            return
        await stream_msg.edit_text(_cap(text), parse_mode=None, reply_markup=keyboard)

    async def on_tool(status_line: str) -> None:
        if handle.cancelled:
            return
        await message.answer(f"🔧 {status_line}")

    async def on_permission(request_id: str) -> None:
        if handle.cancelled:
            return
        await message.answer(
            "🔐 Требуется разрешение:", reply_markup=permission_keyboard(request_id)
        )

    async def on_turn_close() -> None:
        await stream_msg.edit_text(
            _cap(stream_msg.text or "(пустой ответ)"), reply_markup=None
        )

    try:
        final = await stream_prompt(
            kilo,
            session_id,
            prompt,
            flush=flush,
            on_tool=on_tool,
            on_permission=on_permission,
            on_turn_close=on_turn_close,
            edit_interval=settings.telegram_edit_throttle_seconds,
        )
        await stream_msg.edit_text(_cap(final or "(пустой ответ)"), reply_markup=None)
        await status.delete()
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        logger.exception("Streaming error")
        try:
            await message.answer(f"⚠️ Ошибка при обработке запроса: {exc}")
        except Exception:  # noqa: BLE001
            pass


def _cap(text: str, limit: int = 3900) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 4] + "\n\n…"


@router.callback_query(F.data.startswith(STOP_PREFIX))
async def on_stop(callback: CallbackQuery, kilo: Kilo) -> None:
    data = callback.data or ""
    session_id = data.split(":", 1)[1] if ":" in data else ""
    if not session_id:
        await callback.answer("Не удалось определить сессию")
        return
    msg = editable_message(callback)
    if not controller.is_running(session_id):
        await callback.answer("В этой сессии нет активной генерации")
        if msg is not None:
            await msg.edit_reply_markup(reply_markup=None)
        return
    if msg is not None:
        await call_kilo(lambda: kilo.interrupt(session_id), msg)
    handle = controller.get(session_id)
    if handle is not None:
        handle.cancel()
    await callback.answer("⏹ Останавливаю...")
    if msg is not None:
        await msg.edit_reply_markup(reply_markup=None)


@router.message(Command("history", "messages"))
async def on_history(message: Message, kilo: Kilo, store: Any, settings: Settings) -> None:
    user_id = message.from_user.id if message.from_user else 0
    session_id = await store.get_active(user_id)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    messages = await call_kilo(lambda: kilo.list_messages(session_id, limit=50), message)
    if messages is None:
        return
    if not messages:
        await message.answer("Сообщений в сессии нет.")
        return
    total = len(messages)
    start = max(0, total - _HIST_PAGE)
    await _render_history_page(message, kilo, settings, session_id, messages, start, total)


async def _render_history_page(
    message: Message,
    kilo: Kilo,
    settings: Settings,
    session_id: str,
    messages: list[Any],
    start: int,
    total: int,
) -> None:
    page = messages[start : start + _HIST_PAGE]
    lines = [f"История сессии `{session_id[:8]}` (msg {start + 1}–{start + len(page)} из {total}):"]
    for m in page:
        info = getattr(m, "info", None)
        role = getattr(info, "role", "?") if info else "?"
        m_id = getattr(info, "id", "?") if info else "?"
        text = _message_text(m)
        lines.append(f"· [`{m_id[:8]}`] **{role}**: {text[:120]}")
    await message.answer(
        "\n".join(lines),
        reply_markup=history_pagination_keyboard(
            session_id, start, start > 0, start + _HIST_PAGE < total
        ),
    )


@router.callback_query(HistoryNavCD.filter())
async def on_history_nav(
    callback: CallbackQuery,
    callback_data: HistoryNavCD,
    kilo: Kilo,
    settings: Settings,
) -> None:
    if callback.message is None:
        return
    msg = editable_message(callback)
    if msg is None:
        await callback.answer("Сообщение недоступно")
        return
    messages = await call_kilo(lambda: kilo.list_messages(callback_data.session_id, limit=50), msg)
    if messages is None:
        return
    total = len(messages)
    new_start = callback_data.offset
    if callback_data.direction == "next":
        new_start = min(total - _HIST_PAGE, new_start + _HIST_PAGE)
    else:
        new_start = max(0, new_start - _HIST_PAGE)
    new_start = max(0, min(new_start, max(0, total - _HIST_PAGE)))
    await _render_history_page(
        msg, kilo, settings, callback_data.session_id, messages, new_start, total
    )
    await callback.answer()


def _message_text(msg: Any) -> str:
    parts = getattr(msg, "parts", None) or []
    chunks = []
    for p in parts:
        ptype = getattr(p, "type", "")
        if ptype == "text":
            chunks.append(getattr(p, "text", ""))
        elif ptype == "tool":
            state = getattr(p, "state", None)
            status = getattr(state, "status", "?") if state else "?"
            tool = getattr(p, "tool", "")
            chunks.append(f"[tool {status}] {tool}")
    joined = "\n".join(c for c in chunks if c)
    return joined if joined else "(нет текста)"


__all__ = ["router", "controller", "stop_keyboard", "RunController"]
