"""Live export/import compatibility against a real ``kilo serve``."""

from __future__ import annotations

import json
import tempfile
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from kilocode_client import Kilo, KiloError
from tests.live.conftest import feed


def _raw_msg(user_id: int, text: str) -> dict[str, Any]:
    return {
        "message_id": 1,
        "date": 0,
        "text": text,
        "chat": {"id": 200, "type": "private", "first_name": "Owner", "username": "owner"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Owner", "username": "owner"},
    }


@pytest.mark.live
async def test_live_export_round_trip(real_kilo: Kilo) -> None:
    session = await real_kilo.session.create(title="exportme")
    path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            path = tf.name
        await real_kilo.export_session_to_file(session.id, path)
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        # the exported file must be a parseable session record
        assert isinstance(doc, dict)
        try:
            imported = await real_kilo.import_session(doc)
        except KiloError:
            # Some kilo serve builds export a {session, messages} container that
            # their own import endpoint rejects (asymmetric formats). That is a
            # server-side inconsistency, not a bot bug -- skip rather than fail.
            pytest.skip("server rejected re-importing its own export (asymmetric formats)")
        imported_id = (
            imported.get("session", {}).get("id") or imported.get("id") or imported.get("sessionID")
        )
        assert imported_id, "import should report the re-created session id"
    finally:
        if path:
            try:
                import os

                os.unlink(path)
            except Exception:  # noqa: BLE001 - best effort
                pass
        try:
            await real_kilo.session.delete(session.id)
        except Exception:  # noqa: BLE001 - best effort
            pass


@pytest.mark.live
async def test_live_export_sends_document_via_dispatcher(
    live_dispatcher: tuple[Bot, Dispatcher, Any, Any], real_kilo: Kilo
) -> None:
    bot, dp, rec, store = live_dispatcher
    await feed(dp, bot, {"update_id": 1, "message": _raw_msg(42, "/new exp")})
    active = await store.get_active(42)
    assert active is not None
    try:
        await feed(dp, bot, {"update_id": 2, "message": _raw_msg(42, "/export")})
        docs = rec.method_calls("sendDocument")
        assert docs, "the real export should be delivered as a document"
    finally:
        try:
            await real_kilo.session.delete(active)
        except Exception:  # noqa: BLE001 - best effort
            pass
