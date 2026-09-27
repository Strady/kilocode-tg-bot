"""Inline keyboard builders.

All interactive choices the bot presents live here as structured callback data
(``aiogram.utils.keyboard.InlineKeyboardBuilder`` + ``CallbackData`` factories),
so handlers can decode a pressed button into typed arguments instead of parsing
free-form callback strings.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# -- factory data classes -----------------------------------------------------


class SessionSelectCD(CallbackData, prefix="ssess"):
    action: str  # "set" | "delete"
    session_id: str


class HistoryNavCD(CallbackData, prefix="shist"):
    session_id: str
    offset: int
    direction: str  # "next" | "prev"


class ModelProviderCD(CallbackData, prefix="sprov"):
    provider_index: int
    provider_id: str


class ModelSelectCD(CallbackData, prefix="smodel"):
    provider_id: str
    model_index: int
    model_id: str
    agent: str = ""


class AgentSelectCD(CallbackData, prefix="sagent"):
    agent_index: int
    agent_name: str


class PermissionReplyCD(CallbackData, prefix="sperm"):
    request_id: str
    reply: str


class ShellConfirmCD(CallbackData, prefix="sshell"):
    action: str  # "run" | "cancel"


class DeleteConfirmCD(CallbackData, prefix="sdel"):
    action: str  # "yes" | "no"
    session_id: str


# -- builders -----------------------------------------------------------------


def _session_label(session_id: str, title: str | None) -> str:
    safe = html.escape(title or "untitled")
    return f"{safe} ({session_id[:8]})"


def sessions_keyboard(
    sessions: Sequence[object],
    get_id: callable,
    get_title: callable,
    with_delete: bool = False,
) -> InlineKeyboardMarkup:
    """Build a list of sessions as buttons; each sets it active. Requires
    ``get_id`` / ``get_title`` callables to adapt pg-model attrs without a hard
    dependency on their schema.
    """
    builder = InlineKeyboardBuilder()
    for session in sessions:
        sid = get_id(session)
        title = get_title(session)
        builder.row(
            InlineKeyboardButton(
                text=_session_label(sid, title),
                callback_data=SessionSelectCD(action="set", session_id=sid).pack(),
            )
        )
    return builder.as_markup()


def confirm_keyboard(
    yes_callback: CallbackData,
    no_callback: CallbackData,
    yes_text: str = "✅ Да",
    no_text: str = "❌ Нет",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=yes_text, callback_data=yes_callback.pack()),
        InlineKeyboardButton(text=no_text, callback_data=no_callback.pack()),
    )
    return builder.as_markup()


def history_pagination_keyboard(
    session_id: str, offset: int, has_prev: bool, has_next: bool
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    row: list[InlineKeyboardButton] = []
    if has_prev:
        row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=HistoryNavCD(
                    session_id=session_id, offset=offset, direction="prev"
                ).pack(),
            )
        )
    if has_next:
        row.append(
            InlineKeyboardButton(
                text="Далее ➡️",
                callback_data=HistoryNavCD(
                    session_id=session_id, offset=offset, direction="next"
                ).pack(),
            )
        )
    if row:
        builder.row(*row)
    return builder.as_markup()


def providers_keyboard(
    providers: list[dict], get_provider_id: callable, get_provider_name: callable
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, provider in enumerate(providers):
        builder.row(
            InlineKeyboardButton(
                text=get_provider_name(provider),
                callback_data=ModelProviderCD(
                    provider_index=index, provider_id=get_provider_id(provider)
                ).pack(),
            )
        )
    return builder.as_markup()


def models_keyboard(
    models: list[dict], provider_id: str, get_model_id: callable, get_model_name: callable
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, model in enumerate(models):
        builder.row(
            InlineKeyboardButton(
                text=get_model_name(model),
                callback_data=ModelSelectCD(
                    provider_id=provider_id,
                    model_index=index,
                    model_id=get_model_id(model),
                ).pack(),
            )
        )
    return builder.as_markup()


def agents_keyboard(
    agents: list[dict], get_agent_name: callable, current_agent: str | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, agent in enumerate(agents):
        name = get_agent_name(agent)
        label = f"⭐ {name}" if current_agent and name == current_agent else name
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=AgentSelectCD(agent_index=index, agent_name=name).pack(),
            )
        )
    return builder.as_markup()


def permission_keyboard(request_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for reply, label in (("once", "✅ Once"), ("always", "♾ Always"), ("reject", "🚫 Reject")):
        builder.button(
            text=label,
            callback_data=PermissionReplyCD(request_id=request_id, reply=reply),
        )
    builder.adjust(3)
    return builder.as_markup()
