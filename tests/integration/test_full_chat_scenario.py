"""A single end-to-end dispatcher scenario on FakeKilo: create a session, chat,
list sessions, then delete it — verifying the whole chain routes correctly."""

from __future__ import annotations

import asyncio
from typing import Any

from aiogram import Bot, Dispatcher
from tests.fakes import events
from tests.fakes.fake_telegram import make_raw_callback_update, make_raw_message_update

OWNER = 42


def _feed(dp: Dispatcher, bot: Bot, update: dict[str, Any]) -> Any:
    return asyncio.run(dp.feed_raw_update(bot=bot, update=update))


def _sent(rec: Any) -> list[str]:
    return [c.text() for c in rec.method_calls("sendMessage")]


def _edits(rec: Any) -> list[str]:
    return [c.text() for c in rec.method_calls("editMessageText")]


def test_full_chat_scenario(
    dispatcher: tuple[Bot, Dispatcher, Any], fake_kilo: Any, store: Any
) -> None:
    bot, dp, rec = dispatcher
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/new scenario"))
    # the new session became active; grab its id from the store
    active = asyncio.run(store.get_active(OWNER))
    assert active is not None

    # plain-text message streams a reply back into an edit
    asyncio.run(
        fake_kilo.set_stream_events(
            active,
            [
                events.text_delta(active, "Partly "),
                events.text_delta(active, "done."),
                events.turn_close(active),
            ],
        )
    )
    # keep the stream open past subscribe_settle so send_prompt_async fires
    fake_kilo.event_delay = 0.3
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="summarize"))
    assert fake_kilo.called("send_prompt_async")
    all_text = "\n".join(_sent(rec) + _edits(rec))
    assert "Partly done." in all_text

    # /sessions lists the session we just created
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/sessions"))
    assert "Доступно сессий: 1" in "\n".join(_sent(rec))

    # /delete → confirm → the session is removed from the server and store
    _feed(dp, bot, make_raw_message_update(user_id=OWNER, text="/delete"))
    assert not fake_kilo.called("session.delete")  # nothing deleted before confirm
    _feed(dp, bot, make_raw_callback_update(user_id=OWNER, data=f"sdel:yes:{active}"))
    assert fake_kilo.called("session.delete")
    assert asyncio.run(store.get_active(OWNER)) is None
