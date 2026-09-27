"""Switch the active session's model (/model) or agent (/agent).

Model switching is a two-step inline flow: pick a provider, then a model. Agent
switching is a one-step flow. Both apply through ``kilo.change_model``, passing
``agent=`` when only an agent is being changed.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from kilocode_client import Kilo

from kilocode_tg_bot.handlers.common import call_kilo, editable_message
from kilocode_tg_bot.keyboards.inline import (
    AgentSelectCD,
    ModelProviderCD,
    ModelSelectCD,
    agents_keyboard,
    models_keyboard,
    providers_keyboard,
)
from kilocode_tg_bot.state.session_store import SessionStore
from kilocode_tg_bot.state.states import AgentSelectStates, ModelSelectStates

router = Router(name="model_agent")


def _provider_id(p: dict) -> str:
    return str(p.get("id") or p.get("providerID") or p.get("name") or "")


def _provider_name(p: dict) -> str:
    return str(p.get("name") or p.get("displayName") or _provider_id(p))


def _model_id(m: dict) -> str:
    return str(m.get("id") or m.get("modelID") or "")


def _model_name(m: dict) -> str:
    return str(m.get("name") or m.get("displayName") or _model_id(m))


def _model_provider(m: dict) -> str:
    return str(m.get("providerID") or m.get("provider") or "")


@router.message(Command("model"))
async def on_model(message: Message, kilo: Kilo, state: FSMContext, store: SessionStore) -> None:
    user_id = message.from_user.id if message.from_user else 0
    session_id = await store.get_active(user_id)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    providers = await call_kilo(lambda: kilo.list_providers(), message)
    if providers is None:
        return
    await state.set_state(ModelSelectStates.choosing_provider)
    await state.update_data(session_id=session_id)
    kb = providers_keyboard(providers, _provider_id, _provider_name)
    await message.answer("Выберите провайдера:", reply_markup=kb)


@router.callback_query(ModelProviderCD.filter())
async def on_provider(
    callback: CallbackQuery, callback_data: ModelProviderCD, kilo: Kilo, state: FSMContext
) -> None:
    data = await state.get_data()
    session_id = data.get("session_id")
    if not session_id:
        await callback.answer("Сессия не выбрана. Начните /model заново")
        return
    msg = editable_message(callback)
    if msg is None:
        await callback.answer("Сообщение недоступно. Начните /model заново")
        return
    models = await call_kilo(lambda: kilo.list_models(directory=None), msg)
    if models is None:
        return
    provider_id = callback_data.provider_id
    scoped = [m for m in models if _model_provider(m) in (provider_id, "")] or models
    await state.set_state(ModelSelectStates.choosing_model)
    await state.update_data(provider_id=provider_id)
    await msg.edit_text(
        f"Провайдер `{provider_id}`. Выберите модель:",
        reply_markup=models_keyboard(scoped, provider_id, _model_id, _model_name),
    )


@router.callback_query(ModelSelectCD.filter())
async def on_model_pick(
    callback: CallbackQuery, callback_data: ModelSelectCD, kilo: Kilo, state: FSMContext
) -> None:
    data = await state.get_data()
    session_id = data.get("session_id")
    if not session_id:
        await callback.answer("Сессия не выбрана. Начните /model заново")
        return
    msg = editable_message(callback)
    if msg is None:
        await callback.answer("Сообщение недоступно. Начните /model заново")
        return
    ok = await call_kilo(
        lambda: kilo.change_model(session_id, callback_data.provider_id, callback_data.model_id),
        msg,
    )
    if ok is None:
        return
    await state.clear()
    await callback.answer("Модель применена")
    await msg.edit_text(
        f"✅ Модель сменена на `{callback_data.model_id}` "
        f"(provider `{callback_data.provider_id}`).",
        reply_markup=None,
    )


@router.message(Command("agent"))
async def on_agent(message: Message, kilo: Kilo, state: FSMContext, store: SessionStore) -> None:
    user_id = message.from_user.id if message.from_user else 0
    session_id = await store.get_active(user_id)
    if not session_id:
        await message.answer("Нет активной сессии.")
        return
    agents = await call_kilo(lambda: kilo.list_agents(), message)
    if agents is None:
        return
    await state.set_state(AgentSelectStates.choosing_agent)
    await state.update_data(session_id=session_id)
    await message.answer(
        "Выберите агента:",
        reply_markup=agents_keyboard(agents, _provider_name),
    )


@router.callback_query(AgentSelectCD.filter())
async def on_agent_pick(
    callback: CallbackQuery, callback_data: AgentSelectCD, kilo: Kilo, state: FSMContext
) -> None:
    data = await state.get_data()
    session_id = data.get("session_id")
    if not session_id:
        await callback.answer("Сессия не выбрана. Начните /agent заново")
        return

    async def apply() -> bool:
        current = await kilo.session.get(session_id)
        model = current.model
        provider_id = model.providerID if model else ""
        model_id = model.id if model else ""
        return await kilo.change_model(
            session_id, provider_id, model_id, agent=callback_data.agent_name
        )

    msg = editable_message(callback)
    if msg is None:
        await callback.answer("Сообщение недоступно. Начните /agent заново")
        return
    ok = await call_kilo(apply, msg)
    if ok is None:
        return
    await state.clear()
    await callback.answer("Агент применён")
    await msg.edit_text(f"✅ Агент сменён на `{callback_data.agent_name}`.", reply_markup=None)


__all__ = ["router"]
