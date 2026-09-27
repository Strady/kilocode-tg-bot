"""Handler-level tests for the tool commands: /run /shell /compact /context /todo /revert /unrevert.

``/shell`` is confirm-guarded: the first step only stores the command and asks; the actual
``run_shell`` call happens only after the user confirms via the inline button.
"""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot
from kilocode_client import Kilo, KiloError
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_callback, make_message, records

ACTIVE = "session-01"


def _config() -> Any:
    from kilocode_tg_bot.config import Settings

    return Settings(telegram_bot_token="123456:TEST-TOKEN", telegram_allowed_user_id=42)


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]


def _edits(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "editMessageText"]


async def _activate(fake_kilo: FakeKilo, store: Any) -> None:
    fake_kilo.seed_session(ACTIVE, "demo")
    await store.set_active(42, ACTIVE)


async def test_run_command(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_run

    await _activate(fake_kilo, store)
    message = make_message(bot, text="/run /help")
    await on_run(
        message, command=make_command("/help", "run"), kilo=cast(Kilo, fake_kilo), store=store
    )
    calls = fake_kilo.calls_for("run_command")
    assert calls and calls[0].args == (ACTIVE, "help", "")
    assert any("ran /help" in s for s in _texts(bot))


async def test_run_requires_args(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_run

    await _activate(fake_kilo, store)
    message = make_message(bot, text="/run")
    await on_run(
        message, command=make_command(None, "run"), kilo=cast(Kilo, fake_kilo), store=store
    )
    assert not fake_kilo.called("run_command")
    assert any("Использование" in s for s in _texts(bot))


async def test_shell_first_step_does_not_run(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_shell

    await _activate(fake_kilo, store)
    message = make_message(bot, text="/shell pwd")
    await on_shell(
        message,
        command=make_command("pwd", "shell"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
        state=fsm,
    )
    # must NOT call run_shell yet
    assert not fake_kilo.called("run_shell")
    sent = "\n".join(_texts(bot))
    assert "Выполнить shell-команду" in sent
    data = await fsm.get_data()
    assert data["session_id"] == ACTIVE
    assert data["command"] == "pwd"


async def test_shell_confirm_runs(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_shell, on_shell_confirm
    from kilocode_tg_bot.keyboards.inline import ShellConfirmCD

    await _activate(fake_kilo, store)
    msg = make_message(bot, text="/shell ls -la")
    await on_shell(
        msg,
        command=__make_command("ls -la", "shell"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
        state=fsm,
    )
    base = make_message(bot, message_id=2, text="Выполнить shell-команду?")
    cd = ShellConfirmCD(action="run")
    callback = make_callback(bot, data=cd.pack(), message=base)
    await on_shell_confirm(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo), state=fsm)
    calls = fake_kilo.calls_for("run_shell")
    assert calls and calls[0].args == (ACTIVE, "ls", "-la")


async def test_shell_cancel_does_not_run(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_shell, on_shell_confirm
    from kilocode_tg_bot.keyboards.inline import ShellConfirmCD

    await _activate(fake_kilo, store)
    msg = make_message(bot, text="/shell rm -rf /")
    await on_shell(
        msg,
        command=__make_command("rm -rf /", "shell"),
        kilo=cast(Kilo, fake_kilo),
        store=store,
        state=fsm,
    )
    base = make_message(bot, message_id=3, text="Выполнить shell-команду?")
    cd = ShellConfirmCD(action="cancel")
    callback = make_callback(bot, data=cd.pack(), message=base)
    await on_shell_confirm(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo), state=fsm)
    assert not fake_kilo.called("run_shell")
    assert any("отменена" in e for e in _edits(bot))


async def test_compact(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_compact

    await _activate(fake_kilo, store)
    message = make_message(bot, text="/compact")
    await on_compact(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_config())
    assert fake_kilo.called("compact_v2")
    assert any("Контекст сжат" in s for s in _texts(bot))


async def test_compact_error_is_friendly(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_compact

    await _activate(fake_kilo, store)
    fake_kilo.fail("compact_v2", KiloError(message="no compact", status_code=400))
    message = make_message(bot, text="/compact")
    await on_compact(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_config())
    assert any("Kilo server error" in s for s in _texts(bot))


async def test_context_empty(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_context

    await _activate(fake_kilo, store)
    message = make_message(bot, text="/context")
    await on_context(message, kilo=cast(Kilo, fake_kilo), store=store, settings=_config())
    assert fake_kilo.called("get_context")
    assert any("нет" in s.lower() or "сообщений нет" in s for s in _texts(bot))


async def test_todo_empty(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_todo

    await _activate(fake_kilo, store)
    message = make_message(bot, text="/todo")
    await on_todo(message, kilo=cast(Kilo, fake_kilo), store=store)
    assert fake_kilo.called("get_todos")
    assert any("пуст" in s for s in _texts(bot))


async def test_todo_with_items(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_todo

    await _activate(fake_kilo, store)
    fake_kilo.seed_todo(ACTIVE, "Fix bug", "pending")
    fake_kilo.seed_todo(ACTIVE, "Ship it", "completed")
    message = make_message(bot, text="/todo")
    await on_todo(message, kilo=cast(Kilo, fake_kilo), store=store)
    sent = "\n".join(_texts(bot))
    assert "Fix bug" in sent and "Ship it" in sent


async def test_revert_with_message_id(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_revert

    await _activate(fake_kilo, store)
    fake_kilo.seed_message(ACTIVE, "assistant", "msg-1", "text")
    message = make_message(bot, text="/revert msg-1")
    await on_revert(
        message, command=make_command("msg-1", "revert"), kilo=cast(Kilo, fake_kilo), store=store
    )
    calls = fake_kilo.calls_for("revert")
    assert calls and calls[0].args[0] == ACTIVE and calls[0].args[1] == "msg-1"


async def test_revert_without_id_uses_last_assistant(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_revert

    await _activate(fake_kilo, store)
    fake_kilo.seed_message(ACTIVE, "user", "m1", "u")
    fake_kilo.seed_message(ACTIVE, "assistant", "m2", "a")
    message = make_message(bot, text="/revert")
    await on_revert(
        message, command=make_command(None, "revert"), kilo=cast(Kilo, fake_kilo), store=store
    )
    calls = fake_kilo.calls_for("revert")
    assert calls and calls[0].args[1] == "m2"


async def test_unrevert(
    bot: Bot, fake_kilo: FakeKilo, store: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_unrevert

    await _activate(fake_kilo, store)
    message = make_message(bot, text="/unrevert")
    await on_unrevert(message, kilo=cast(Kilo, fake_kilo), store=store)
    assert fake_kilo.called("unrevert")
    assert any("unrevert" in s.lower() for s in _texts(bot))


async def test_tools_no_active_session(
    bot: Bot, fake_kilo: FakeKilo, store: Any, make_command: Any
) -> None:
    from kilocode_tg_bot.handlers.tools import on_run

    message = make_message(bot, text="/run /help")
    await on_run(
        message, command=make_command("/help", "run"), kilo=cast(Kilo, fake_kilo), store=store
    )
    assert not fake_kilo.called("run_command")
    assert any("Нет активной сессии" in s for s in _texts(bot))


def __make_command(args: str, command: str) -> Any:
    from aiogram.filters import CommandObject

    return CommandObject(command=command, args=args)
