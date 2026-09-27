"""Offline Telegram building blocks for tests.

Level 3 of the test plan needs to observe exactly which Telegram API calls the bot
made (``sendMessage``, ``editMessageText``, ``sendDocument``, ...). Instead of
patching dozens of ``answer``/``edit_text`` methods by hand, we swap the bot's HTTP
transport for a :class:`RecordingSession` (a :class:`aiogram.client.session.base.BaseSession`)
that records every call and returns an inert, bound :class:`Message`. Because aiogram
objects carry the bound bot around, handlers can still chain ``edit_text`` /
``answer`` and those calls land in the same recording — so one mechanism covers
handler-level (level 1), dispatcher-level (level 2) and call-counting (level 3) tests.

This mirrors what external ``aiogram_tests`` / ``aiogram-test-framework`` offer, but
keeps everything in-repo with only the stdlib ``unittest.mock``.

Helpers::

    bot = make_bot(rec)              # Bot whose session records into `rec`
    msg  = make_message(bot, user_id=42, chat_id=200, message_id=5, text="/new")
    update = make_update(msg)        # real Update dict for feed_raw_update
    cq   = make_callback(bot, user_id=42, data="...", callback_data="...", message=msg)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any, cast

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import CallbackQuery, Chat, Document, Message, User

TOKEN = "123456:TEST-TOKEN"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def records(bot: Bot) -> RecordingSession:
    """Return ``bot.session`` typed as the :class:`RecordingSession` it really is.

    aiogram types :attr:`Bot.session` as the abstract :class:`BaseSession`, which
    has no ``calls``. Tests that introspect recorded Telegram calls therefore
    cast through this helper so static checkers stay satisfied.
    """
    return cast("RecordingSession", bot.session)


class CallRecord:
    """A single recorded Telegram API call."""

    __slots__ = ("method", "data")

    def __init__(self, method: str, data: dict[str, Any]) -> None:
        self.method = method
        self.data = data

    def text(self) -> str:
        return str(self.data.get("text") or "")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"CallRecord({self.method}, {self.data!r})"


class RecordingSession(BaseSession):
    """A :class:`BaseSession` that records calls and returns inert replies.

    Every ``make_request`` is appended to :attr:`calls`. Message-returning methods
    (``sendMessage``, ``editMessageText``, ``sendDocument``) return a bound
    :class:`Message` so the handler can keep chaining calls that are also recorded.
    """

    def __init__(self, *, parse_mode: str | None = None) -> None:
        super().__init__()
        self.calls: list[CallRecord] = []
        self.parse_mode = parse_mode

    async def close(self) -> None:
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b""

    def method_calls(self, method: str) -> list[CallRecord]:
        return [c for c in self.calls if c.method == method]

    async def make_request(
        self,
        bot: Bot,
        method: Any,
        timeout: int | None = None,
    ) -> Any:
        api_method = method.__api_method__
        try:
            data = method.model_dump(exclude_none=True)
        except Exception:  # noqa: BLE001 - never crash the fake on a weird method
            data = {}
        self.calls.append(CallRecord(api_method, data))

        if api_method in (
            "sendMessage",
            "editMessageText",
            "sendDocument",
            "sendPhoto",
        ):
            return _make_result_message(bot, text=data.get("text") or "")
        if api_method in ("answerCallbackQuery", "deleteMessage", "setMyCommands"):
            return True
        if api_method in ("pinChatMessage", "unpinChatMessage"):
            return True
        if api_method == "answerInlineQuery":
            return True
        if api_method == "getMe":
            return self._get_me(bot)
        return None

    def _get_me(self, bot: Bot) -> dict[str, Any]:
        return {
            "id": 300,
            "is_bot": True,
            "first_name": "testbot",
            "username": "testbot",
        }


def _make_result_message(bot: Bot, text: str) -> Message:
    message = Message(
        message_id=999,
        date=_now(),
        chat=Chat(id=200, type="private", first_name="Owner", username="owner"),
        from_user=User(
            id=300, is_bot=True, first_name="testbot", username="testbot"
        ),
        text=text,
    )
    message._bot = bot
    return message


# -- construction helpers -------------------------------------------------------


def make_bot(rec: RecordingSession | None = None) -> Bot:
    """Return a real ``Bot`` on a :class:`RecordingSession` (no network)."""
    rec = rec or RecordingSession()
    return Bot(token=TOKEN, session=rec)


def _own_user() -> User:
    return User(id=42, is_bot=False, first_name="Owner", username="owner")


def owner_user() -> User:
    return _own_user()


def make_message(
    bot: Bot,
    *,
    user_id: int = 42,
    chat_id: int = 200,
    message_id: int = 5,
    text: str = "",
    document: Document | None = None,
) -> Message:
    """Return a real, bot-bound :class:`Message`."""

    user = User(
        id=user_id,
        is_bot=False,
        first_name="Owner",
        username="owner" if user_id == 42 else "stranger",
    )
    chat = Chat(id=chat_id, type="private")
    message = Message(
        message_id=message_id,
        date=_now(),
        chat=chat,
        from_user=user,
        text=text or None,
        document=document,
    )
    message._bot = bot
    return message


def bind(bot: Bot, obj: Any) -> Any:
    obj._bot = bot
    return obj


def make_document(bot: Bot, *, file_name: str = "x.json") -> Document:
    doc = Document(
        file_id="file123",
        file_unique_id="fuid123",
        file_name=file_name,
        file_size=10,
    )
    doc._bot = bot
    return doc


def make_callback(
    bot: Bot,
    *,
    user_id: int = 42,
    message: Message | None = None,
    data: str = "",
    callback_data: str = "x",
    message_id: int = 999,
) -> CallbackQuery:
    user = User(
        id=user_id,
        is_bot=False,
        first_name="Owner",
        username="owner" if user_id == 42 else "stranger",
    )
    target = message or _make_result_message(bot, text="base")
    cq = CallbackQuery(
        id=f"cq-{callback_data}",
        from_user=user,
        chat_instance="ci1",
        data=data or None,
        message=target,
    )
    cq._bot = bot
    return cq


def make_update(
    message: Message | None = None, callback: CallbackQuery | None = None
) -> dict[str, Any]:
    """Return a raw comma dict for :meth:`Dispatcher.feed_raw_update`."""
    update: dict[str, Any] = {"update_id": 1}
    if message is not None:
        update["message"] = message.model_dump(mode="json")
    if callback is not None:
        cbd = callback.model_dump(mode="json")
        update["callback_query"] = cbd
    return update


def make_raw_message_update(
    *,
    user_id: int = 42,
    text: str = "",
    message_id: int = 5,
    entity_type: str | None = None,
    entity_value: str | None = None,
) -> dict[str, Any]:
    """Return a raw update dict directly (no ``model_dump`` round-trip)."""
    base: dict[str, Any] = {
        "message_id": message_id,
        "date": 0,
        "text": text,
        "chat": {"id": 200, "type": "private", "first_name": "Owner", "username": "owner"},
        "from": {
            "id": user_id,
            "is_bot": False,
            "first_name": "Owner",
            "username": "owner" if user_id == 42 else "stranger",
        },
    }
    if entity_type:
        base["entities"] = [
            {"offset": 0, "length": len(text), "type": entity_type, "url": entity_value}
        ]
    return {"update_id": 1, "message": base}


def make_raw_callback_update(
    *,
    user_id: int = 42,
    data: str,
    message_id: int = 999,
) -> dict[str, Any]:
    return {
        "update_id": 2,
        "callback_query": {
            "id": f"cq-{data}",
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Owner",
                "username": "owner" if user_id == 42 else "stranger",
            },
            "chat_instance": "ci1",
            "data": data,
            "message": {
                "message_id": message_id,
                "date": 0,
                "text": "base",
                "chat": {"id": 200, "type": "private"},
            },
        },
    }


def for_command_update(text: str, *, user_id: int = 42) -> dict[str, Any]:
    """A raw update for a bot-command message (no entities needed)."""
    return make_raw_message_update(user_id=user_id, text=text)


__all__ = [
    "TOKEN",
    "CallRecord",
    "RecordingSession",
    "make_bot",
    "make_message",
    "make_document",
    "make_callback",
    "make_update",
    "make_raw_message_update",
    "make_raw_callback_update",
    "for_command_update",
    "owner_user",
    "bind",
    "records",
]
