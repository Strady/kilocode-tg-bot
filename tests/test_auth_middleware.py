"""Unit tests for the authorization middleware.

Every other feature of the bot depends on this gate: foreign updates must be
dropped before any handler sees them. We exercise the middleware against
lightweight stand-ins because constructing real aiogram ``Update`` objects is
heavyweight.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from aiogram.types import Update
from kilocode_tg_bot.middlewares.auth import AuthMiddleware, _extract_user


def _make_update(**payload: Any) -> Update:
    """A lightweight stand-in for an ``Update`` (duck-typed by the middleware)."""
    base: dict[str, Any] = {
        "update_id": 1,
        "message": None,
        "edited_message": None,
        "channel_post": None,
        "edited_channel_post": None,
        "business_message": None,
        "edited_business_message": None,
        "callback_query": None,
        "inline_query": None,
    }
    base.update(payload)
    return cast(Update, SimpleNamespace(**base))


async def _dummy_handler(event, data):  # pragma: no cover - only reached for allowed users
    return ("handled", data)


def test_allowed_message_passes():
    user = SimpleNamespace(id=42, username="owner")
    msg = SimpleNamespace(from_user=user)
    mw = AuthMiddleware(allowed_user_id=42)
    update = _make_update(message=msg)

    async def run():
        result = await mw(_dummy_handler, update, {})
        assert result == ("handled", {})

    import asyncio

    asyncio.run(run())


def test_foreign_message_blocked():
    user = SimpleNamespace(id=999, username="stranger")
    msg = SimpleNamespace(from_user=user)
    mw = AuthMiddleware(allowed_user_id=42)
    update = _make_update(message=msg)

    async def run():
        result = await mw(_dummy_handler, update, {})
        assert result is None

    import asyncio

    asyncio.run(run())


def test_callback_from_foreign_user_blocked():
    user = SimpleNamespace(id=1, username="x")
    cq = SimpleNamespace(from_user=user)
    mw = AuthMiddleware(allowed_user_id=42)
    update = _make_update(callback_query=cq)

    async def run():
        result = await mw(_dummy_handler, update, {})
        assert result is None

    import asyncio

    asyncio.run(run())


def test_inline_query_from_allowed_user_passes():
    user = SimpleNamespace(id=42, username="owner")
    iq = SimpleNamespace(from_user=user)
    mw = AuthMiddleware(allowed_user_id=42)
    update = _make_update(inline_query=iq)

    async def run():
        result = await mw(_dummy_handler, update, {})
        assert result == ("handled", {})

    import asyncio

    asyncio.run(run())


def test_extract_user_none():
    assert _extract_user(_make_update()) is None
