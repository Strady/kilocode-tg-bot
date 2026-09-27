"""Helpers for building :class:`KiloEvent` streams in tests."""

from __future__ import annotations

from kilocode_client import KiloEvent


def text_delta(session_id: str, delta: str) -> KiloEvent:
    return KiloEvent(
        type="message.part.delta",
        properties={"field": "text", "delta": delta, "sessionID": session_id},
    )


def tool_event(session_id: str, tool: str, input_data: dict | None = None) -> KiloEvent:
    return KiloEvent(
        type="session.next.tool.called",
        properties={
            "tool": tool,
            "input": input_data or {},
            "sessionID": session_id,
        },
    )


def permission_event(session_id: str, request_id: str, permission: str = "write") -> KiloEvent:
    return KiloEvent(
        type="permission.asked",
        properties={
            "id": request_id,
            "permission": permission,
            "patterns": ["/tmp/a"],
            "sessionID": session_id,
        },
    )


def turn_close(session_id: str, reason: str = "done") -> KiloEvent:
    return KiloEvent(
        type="session.turn.close",
        properties={"reason": reason, "sessionID": session_id},
    )


def text_turn(session_id: str, frames: list[str]) -> list[KiloEvent]:
    """A full stream: ``frames`` of text deltas followed by turn-close."""
    return [text_delta(session_id, f) for f in frames] + [turn_close(session_id)]


__all__ = [
    "text_delta",
    "tool_event",
    "permission_event",
    "turn_close",
    "text_turn",
]
