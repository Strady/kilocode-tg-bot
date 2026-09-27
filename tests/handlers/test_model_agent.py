"""Handler-level tests for /model (provider→model flow) and /agent (one-step)."""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot
from kilocode_client import Kilo, KiloError
from tests.fakes.fake_kilo import FakeKilo
from tests.fakes.fake_telegram import make_callback, make_message, records


def _texts(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "sendMessage"]


def _edits(bot: Bot) -> list[str]:
    return [c.text() for c in records(bot).calls if c.method == "editMessageText"]


async def test_model_no_active_session(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.model_agent import on_model

    message = make_message(bot, text="/model")
    await on_model(
        message, kilo=cast(Kilo, fake_kilo), state=fsm, store=store
    )
    assert any("Нет активной сессии" in s for s in _texts(bot))
    assert not fake_kilo.called("list_providers")


async def test_model_shows_providers(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.model_agent import on_model

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    message = make_message(bot, text="/model")
    await on_model(message, kilo=cast(Kilo, fake_kilo), state=fsm, store=store)
    assert fake_kilo.called("list_providers")
    sent = "\n".join(_texts(bot))
    assert "Выберите провайдера" in sent or "OpenAI" in sent


async def test_provider_pick_shows_models(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.model_agent import on_model, on_provider
    from kilocode_tg_bot.keyboards.inline import ModelProviderCD

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    # put the flow in the provider-choosing state
    start_msg = make_message(bot, text="/model")
    await on_model(start_msg, kilo=cast(Kilo, fake_kilo), state=fsm, store=store)

    base = make_message(bot, message_id=50, text="Выберите провайдера:")
    cd = ModelProviderCD(provider_index=0, provider_id="openai")
    callback = make_callback(bot, data=cd.pack(), message=base)
    await on_provider(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo), state=fsm)
    assert fake_kilo.called("list_models")
    assert any("Выберите модель" in e for e in _edits(bot))


async def test_model_pick_applies_model(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.model_agent import on_model_pick
    from kilocode_tg_bot.keyboards.inline import ModelSelectCD

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    await fsm.set_data({"session_id": "s1"})

    base = make_message(bot, message_id=51, text="Выберите модель:")
    cd = ModelSelectCD(provider_id="openai", model_id="gpt-4o", model_index=0)
    callback = make_callback(bot, data=cd.pack(), message=base)
    await on_model_pick(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo), state=fsm)
    calls = fake_kilo.calls_for("change_model")
    assert calls and calls[0].args == ("s1", "openai", "gpt-4o")
    assert any("Модель сменена" in e for e in _edits(bot))


async def test_model_pick_without_session_state(
    bot: Bot, fake_kilo: FakeKilo, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.model_agent import on_model_pick
    from kilocode_tg_bot.keyboards.inline import ModelSelectCD

    base = make_message(bot, message_id=52, text="Выберите модель:")
    cd = ModelSelectCD(provider_id="openai", model_id="gpt-4o", model_index=0)
    callback = make_callback(bot, data=cd.pack(), message=base)
    await on_model_pick(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo), state=fsm)
    assert not fake_kilo.called("change_model")


async def test_agent_shows_agents(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.model_agent import on_agent

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    message = make_message(bot, text="/agent")
    await on_agent(message, kilo=cast(Kilo, fake_kilo), state=fsm, store=store)
    assert fake_kilo.called("list_agents")
    assert any("Выберите агента" in s for s in _texts(bot))


async def test_agent_pick_applies_agent(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.model_agent import on_agent_pick
    from kilocode_tg_bot.keyboards.inline import AgentSelectCD

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    await fsm.set_data({"session_id": "s1"})

    base = make_message(bot, message_id=53, text="Выберите агента:")
    cd = AgentSelectCD(agent_index=0, agent_name="coder")
    callback = make_callback(bot, data=cd.pack(), message=base)
    await on_agent_pick(callback, callback_data=cd, kilo=cast(Kilo, fake_kilo), state=fsm)
    calls = fake_kilo.calls_for("change_model")
    # agent path calls session.get then change_model(..., agent=name)
    assert calls and calls[0].kwargs.get("agent") == "coder"
    assert any("Агент сменён" in e for e in _edits(bot))


async def test_model_provider_error_is_friendly(
    bot: Bot, fake_kilo: FakeKilo, store: Any, fsm: Any
) -> None:
    from kilocode_tg_bot.handlers.model_agent import on_model

    fake_kilo.seed_session("s1", "demo")
    await store.set_active(42, "s1")
    fake_kilo.fail("list_providers", KiloError(message="server down", status_code=500))
    message = make_message(bot, text="/model")
    await on_model(message, kilo=cast(Kilo, fake_kilo), state=fsm, store=store)
    # friendly error, no crash
    assert any("Kilo server error" in s for s in _texts(bot))
