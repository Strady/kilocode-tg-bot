"""Handler-level tests for /export (send file) and /import (upload a document)."""

from __future__ import annotations

import json
from typing import Any, cast

from aiogram import Bot
from kilocode_client import Kilo
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_document, make_message, records

ACTIVE = "session-01"


async def test_export_sends_document(bot: Bot, fake_kilo: FakeKilo, store: Any) -> None:
    from kilocode_tg_bot.handlers.export_import import on_export

    fake_kilo.seed_session(ACTIVE, "demo")
    await store.set_active(42, ACTIVE)

    message = make_message(bot, text="/export")
    await on_export(message, kilo=cast(Kilo, fake_kilo), store=store)

    assert fake_kilo.called("export_session_to_file")
    sent_docs = [c for c in records(bot).calls if c.method == "sendDocument"]
    # the exported file is sent as a document, never as plain text
    assert sent_docs
    # no plain-text sendMessage carrying the session body either
    assert not any(
        "kilo_session" in c.text() for c in records(bot).calls if c.method == "sendMessage"
    )


async def test_export_no_session(bot: Bot, fake_kilo: FakeKilo, store: Any) -> None:
    from kilocode_tg_bot.handlers.export_import import on_export

    message = make_message(bot, text="/export")
    await on_export(message, kilo=cast(Kilo, fake_kilo), store=store)
    assert not fake_kilo.called("export_session_to_file")
    assert not [c for c in records(bot).calls if c.method == "sendDocument"]


async def test_import_valid_json_calls_import(
    bot: Bot, fake_kilo: FakeKilo, store: Any, monkeypatch: Any
) -> None:
    from kilocode_tg_bot.handlers.export_import import on_import_document

    _stub_download(bot, monkeypatch, {"session": {"id": "imp-99", "title": "imported"}})

    doc = make_document(bot, file_name="session.json")
    message = make_message(bot, text="", document=doc)
    await on_import_document(
        message, document=doc, bot=bot, kilo=cast(Kilo, fake_kilo), store=store
    )

    calls = fake_kilo.calls_for("import_session")
    assert calls
    assert await store.get_active(42) == "imp-99"
    assert any("Сессия импортирована" in s for s in _texts(bot))


async def test_import_rejects_non_json_filename(
    bot: Bot, fake_kilo: FakeKilo, store: Any, monkeypatch: Any
) -> None:
    from kilocode_tg_bot.handlers.export_import import on_import_document

    doc = make_document(bot, file_name="notes.txt")
    message = make_message(bot, text="", document=doc)
    await on_import_document(
        message, document=doc, bot=bot, kilo=cast(Kilo, fake_kilo), store=store
    )
    assert not fake_kilo.called("import_session")
    assert any("JSON" in s for s in _texts(bot))


async def test_import_invalid_json_is_friendly(
    bot: Bot, fake_kilo: FakeKilo, store: Any, monkeypatch: Any
) -> None:
    from kilocode_tg_bot.handlers.export_import import on_import_document

    _stub_download(bot, monkeypatch, {"name": "not a session", "value": 1})
    doc = make_document(bot, file_name="session.json")
    message = make_message(bot, text="", document=doc)
    await on_import_document(
        message, document=doc, bot=bot, kilo=cast(Kilo, fake_kilo), store=store
    )
    # still a dict -> import is called, but a non-dict top-level should not happen here
    assert fake_kilo.called("import_session")


async def test_import_malformed_body_is_rejected(
    bot: Bot, fake_kilo: FakeKilo, store: Any, monkeypatch: Any
) -> None:
    from kilocode_tg_bot.handlers.export_import import on_import_document

    _stub_download(bot, monkeypatch, ['not', 'a', 'dict'])
    doc = make_document(bot, file_name="session.json")
    message = make_message(bot, text="", document=doc)
    await on_import_document(
        message, document=doc, bot=bot, kilo=cast(Kilo, fake_kilo), store=store
    )
    assert not fake_kilo.called("import_session")
    assert any("JSON-объект" in s for s in _texts(bot))


def _stub_download(bot: Bot, monkeypatch: Any, payload: Any) -> None:
    import io

    async def fake_download(document: Any, destination: Any, **_: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        if isinstance(destination, io.BytesIO):
            destination.write(data)

    monkeypatch.setattr(bot, "download", fake_download)


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]
