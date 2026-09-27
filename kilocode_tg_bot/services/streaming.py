"""Live streaming of a prompt into Telegram with rate-limit-safe editing.

The chat handler subscribes to the session event stream *before* sending, runs
``send_prompt_async`` in a background task, then consumes typed events. Text
deltas are accumulated into a buffer and flushed to Telegram at most once per
``interval`` seconds (throttled) so we never trip Telegram's edit rate limit.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from kilocode_client import KiloEvent, permission_of, text_delta_of, tool_call_of

# Emit callbacks: every one is awaitable and errors inside are swallowed so a
# transient Telegram/API failure never aborts the whole stream.
Flush = Callable[[str], Awaitable[None]]
ToolCallback = Callable[[str], Awaitable[None]]
PermissionCallback = Callable[[str], Awaitable[None]]


class KiloStream(Protocol):
    """The tiny async streaming surface :func:`stream_prompt` consumes.

    Declared as a ``Protocol`` so tests can hand it a small fake instead of a
    full :class:`kilocode_client.Kilo`. ``text`` is positional-only because the
    test fakes name it ``prompt``.
    """

    async def send_prompt_async(self, session_id: str, text: str, /) -> None: ...

    async def stream_session_events(
        self, session_id: str, *, instance: bool = False
    ) -> AsyncIterator[KiloEvent]: ...


class EditThrottler:
    """Accumulate deltas and flush them at a bounded rate.

    Consuming code calls :meth:`push` for every text fragment; :meth:`flush_now`
    concatenates the buffer and invokes the flush callback, but only if enough
    time has elapsed since the last flush. This batching avoids Telegram's edit
    rate limit while keeping the message reasonably live.
    """

    def __init__(self, flush: Flush, interval: float = 1.0) -> None:
        self._flush = flush
        self._interval = interval
        self._buffer: list[str] = []
        self._last_flush: float | None = None
        self._lock = asyncio.Lock()

    def push(self, delta: str) -> None:
        """Queue a delta for the next flush."""
        self._buffer.append(delta)

    @property
    def pending(self) -> bool:
        return bool(self._buffer)

    async def flush_now(self) -> None:
        """Flush buffered deltas straight away, skipping the throttle check."""
        async with self._lock:
            await self._emit(force=True)

    async def maybe_flush(self) -> None:
        """Flush only if the throttle interval has elapsed."""
        async with self._lock:
            await self._emit(force=False)

    async def _emit(self, *, force: bool) -> None:
        text = "".join(self._buffer)
        if not text:
            return
        now = time.monotonic()
        if not force and self._last_flush is not None and now - self._last_flush < self._interval:
            return
        self._buffer = []
        self._last_flush = now
        try:
            await self._flush(text)
        except Exception:  # noqa: BLE001 - a failed edit is not fatal
            return


def _is_reasoning_delta(event: Any, part_kind: dict[str, str]) -> bool:
    """True if this text delta belongs to a reasoning (chain-of-thought) part."""
    if event.type != "message.part.delta":
        return False
    pid = event.properties.get("partID")
    if not isinstance(pid, str):
        return False
    return part_kind.get(pid) == "reasoning"


def _format_tool(tool: Any) -> str:
    """Render a :class:`ToolCallEvent` as a short status line."""
    status = getattr(tool, "status", "running")
    name = getattr(tool, "tool", "")
    input_data = getattr(tool, "input", {}) or {}
    try:
        compact = ",".join(f"{k}={v}" for k, v in list(input_data.items())[:3])
    except AttributeError:
        compact = str(input_data)[:120]
    return f"[tool {status}] {name} {compact}"


async def stream_prompt(
    client: KiloStream,
    session_id: str,
    prompt: str,
    *,
    flush: Flush,
    on_tool: ToolCallback | None = None,
    on_permission: PermissionCallback | None = None,
    on_turn_close: Callable[[], Awaitable[None]] | None = None,
    edit_interval: float = 1.0,
    subscribe_settle: float = 0.2,
) -> str:
    """Stream one prompt via the client, driving the ``flush`` callback with text.

    Subscribes to ``stream_session_events`` *before* sending, posts the prompt
    through ``send_prompt_async`` in a background task, then consumes the stream
    until ``session.turn.close``. Returns the final concatenated text so callers
    can finalise the message without an extra edit.
    """
    final_chunks: list[str] = []

    async def flush_with_final(text: str) -> None:
        final_chunks.append(text)
        await flush(text)

    throttler = EditThrottler(flush_with_final, interval=edit_interval)

    async def send() -> None:
        await asyncio.sleep(subscribe_settle)
        await client.send_prompt_async(session_id, prompt)

    stream = await client.stream_session_events(session_id)
    sender = asyncio.create_task(send())
    final_text = ""

    # Track the kind of each message part (``text``/``reasoning``) so text deltas
    # belonging to a reasoning part are dropped: only the final assistant answer
    # is shown to the user, never the model's internal chain of thought.
    part_kind: dict[str, str] = {}

    def _remember_part(part: Any) -> None:
        pid = part.get("id") if isinstance(part, dict) else getattr(part, "id", None)
        kind = part.get("type") if isinstance(part, dict) else getattr(part, "type", None)
        if pid is not None and kind is not None:
            part_kind[str(pid)] = str(kind)

    try:
        async for event in stream:
            if event.type == "message.part.updated":
                part = event.properties.get("part")
                if part is not None:
                    _remember_part(part)
            if delta := text_delta_of(event):
                # Drop reasoning deltas but keep something when the part kind is
                # unknown (older event shapes / tests) so a reply is never lost.
                if not _is_reasoning_delta(event, part_kind):
                    throttler.push(delta)
                    await throttler.maybe_flush()
            if tool := tool_call_of(event):
                if on_tool is not None:
                    await on_tool(_format_tool(tool))
            if perm := permission_of(event):
                if perm.request_id and on_permission is not None:
                    await on_permission(perm.request_id)
            if event.is_turn_close:
                await throttler.flush_now()
                final_text = "".join(final_chunks)
                if on_turn_close is not None:
                    await on_turn_close()
                break
    finally:
        if not sender.done():
            sender.cancel()
        try:
            await sender
        except asyncio.CancelledError:
            pass

    return final_text
