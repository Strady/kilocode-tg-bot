"""Handler-level tests for permission commands and the inline reply buttons."""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot
from kilocode_client import Kilo, KiloError
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_callback, make_message, records


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]


async def test_permission_reply_calls_permission_reply(
    bot: Bot, fake_kilo: FakeKilo
) -> None:
    from kilocode_tg_bot.handlers.permissions import on_permission_reply
    from kilocode_tg_bot.keyboards.inline import PermissionReplyCD

    msg = make_message(bot, message_id=1, text="🔐 Требуется разрешение:")
    cd = PermissionReplyCD(request_id="req-1", reply="always")
    callback = make_callback(bot, data=cd.pack(), message=msg)
    await on_permission_reply(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo))
    calls = fake_kilo.calls_for("permission.reply")
    assert calls and calls[0].args == ("req-1", "always")


async def test_permission_reply_reject(
    bot: Bot, fake_kilo: FakeKilo
) -> None:
    from kilocode_tg_bot.handlers.permissions import on_permission_reply
    from kilocode_tg_bot.keyboards.inline import PermissionReplyCD

    msg = make_message(bot, message_id=1, text="🔐 Требуется разрешение:")
    cd = PermissionReplyCD(request_id="req-2", reply="reject")
    callback = make_callback(bot, data=cd.pack(), message=msg)
    await on_permission_reply(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo))
    calls = fake_kilo.calls_for("permission.reply")
    assert calls and calls[0].args == ("req-2", "reject")


async def test_permission_reply_error_is_friendly(
    bot: Bot, fake_kilo: FakeKilo
) -> None:
    from kilocode_tg_bot.handlers.permissions import on_permission_reply
    from kilocode_tg_bot.keyboards.inline import PermissionReplyCD

    fake_kilo.fail("permission.reply", KiloError(message="expired", status_code=404))
    msg = make_message(bot, message_id=1, text="🔐 Требуется разрешение:")
    cd = PermissionReplyCD(request_id="req-1", reply="once")
    callback = make_callback(bot, data=cd.pack(), message=msg)
    await on_permission_reply(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo))
    assert fake_kilo.called("permission.reply")
    # no crash; the message stays (or got a reply)
    assert records(bot).calls


async def test_permissions_empty_shows_message(bot: Bot, fake_kilo: FakeKilo) -> None:
    from kilocode_tg_bot.handlers.permissions import on_permissions

    message = make_message(bot, text="/permissions")
    await on_permissions(message, kilo=cast(Kilo, fake_kilo))
    assert any("Ожидающих запросов на разрешение нет" in s for s in _texts(bot))


async def test_permissions_with_pending_shows_keyboard(
    bot: Bot, fake_kilo: FakeKilo
) -> None:
    from kilocode_tg_bot.handlers.permissions import on_permissions

    fake_kilo.seed_pending_permission("req-1", "write")
    message = make_message(bot, text="/permissions")
    await on_permissions(message, kilo=cast(Kilo, fake_kilo))
    assert any("Запрос разрешения" in s for s in _texts(bot))


async def test_allow_all_on(bot: Bot, fake_kilo: FakeKilo, make_command: Any) -> None:
    from kilocode_tg_bot.handlers.permissions import on_allow_all

    message = make_message(bot, text="/allow_all on")
    await on_allow_all(
        message, command=make_command("on", "allow_all"), kilo=cast(Kilo, fake_kilo)
    )
    calls = fake_kilo.calls_for("permission.allow_everything")
    assert calls and calls[0].args == (True,)
    assert any("включено" in s for s in _texts(bot))


async def test_allow_all_off(bot: Bot, fake_kilo: FakeKilo, make_command: Any) -> None:
    from kilocode_tg_bot.handlers.permissions import on_allow_all

    message = make_message(bot, text="/allow_all off")
    await on_allow_all(
        message, command=make_command("off", "allow_all"), kilo=cast(Kilo, fake_kilo)
    )
    calls = fake_kilo.calls_for("permission.allow_everything")
    assert calls and calls[0].args == (False,)


async def test_allow_all_bad_arg_shows_usage(
    bot: Bot, fake_kilo: FakeKilo, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.permissions import on_allow_all

    message = make_message(bot, text="/allow_all whatever")
    await on_allow_all(
        message, command=make_command("whatever", "allow_all"), kilo=cast(Kilo, fake_kilo)
    )
    assert not fake_kilo.called("permission.allow_everything")
    assert any("Использование" in s for s in _texts(bot))
