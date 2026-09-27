"""Export a Kilo session to a file and send it; import a session from an uploaded doc."""

from __future__ import annotations

import io
import json
import logging
import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Document, FSInputFile, Message
from kilocode_client import Kilo

from kilocode_tg_bot.handlers.common import call_kilo
from kilocode_tg_bot.services.kilo import humanize_error
from kilocode_tg_bot.state.session_store import SessionStore

logger = logging.getLogger(__name__)

router = Router(name="export_import")


@router.message(Command("export"))
async def on_export(message: Message, kilo: Kilo, store: SessionStore) -> None:
    user_id = message.from_user.id if message.from_user else 0
    session_id = await store.get_active(user_id)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    path = Path(tempfile.gettempdir()) / f"kilo_session_{session_id[:8]}.json"
    # export_session_to_file returns None on success, so we cannot use call_kilo's
    # None-means-error convention; report failures explicitly instead.
    try:
        await kilo.export_session_to_file(session_id, str(path))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Export failed for session %s", session_id)
        await message.answer(humanize_error(exc))
        return
    await message.answer_document(
        FSInputFile(path, filename=f"{session_id}.json"),
        caption=f"Экспорт сессии `{session_id}`",
    )


@router.message(Command("import"))
async def on_import_hint(message: Message) -> None:
    await message.answer("Пришлите JSON-документ сессии (файл) для импорта.")


@router.message(F.document)
async def on_import_document(
    message: Message, document: Document, bot: Bot, kilo: Kilo, store: SessionStore
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not (filename := document.file_name):
        filename = "import.json"
    if not filename.lower().endswith(".json"):
        await message.answer("Поддерживаю только JSON-документы (*.json).")
        return
    try:
        data = io.BytesIO()
        await bot.download(document, destination=data)
        doc = json.loads(data.getvalue().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Не удалось прочитать документ: {exc}")
        return
    if not isinstance(doc, dict):
        await message.answer("Ожидал JSON-объект (session record).")
        return
    result = await call_kilo(lambda: kilo.import_session(doc), message)
    if result is None:
        return
    new_session_id = _extract_session_id(result)
    if new_session_id:
        await store.set_active(user_id, new_session_id)
    await message.answer(f"✅ Сессия импортирована ({new_session_id or 'id неизвестен'}).")


def _extract_session_id(result: dict) -> str | None:
    if isinstance(result, dict):
        session_part = result.get("session")
        sid = session_part.get("id") if isinstance(session_part, dict) else None
        if not sid:
            sid = result.get("id") if "id" in result else result.get("sessionID")
        return str(sid) if sid else None
    return None


__all__ = ["router"]
