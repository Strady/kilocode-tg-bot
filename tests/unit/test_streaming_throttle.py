"""Unit tests for streaming throttling and the prompt loop.

Verified offline against :class:`EditThrottler` and :class:`stream_prompt` driven
by a tiny fake Kilo, covering batching, turn-close flush, tool/permission events,
and resilient handling of a failed edit.
"""

from __future__ import annotations

from typing import Any

from tests.fakes.events import permission_event, text_delta, tool_event, turn_close
from tests.fakes.fake_kilo import FakeKilo

# a negligible throttle interval makes every maybe_flush eligible
_INSTANT = 0.0


async def test_throttler_batches_deltas_when_below_interval() -> None:
    flushed: list[str] = []
    kilo = FakeKilo()
    kilo.seed_session("s", "demo")
    # 5 deltas but a slow edit interval: the stream must not edit once per delta.
    await kilo.set_stream_events(
        "s",
        [text_delta("s", "1"), text_delta("s", "2"), text_delta("s", "3"),
         text_delta("s", "4"), text_delta("s", "5"), turn_close("s")],
    )

    async def flush(text: str) -> None:
        flushed.append(text)

    from kilocode_tg_bot.services.streaming import stream_prompt

    final = await stream_prompt(
        kilo, "s", "hi",
        flush=flush,
        edit_interval=999.0,  # far above the test's runtime → single end-of-stream flush
        subscribe_settle=0.0,
    )
    # only the first delta (no prior flush) and the forced final flush happened:
    # "2345" was batched, so 4 deltas did not each trigger an edit.
    assert len(flushed) == 2
    assert "".join(flushed) == "12345"
    assert final == "12345"


async def test_turn_close_forces_flush_of_pending_buffer() -> None:
    flushed: list[str] = []
    kilo = FakeKilo()
    kilo.seed_session("s", "demo")
    # a single delta then immediate turn close: no intermediate edit boundary
    await kilo.set_stream_events("s", [text_delta("s", "final"), turn_close("s")])

    async def flush(text: str) -> None:
        flushed.append(text)

    final = await _stream(kilo, "s", "q", flush=flush)
    assert "final" in final
    assert any("final" in f for f in flushed)


async def test_tool_call_does_not_break_text_buffer() -> None:
    kilo = FakeKilo()
    kilo.seed_session("s", "demo")
    await kilo.set_stream_events(
        "s",
        [
            text_delta("s", "A"),
            tool_event("s", "read", {"file": "/tmp/a"}),
            text_delta("s", "B"),
            turn_close("s"),
        ],
    )
    tool_lines: list[str] = []

    async def on_tool(line: str) -> None:
        tool_lines.append(line)

    final = await _stream(kilo, "s", "do it", on_tool=on_tool)
    assert "A" in final and "B" in final
    assert any("read" in t for t in tool_lines)


async def test_permission_event_triggers_callback_with_request_id() -> None:
    kilo = FakeKilo()
    kilo.seed_session("s", "demo")
    await kilo.set_stream_events(
        "s", [permission_event("s", "req-9", "write"), turn_close("s")]
    )
    perms: list[str] = []

    async def on_permission(rid: str) -> None:
        perms.append(rid)

    await _stream(kilo, "s", "q", on_permission=on_permission)
    assert perms == ["req-9"]


async def test_edit_failure_is_not_fatal() -> None:
    kilo = FakeKilo()
    kilo.seed_session("s", "demo")
    await kilo.set_stream_events("s", [text_delta("s", "x"), turn_close("s")])

    async def flush(text: str) -> None:
        raise RuntimeError("simulated TelegramRetryAfter/network failure")

    final = await _stream(kilo, "s", "q", flush=flush)
    # the stream loop must complete and return the concatenated text anyway
    assert "x" in final


async def _stream(
    kilo: FakeKilo, session_id: str, prompt: str, **extra: Any
) -> str:
    from kilocode_tg_bot.services.streaming import stream_prompt

    async def _flush(text: str) -> None:
        await _noop(text)

    defaults: dict[str, Any] = {
        "flush": _flush,
        "edit_interval": _INSTANT,
        "subscribe_settle": 0.005,
    }
    defaults.update(extra)
    return await stream_prompt(kilo, session_id, prompt, **defaults)


async def _noop(text: str) -> None:
    return None


# Re-test the two original focus behaviors for completeness.


async def test_stream_concatenates_and_sends_prompt() -> None:
    kilo = FakeKilo()
    kilo.seed_session("s1", "demo")
    await kilo.set_stream_events(
        "s1", [text_delta("s1", "Hel"), text_delta("s1", "lo"), turn_close("s1")]
    )
    # hold the loop open longer than subscribe_settle so the background
    # send task deterministically completes before the stream closes
    kilo.event_delay = 0.02
    final = await _stream(kilo, "s1", "Hi")
    assert "Hel" in final and "lo" in final
    sends = kilo.calls_for("send_prompt_async")
    assert sends and sends[0].args == ("s1", "Hi")


async def test_stream_forwards_tool_and_permission() -> None:
    kilo = FakeKilo()
    kilo.seed_session("s2", "demo")
    await kilo.set_stream_events(
        "s2",
        [
            tool_event("s2", "read", {"file": "/tmp/a"}),
            permission_event("s2", "r1", "write"),
            turn_close("s2"),
        ],
    )
    tools: list[str] = []
    perms: list[str] = []

    async def on_tool(line: str) -> None:
        tools.append(line)

    async def on_perm(rid: str) -> None:
        perms.append(rid)

    await _stream(kilo, "s2", "x", on_tool=on_tool, on_permission=on_perm)
    assert any("read" in t for t in tools)
    assert perms == ["r1"]
