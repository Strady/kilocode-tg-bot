"""Unit tests for :class:`~kilocode_tg_bot.state.session_store.SessionStore`."""

from __future__ import annotations

from pathlib import Path

import pytest
from kilocode_tg_bot.state.session_store import SessionStore


async def test_set_get_active() -> None:
    store = SessionStore(":memory:")
    await store.open()
    try:
        await store.set_active(42, "session-abc", "my session")
        assert await store.get_active(42) == "session-abc"
    finally:
        await store.close()


async def test_get_active_missing_user_is_none() -> None:
    store = SessionStore(":memory:")
    await store.open()
    try:
        assert await store.get_active(999) is None
        # and there is no crash even with no rows
        assert await store.get_active(1) is None
    finally:
        await store.close()


async def test_set_active_overwrites_existing() -> None:
    store = SessionStore(":memory:")
    await store.open()
    try:
        await store.set_active(42, "first", "t1")
        await store.set_active(42, "second", "t2")
        assert await store.get_active(42) == "second"
        rows = await store._rows()
        assert len(rows) == 1
        assert rows[0]["session_id"] == "second"
    finally:
        await store.close()


async def test_set_active_per_user_is_independent() -> None:
    store = SessionStore(":memory:")
    await store.open()
    try:
        await store.set_active(1, "s1")
        await store.set_active(2, "s2")
        assert await store.get_active(1) == "s1"
        assert await store.get_active(2) == "s2"
    finally:
        await store.close()


async def test_clear_removes_record() -> None:
    store = SessionStore(":memory:")
    await store.open()
    try:
        await store.set_active(42, "session-x")
        assert await store.get_active(42) == "session-x"
        await store.clear(42)
        assert await store.get_active(42) is None
    finally:
        await store.close()


async def test_persists_to_disk(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    store = SessionStore(str(db))
    await store.open()
    await store.set_active(42, "persisted")
    await store.close()

    reopened = SessionStore(str(db))
    await reopened.open()
    try:
        assert await reopened.get_active(42) == "persisted"
    finally:
        await reopened.close()


async def test_not_open_raises() -> None:
    store = SessionStore(":memory:")
    with pytest.raises(RuntimeError):
        await store.get_active(1)
