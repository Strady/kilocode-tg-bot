"""Unit tests for the HTML send + plain-text fallback path.

``send_html`` converts markdown to Telegram HTML and sends with ``parse_mode=HTML``;
when Telegram rejects it with ``can't parse entities`` the same content is re-sent
as plain text (``parse_mode=None``) so the user never goes without a reply.
"""

from __future__ import annotations

from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage


def _make_error(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(
        method=SendMessage(chat_id=1, text="x"),
        message=message,
    )


def _parse_error() -> TelegramBadRequest:
    return _make_error("Bad Request: can't parse entities")


async def _recording_sender(*, fail_first: bool = False) -> tuple[Any, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def _record(
        text: str, parse_mode: str | None, reply_markup: Any, kwargs: dict[str, Any]
    ) -> None:
        calls.append(
            {
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "kwargs": kwargs,
            }
        )

    async def sender(
        text: str, *, parse_mode: str | None = None, reply_markup: Any = None, **kwargs: Any
    ) -> None:
        if fail_first and not calls:
            _record(text, parse_mode, reply_markup, kwargs)
            raise _parse_error()
        _record(text, parse_mode, reply_markup, kwargs)

    return sender, calls


async def test_send_html_converts_and_uses_html_parse_mode() -> None:
    from kilocode_tg_bot.services.telegram_sender import send_html

    sender, calls = await _recording_sender()
    await send_html(sender, "**bold**")
    assert len(calls) == 1
    assert calls[0]["text"] == "<b>bold</b>"
    assert calls[0]["parse_mode"] == "HTML"


async def test_fallback_resends_plain_on_parse_error() -> None:
    from kilocode_tg_bot.services.telegram_sender import send_html

    sender, calls = await _recording_sender(fail_first=True)
    await send_html(sender, "**bold** &&")
    assert len(calls) == 2
    # first attempt: converted HTML with parse_mode=HTML
    assert calls[0]["parse_mode"] == "HTML"
    assert calls[0]["text"] == "<b>bold</b> &amp;&amp;"
    # second attempt: original source, no parse mode
    assert calls[1]["parse_mode"] is None
    assert calls[1]["text"] == "**bold** &&"


async def test_non_parse_errors_propagate() -> None:
    from kilocode_tg_bot.services.telegram_sender import send_html

    async def sender(text: str, **kwargs: Any) -> None:
        raise _make_error("Bad Request: message is too long")

    with pytest.raises(TelegramBadRequest):
        await send_html(sender, "plain text")


async def test_not_modified_is_swallowed() -> None:
    from kilocode_tg_bot.services.telegram_sender import send_html

    called = False

    async def sender(text: str, **kwargs: Any) -> None:
        nonlocal called
        called = True
        raise _make_error("Bad Request: message is not modified: specified new message content")

    result = await send_html(sender, "same content")
    # identical edit is a benign no-op: returned without raising and without fallback
    assert called is True
    assert result is None


async def test_fallback_forwards_reply_markup_and_kwargs() -> None:
    from kilocode_tg_bot.services.telegram_sender import send_html

    sender, calls = await _recording_sender(fail_first=True)
    await send_html(
        sender,
        "*x*",
        reply_markup="KB",
        fallback_reply_markup="KB_PLAIN",
        reply_to_message_id=7,
    )
    # the HTML attempt used the provided keyboard and forwarded kwargs
    assert calls[0]["reply_markup"] == "KB"
    assert calls[0]["kwargs"] == {"reply_to_message_id": 7}
    # the plain fallback preferred fallback_reply_markup and kept kwargs
    assert calls[1]["reply_markup"] == "KB_PLAIN"
    assert calls[1]["kwargs"] == {"reply_to_message_id": 7}
