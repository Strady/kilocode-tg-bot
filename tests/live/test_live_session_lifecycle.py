"""Live lifecycle test: create → prompt/stream → list → delete against real
``kilo serve``, driven through the real dispatcher (Telegram still mocked)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from kilocode_client import Kilo
from kilocode_client.events import text_delta_of
from tests.live.conftest import feed


def _sent(rec: Any) -> list[str]:
    return [c.text() for c in rec.method_calls("sendMessage")]


def _edits(rec: Any) -> list[str]:
    return [c.text() for c in rec.method_calls("editMessageText")]


@pytest.mark.live
async def test_live_session_lifecycle_through_dispatcher(
    live_dispatcher: tuple[Bot, Dispatcher, Any, Any], real_kilo: Kilo
) -> None:
    bot, dp, rec, store = live_dispatcher
    # create through the real server via the dispatcher
    await feed(dp, bot, {"update_id": 1, "message": _raw_msg(42, "/new Lifecycle")})
    active = await store.get_active(42)
    assert active is not None, "a real session should have been created and activated"

    try:
        # /sessions lists it
        await feed(dp, bot, {"update_id": 2, "message": _raw_msg(42, "/sessions")})
        assert any("Доступно сессий" in s for s in _sent(rec))

        # /delete asks first, then confirm removes it
        await feed(dp, bot, {"update_id": 3, "message": _raw_msg(42, "/delete")})
        await feed(
            dp,
            bot,
            {
                "update_id": 4,
                "callback_query": _raw_callback(42, data=f"sdel:yes:{active}"),
            },
        )
        assert await store.get_active(42) is None
    finally:
        # never leave a stray session on the real server
        try:
            await real_kilo.session.delete(active)
        except Exception:  # noqa: BLE001 - cleanup best effort
            pass


@pytest.mark.live
async def test_live_prompt_streams_text(real_kilo: Kilo) -> None:
    """The real Kilo's subscribe-then-send path yields text against a real server.

    This exercises the exact same streaming surface the bot's chat handler uses,
    proving the SSE event format the server emits is what the bot expects.
    """
    session = await real_kilo.session.create(title="stream-check")
    try:
        stream = await real_kilo.stream_session_events(session.id)

        async def send() -> None:
            await asyncio.sleep(0.3)
            await real_kilo.send_prompt_async(session.id, "Reply with the word PONG only.")

        sender = asyncio.create_task(send())
        chunks: list[str] = []
        seen_turn_close = False
        try:
            async for event in stream:
                if delta := text_delta_of(event):
                    chunks.append(delta)
                if getattr(event, "is_turn_close", False):
                    seen_turn_close = True
                    break
        finally:
            if not sender.done():
                sender.cancel()
        # A real server should stream at least one text delta and close the turn.
        assert chunks, "expected at least one streamed text delta from the real server"
        assert seen_turn_close, "expected a turn-close event from the real server"
    finally:
        try:
            await real_kilo.session.delete(session.id)
        except Exception:  # noqa: BLE001 - best effort
            pass


def _raw_msg(user_id: int, text: str) -> dict[str, Any]:
    return {
        "message_id": 1,
        "date": 0,
        "text": text,
        "entities": [{"offset": 0, "length": len(text), "type": "bot_command", "url": None}],
        "chat": {"id": 200, "type": "private", "first_name": "Owner", "username": "owner"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Owner", "username": "owner"},
    }


def _raw_callback(user_id: int, data: str) -> dict[str, Any]:
    return {
        "id": f"cq-{data}",
        "from": {"id": user_id, "is_bot": False, "first_name": "Owner", "username": "owner"},
        "chat_instance": "ci1",
        "data": data,
        "message": {
            "message_id": 999,
            "date": 0,
            "text": "base",
            "chat": {"id": 200, "type": "private"},
        },
    }
