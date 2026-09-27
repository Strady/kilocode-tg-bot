"""FSM states used by the interactive (multi-step) handlers."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ModelSelectStates(StatesGroup):
    """Choosing a provider, then a model, then applying it to the session."""

    choosing_provider = State()
    choosing_model = State()


class AgentSelectStates(StatesGroup):
    """Choosing an agent to apply to the session."""

    choosing_agent = State()


class ShellPendingStates(StatesGroup):
    """Awaiting explicit confirmation before running a shell command."""

    confirming = State()


class _PendingStates(StatesGroup):
    """Stub grouping retained separately for future Pending flows."""

    pending = State()
