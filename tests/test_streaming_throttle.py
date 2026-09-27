"""Unit tests for streaming throttling and the prompt streaming loop.

No Telegram API is involved: the throttle is tested directly, and ``stream_prompt``
is driven against a fake ``Kilo`` client yielding synthetic :class:`KiloEvent`
objects.
"""

from __future__ import annotations

import asyncio
import time

from kilocode_client import KiloEvent
from kilocode_tg_bot.services.streaming import EditThrottler, stream_prompt


def test_throttler_batches_within_interval():
    flushed: list[str] = []
    interval = 10.0  # big enough that a second flush within the test is suppressed

    async def flush(text: str) -> None:
        flushed.append(text)

    throttler = EditThrottler(flush, interval=interval)
    throttler._last_flush = time.monotonic()  # pretend we flushed just now

    async def run():
        throttler.push("He")
        throttler.push("llo")
        throttler.push(" world")
        await throttler.maybe_flush()
        assert flushed == []  # interval hasn't elapsed -> nothing flushed
        await throttler.flush_now()  # force
        assert flushed == ["Hello world"]  # all deltas concatenated into one flush

    asyncio.run(run())


def test_throttler_flushes_after_interval():
    flushed: list[str] = []
    interval = 0.0  # every maybe_flush is allowed

    async def flush(text: str) -> None:
        flushed.append(text)

    throttler = EditThrottler(flush, interval=interval)

    async def run():
        throttler.push("a")
        await throttler.maybe_flush()
        throttler.push("b")
        await throttler.maybe_flush()
        assert flushed == ["a", "b"]

    asyncio.run(run())


class _FakeKilo:
    """Minimal stand-in for :class:`Kilo` exposing the streaming surface."""

    def __init__(self, events: list[KiloEvent]) -> None:
        self._events = events
        self.sent: list[tuple[str, str]] = []

    async def stream_session_events(self, session_id: str, *, instance: bool = False):
        async def gen():
            for e in self._events:
                await asyncio.sleep(0)  # yield to the event loop so the sender runs
                yield e

        return gen()

    async def send_prompt_async(self, session_id: str, prompt: str) -> None:
        self.sent.append((session_id, prompt))


async def test_stream_prompt_concatenates_deltas_and_stops_on_turn_close():
    session = "sid-1"

    def delta(text: str) -> KiloEvent:
        return KiloEvent(
            type="message.part.delta",
            properties={"field": "text", "delta": text, "sessionID": session},
        )

    events = [
        delta("Hel"),
        delta("lo"),
        KiloEvent(type="session.turn.close", properties={"reason": "done", "sessionID": session}),
    ]
    kilo = _FakeKilo(events)

    final_text = await stream_prompt(
        kilo,
        session,
        "Hi",
        flush=lambda text: _noop(text),
        edit_interval=0.0,
        subscribe_settle=0.0,
    )
    assert "Hel" in final_text and "lo" in final_text
    assert kilo.sent == [(session, "Hi")]


async def _noop(text: str) -> None:
    return None


async def test_stream_prompt_forwards_tool_and_permission_events():
    session = "sid-2"
    events = [
        KiloEvent(
            type="session.next.tool.called",
            properties={"tool": "read", "input": {"file": "/tmp/a"}, "sessionID": session},
        ),
        KiloEvent(
            type="permission.asked",
            properties={
                "id": "req-1",
                "permission": "write",
                "patterns": ["/tmp/a"],
                "sessionID": session,
            },
        ),
        KiloEvent(type="session.turn.close", properties={"sessionID": session}),
    ]
    kilo = _FakeKilo(events)
    tools: list[str] = []
    perms: list[str] = []

    async def on_tool(line: str) -> None:
        tools.append(line)

    async def on_perm(rid: str) -> None:
        perms.append(rid)

    await stream_prompt(
        kilo,
        session,
        "do it",
        flush=lambda text: _noop(text),
        on_tool=on_tool,
        on_permission=on_perm,
        edit_interval=0.0,
        subscribe_settle=0.0,
    )
    assert any("read" in t for t in tools)
    assert perms == ["req-1"]
