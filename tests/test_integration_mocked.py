"""Integration-style tests with an in-memory fake Kilo client.

Covers the primary owner workflow the bot relays to the server: create a session
(``session.create``), send a streaming prompt, list sessions showing the new one,
and delete it. These tests use the bot's own service/streaming code with a fake
client, so no network or Telegram API is involved.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from kilocode_tg_bot.services.streaming import stream_prompt
from kilocode_tg_bot.state.session_store import SessionStore


class FakeSessionInfo:
    """Quacks like :class:`SessionInfo` for the bits the bot touches."""

    def __init__(self, session_id: str, title: str) -> None:
        self.id = session_id
        self.title = title or "untitled"
        self.time = SimpleNamespace(updated=int(datetime.now(UTC).timestamp() * 1000))
        self.model = None


class FakeKilo:
    """Backed by an in-memory dict, mirrors the session surface we use."""

    def __init__(self) -> None:
        self._db: dict[str, FakeSessionInfo] = {}
        self._counter = 0
        self.streamed: list[tuple[str, str]] = []

    async def create_session(self, *, title: str | None = None, **_: object):
        self._counter += 1
        sid = f"session-{self._counter}"
        info = FakeSessionInfo(sid, title or "untitled")
        self._db[sid] = info
        return info

    async def list_sessions(self, **__: object):
        return list(self._db.values())

    async def delete_session(self, session_id: str) -> bool:
        return self._db.pop(session_id, None) is not None

    async def get_session(self, session_id: str):
        return self._db[session_id]

    async def send_prompt_async(self, session_id: str, prompt: str) -> None:
        self.streamed.append((session_id, prompt))

    async def stream_session_events(self, session_id: str, *, instance: bool = False):
        from kilocode_client import KiloEvent

        async def gen():
            await asyncio.sleep(0.02)  # let the sender task finish send_prompt_async
            yield KiloEvent(
                type="message.part.delta",
                properties={
                    "field": "text",
                    "delta": f"echo: {self._db[session_id].title}",
                    "sessionID": session_id,
                },
            )
            await asyncio.sleep(0.02)
            yield KiloEvent(type="session.turn.close", properties={"sessionID": session_id})

        return gen()

    # Namespaced accessors mirroring the real client
    @property
    def session(self):
        return _FakeSessionApi(self)


class _FakeSessionApi:
    def __init__(self, kilo: FakeKilo) -> None:
        self._k = kilo

    async def create(self, title: str | None = None, **kwargs: object):
        return await self._k.create_session(title=title)

    async def list_sessions(self, **kwargs: object):
        return await self._k.list_sessions()

    async def delete(self, session_id: str) -> bool:
        return await self._k.delete_session(session_id)

    async def get(self, session_id: str):
        return await self._k.get_session(session_id)


@pytest.mark.asyncio
async def test_create_prompt_list_delete_workflow():
    kilo = FakeKilo()
    store = SessionStore("/tmp/test_kilo_bot_store.db")
    await store.open()

    user_id = 42
    try:
        # /new
        created = await kilo.session.create(title="demo")
        await store.set_active(user_id, created.id, created.title)
        assert await store.get_active(user_id) == created.id

        # ordinary prompt -> stream
        final = await stream_prompt(
            kilo,
            created.id,
            "hello",
            flush=lambda t: _noop(t),
            edit_interval=0.0,
            subscribe_settle=0.0,
        )
        assert "echo: demo" in final
        assert kilo.streamed == [(created.id, "hello")]

        # /sessions shows it
        sessions = await kilo.list_sessions()
        assert any(s.id == created.id and s.title == "demo" for s in sessions)

        # /delete
        ok = await kilo.session.delete(created.id)
        assert ok is True
        assert await kilo.list_sessions() == []
    finally:
        await store.close()


async def _noop(text: str) -> None:
    return None


@pytest.mark.asyncio
async def test_store_persists_active_session():
    import tempfile

    db = tempfile.mktemp(suffix=".db")
    store = SessionStore(db)
    await store.open()
    await store.set_active(7, "abc123", "t")
    assert await store.get_active(7) == "abc123"
    assert await store.get_active(8) is None
    await store.clear(7)
    assert await store.get_active(7) is None
    await store.close()
