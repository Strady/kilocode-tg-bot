"""Send model content to Telegram as HTML with a plain-text fallback.

Model output is markdown; Telegram does not understand markdown, so content is
converted to Telegram's HTML subset (see :mod:`kilocode_tg_bot.formatting`)
and sent with ``parse_mode=HTML``.

Telegram can still reject the HTML on an edge case the converter did not
predict (``TelegramBadRequest: can't parse entities``). When that happens the
*same* content is re-sent as plain text (``parse_mode=None``) so the user is
never left without a reply, and the original markdown + converted HTML + error
are logged for later converter fixes.

These helpers accept an arbitrary "send" callable so they work for both outgoing
messages (``message.answer`` / ``message.reply``) and streamed edits
(``message.edit_text``): each takes ``(text, parse_mode=..., **kwargs)``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.exceptions import TelegramBadRequest

from kilocode_tg_bot.formatting.markdown_to_tg_html import markdown_to_telegram_html

logger = logging.getLogger(__name__)


async def send_html(
    sender: Callable[..., Awaitable[Any]],
    source: str,
    *,
    reply_markup: Any = None,
    fallback_reply_markup: Any = None,
    **kwargs: Any,
) -> Any:
    """Convert ``source`` (markdown) and send it via ``sender`` as HTML.

    On ``can't parse entities`` the content is re-sent as plain text and the
    event is logged. ``sender`` is typically ``message.answer``, ``message.reply``
    or ``message.edit_text``. Extra ``kwargs`` are forwarded to ``sender``.
    """
    html = markdown_to_telegram_html(source)
    try:
        return await sender(html, parse_mode="HTML", reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest as exc:
        if _is_not_modified(exc):
            # Editing a message to exactly the same content/keyboard is a no-op;
            # Telegram rejects it with ``message is not modified``. Swallow it so a
            # streamed follow-up edit (turn close, Stop, redundant finalise) never
            # surfaces as an error.
            return None
        if not _is_parse_error(exc):
            raise
        logger.warning(
            "Telegram rejected converted HTML; falling back to plain text. "
            "markdown=%r html=%r error=%s",
            source,
            html,
            exc,
        )
        return await sender(source, parse_mode=None, reply_markup=fallback_reply_markup, **kwargs)


def _is_parse_error(exc: TelegramBadRequest) -> bool:
    return "can't parse entities" in str(getattr(exc, "message", "") or str(exc)).lower()


def _is_not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in str(getattr(exc, "message", "") or str(exc)).lower()


__all__ = ["send_html"]
