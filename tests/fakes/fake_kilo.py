"""A drop-in fake for :class:`kilocode_client.Kilo`.

It mirrors the same public surface the bot handlers call (session CRUD, prompt
streaming, permissions, model/agent, tools, export/import, health), records every
call with its arguments for later assertions, and lets a test seed sessions,
messages, providers/models/agents and the SSE event stream it wants to replay.
Errors (HTTP/network/stream-break) can be enabled per method so tests can verify
the bot degrades gracefully.

The fake returns real :class:`kilocode_client` pydantic models where production
does, so handlers exercise the same attribute access paths. Call recording is
organized under ``calls`` as a flat list of ``FuncCall(method, args, kwargs)`` and
also kept on each namespace (``session.calls``, ``permission.calls``) for
convenience.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from kilocode_client import KiloError, MessageWithParts, SessionInfo, SessionMessage, Todo
from kilocode_client.models import Message, SessionModelRef, TextPart

EventFactory = Callable[[], AsyncIterator[Any]]


@dataclass
class FuncCall:
    """A recorded invocation of a fake method."""

    method: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)


class _FakeSession:
    """Session CRUD namespace (``kilo.session.*``)."""

    def __init__(self, kilo: FakeKilo) -> None:
        self._kilo = kilo

    def _rec(self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self._kilo._record("session." + method, args, kwargs)

    async def create(self, title: str | None = None, **kwargs: Any) -> SessionInfo:
        self._rec("create", (title,), kwargs)
        return await self._kilo._call("session.create", self._kilo._do_create, title)

    async def list_sessions(self, **query: Any) -> list[SessionInfo]:
        self._rec("list_sessions", (), query)
        return await self._kilo._call(
            "session.list_sessions", self._kilo._do_list_sessions, query
        )

    async def get(self, session_id: str) -> SessionInfo:
        self._rec("get", (session_id,), {})
        return await self._kilo._call("session.get", self._kilo._do_get, session_id)

    async def delete(self, session_id: str) -> bool:
        self._rec("delete", (session_id,), {})
        return await self._kilo._call("session.delete", self._kilo._do_delete, session_id)

    async def rename(self, session_id: str, title: str) -> SessionInfo:
        self._rec("rename", (session_id, title), {})
        return await self._kilo._call(
            "session.rename", self._kilo._do_rename, session_id, title
        )

    async def fork(self, session_id: str, **kwargs: Any) -> SessionInfo:
        self._rec("fork", (session_id,), kwargs)
        return await self._kilo._call(
            "session.fork", self._kilo._do_fork, session_id, kwargs.get("message_id")
        )


class _FakePermission:
    """Permission namespace (``kilo.permission.*``)."""

    def __init__(self, kilo: FakeKilo) -> None:
        self._kilo = kilo
        self.calls: list[FuncCall] = []

    def _rec(self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self._kilo._record("permission." + method, args, kwargs)
        self.calls.append(FuncCall(method, args, kwargs))

    async def reply(self, request_id: str, response: str, **kwargs: Any) -> bool:
        self._rec("reply", (request_id, response), kwargs)
        return await self._kilo._call(
            "permission.reply", lambda rid, resp: True, request_id, response
        )

    async def allow_everything(self, enable: bool, **kwargs: Any) -> bool:
        self._rec("allow_everything", (enable,), kwargs)
        return await self._kilo._call(
            "permission.allow_everything", lambda enable: True, enable
        )

    async def list_pending(self) -> list[dict[str, Any]]:
        self._rec("list_pending", (), {})
        return await self._kilo._call("permission.list_pending", self._kilo._do_list_pending)


class FakeKilo:
    """In-memory :class:`Kilo` stand-in with call recording and error simulation.

    Seed the fake by either calling the same methods the bot uses (they mutate the
    in-memory DB) or by loading preset objects through :meth:`seed_session`,
    :meth:`seed_message`, :meth:`seed_todo`. Replay a prompt stream by assigning
    ``events`` (an async iterator of :class:`KiloEvent`) and, to pause between
    events, ``event_delay`` (seconds).
    """

    def __init__(self) -> None:
        self._db: dict[str, SessionInfo] = {}
        self._messages: dict[str, list[MessageWithParts]] = {}
        self._todos: dict[str, list[Todo]] = {}
        self._pending: list[dict[str, Any]] = []
        self.calls: list[FuncCall] = []
        self.error_overrides: dict[str, Exception] = {}
        self.events: EventFactory | None = None
        self.event_delay: float = 0.0
        self._counter = 0

        self.session = _FakeSession(self)
        self.permission = _FakePermission(self)

    # -- configuration ---------------------------------------------------------

    def _record(self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.calls.append(FuncCall(method, args, kwargs))

    def _override(self, method: str) -> Exception | None:
        return self.error_overrides.get(method)

    async def _call(self, method: str, fn: Callable[..., Any], *args: Any) -> Any:
        exc = self._override(method)
        if exc is not None:
            raise exc
        result = fn(*args)
        if hasattr(result, "__await__"):
            return await result
        return result

    def fail(self, method: str, exc: Exception) -> None:
        """Make ``method`` raise ``exc`` on its next invocation."""
        self.error_overrides[method] = exc

    # -- seeding ---------------------------------------------------------------

    def seed_session(
        self,
        session_id: str,
        title: str = "untitled",
        model: SessionModelRef | None = None,
        agent: str | None = None,
    ) -> SessionInfo:
        session = SessionInfo(
            id=session_id,
            projectID="p1",
            title=title,
            model=model,
            agent=agent,
        )
        self._db[session_id] = session
        return session

    def seed_message(
        self, session_id: str, role: str, message_id: str, text: str
    ) -> MessageWithParts:
        msg = MessageWithParts(
            info=Message(id=message_id, sessionID=session_id, role=role),
            parts=[
                TextPart(
                    id=f"p-{message_id}",
                    sessionID=session_id,
                    messageID=message_id,
                    text=text,
                )
            ],
        )
        self._messages.setdefault(session_id, []).append(msg)
        return msg

    def seed_todo(self, session_id: str, content: str, status: str = "pending") -> Todo:
        todo_id = f"todo-{len(self._todos.get(session_id, []))}"
        todo = Todo(id=todo_id, sessionID=session_id, content=content, status=status)
        self._todos.setdefault(session_id, []).append(todo)
        return todo

    def seed_pending_permission(self, request_id: str, permission: str = "write") -> None:
        self._pending.append({"id": request_id, "permission": permission, "patterns": ["/a"]})

    def provide_model_state(self, provider_id: str, model_id: str) -> None:
        self._active_model = SessionModelRef(id=model_id, providerID=provider_id)

    # -- core session operations -----------------------------------------------

    def _do_create(self, title: str | None) -> SessionInfo:
        self._counter += 1
        sid = f"session-{self._counter:02d}"
        session = self.seed_session(sid, title or "untitled")
        return session

    async def _do_list_sessions(self, query: dict[str, Any]) -> list[SessionInfo]:
        return list(self._db.values())

    async def _do_get(self, session_id: str) -> SessionInfo:
        if session_id not in self._db:
            raise KiloError(message=f"Session {session_id} not found", status_code=404)
        return self._db[session_id]

    async def _do_delete(self, session_id: str) -> bool:
        existed = session_id in self._db
        self._db.pop(session_id, None)
        return existed

    async def _do_rename(self, session_id: str, title: str) -> SessionInfo:
        session = self._db[session_id]
        session.title = title
        return session

    async def _do_fork(self, session_id: str, message_id: str | None) -> SessionInfo:
        parent = self._db[session_id]
        self._counter += 1
        sid = f"session-{self._counter:02d}"
        return self.seed_session(sid, f"{parent.title}-fork")

    # -- permissions -----------------------------------------------------------

    async def _do_list_pending(self) -> list[dict[str, Any]]:
        return list(self._pending)

    # -- model / agent ---------------------------------------------------------

    async def list_providers(self, directory: str | None = None) -> list[dict[str, Any]]:
        self._record("list_providers", (directory,), {})
        return await self._call(
            "list_providers", lambda: [{"id": "openai", "name": "OpenAI"}]
        )

    async def list_models(self, directory: str | None = None) -> list[dict[str, Any]]:
        self._record("list_models", (directory,), {})
        return await self._call(
            "list_models",
            lambda: [
                {"id": "gpt-4o", "name": "GPT-4o", "providerID": "openai"},
                {"id": "claude", "name": "Claude", "providerID": "anthropic"},
            ],
        )

    async def list_agents(self) -> list[dict[str, Any]]:
        self._record("list_agents", (), {})
        return await self._call(
            "list_agents", lambda: [{"name": "general"}, {"name": "coder"}]
        )

    async def change_model(
        self, session_id: str, provider_id: str, model_id: str, agent: str | None = None
    ) -> bool:
        self._record("change_model", (session_id, provider_id, model_id), {"agent": agent})
        return await self._call(
            "change_model",
            lambda: self._do_change_model(session_id, provider_id, model_id, agent),
        )

    def _do_change_model(
        self, session_id: str, provider_id: str, model_id: str, agent: str | None
    ) -> bool:
        if session_id not in self._db:
            raise KiloError(message=f"Session {session_id} not found", status_code=404)
        self._db[session_id].model = SessionModelRef(id=model_id, providerID=provider_id)
        self._db[session_id].agent = agent
        return True

    # -- prompts / streaming ---------------------------------------------------

    async def send_prompt_async(self, session_id: str, text: str) -> None:
        self._record("send_prompt_async", (session_id, text), {})
        exc = self._override("send_prompt_async")
        if exc is not None:
            raise exc

    async def stream_session_events(
        self, session_id: str, *, instance: bool = False
    ) -> AsyncIterator[Any]:
        self._record("stream_session_events", (session_id,), {"instance": instance})
        exc = self._override("stream_session_events")
        if exc is not None:
            raise exc
        if session_id not in self._db:
            raise KiloError(message=f"Session {session_id} not found", status_code=404)

        async def empty() -> AsyncIterator[Any]:
            if False:  # pragma: no cover - makes the generator async
                yield None
            return

        if self.events is None:
            return empty()
        return self._delay(self.events())

    async def _delay(self, source: AsyncIterator[Any]) -> AsyncIterator[Any]:
        import asyncio

        async for event in source:
            if self.event_delay:
                await asyncio.sleep(self.event_delay)
            yield event

    async def set_stream_events(self, session_id: str, events: list[Any]) -> None:
        async def gen() -> AsyncIterator[Any]:
            for event in events:
                yield event

        self.events = gen

    # -- tools ---------------------------------------------------------------

    async def interrupt(self, session_id: str) -> bool:
        self._record("interrupt", (session_id,), {})
        return await self._call("interrupt", lambda sid: True, session_id)

    async def run_command(
        self, session_id: str, command: str, arguments: str = ""
    ) -> MessageWithParts:
        self._record("run_command", (session_id, command, arguments), {})
        return await self._call(
            "run_command", self._do_run_command, session_id, command, arguments
        )

    def _do_run_command(
        self, session_id: str, command: str, arguments: str
    ) -> MessageWithParts:
        self.seed_message(session_id, "assistant", f"cmd-{command}", f"ran /{command} {arguments}")
        return self._messages[session_id][-1]

    async def run_shell(
        self,
        session_id: str,
        command: str,
        arguments: str = "",
        *,
        agent: str,
    ) -> MessageWithParts:
        self._record("run_shell", (session_id, command, arguments), {"agent": agent})
        return await self._call(
            "run_shell", self._do_run_shell, session_id, command, arguments, agent
        )

    def _do_run_shell(
        self, session_id: str, command: str, arguments: str, agent: str
    ) -> MessageWithParts:
        self.seed_message(session_id, "assistant", f"shl-{command}", f"$ {command} {arguments}")
        return self._messages[session_id][-1]

    async def compact_v2(self, session_id: str) -> None:
        self._record("compact_v2", (session_id,), {})
        exc = self._override("compact_v2")
        if exc is not None:
            raise exc

    async def get_context(self, session_id: str) -> list[SessionMessage]:
        self._record("get_context", (session_id,), {})
        return await self._call("get_context", lambda sid: [], session_id)

    async def get_todos(self, session_id: str) -> list[Todo]:
        self._record("get_todos", (session_id,), {})
        return await self._call(
            "get_todos", self._do_get_todos, session_id
        )

    async def _do_get_todos(self, session_id: str) -> list[Todo]:
        return list(self._todos.get(session_id, []))

    async def list_messages(
        self, session_id: str, limit: int | None = None
    ) -> list[MessageWithParts]:
        self._record("list_messages", (session_id,), {"limit": limit})
        return await self._call(
            "list_messages", self._do_list_messages, session_id, limit
        )

    async def _do_list_messages(
        self, session_id: str, limit: int | None
    ) -> list[MessageWithParts]:
        return list(self._messages.get(session_id, []))

    async def revert(
        self, session_id: str, message_id: str, part_id: str | None = None
    ) -> SessionInfo:
        self._record("revert", (session_id, message_id), {"part_id": part_id})
        return await self._call(
            "revert", self._do_get, session_id
        )

    async def unrevert(self, session_id: str) -> SessionInfo:
        self._record("unrevert", (session_id,), {})
        return await self._call("unrevert", self._do_get, session_id)

    # -- export / import -------------------------------------------------------

    async def export_session_to_file(self, session_id: str, path: str) -> None:
        import json

        self._record("export_session_to_file", (session_id, path), {})
        exc = self._override("export_session_to_file")
        if exc is not None:
            raise exc
        if session_id not in self._db:
            raise KiloError(message=f"Session {session_id} not found", status_code=404)
        doc = {
            "session": {"id": session_id, "title": self._db[session_id].title},
            "messages": [],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)

    async def import_session(self, session: dict[str, Any]) -> dict[str, Any]:
        self._record("import_session", (session,), {})
        return await self._call(
            "import_session", self._do_import_session, session
        )

    async def _do_import_session(self, session: dict[str, Any]) -> dict[str, Any]:
        sid = str(
            session.get("session", {}).get("id")
            or session.get("id")
            or f"imp-{self._counter}"
        )
        title = str(session.get("session", {}).get("title") or "imported")
        self.seed_session(sid, title)
        return {"session": {"id": sid, "title": title}}

    # -- health ----------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        self._record("health", (), {})
        return await self._call(
            "health", lambda: {"status": "ok", "version": "test"}
        )

    # -- test utilities --------------------------------------------------------

    def called(self, *methods: str) -> bool:
        """True if every named method has been called at least once."""
        names = {c.method for c in self.calls}
        return all(m in names for m in methods)

    def calls_for(self, method: str) -> list[FuncCall]:
        return [c for c in self.calls if c.method == method]

    @property
    def active_model(self) -> SessionModelRef | None:
        return getattr(self, "_active_model", None)


def make_session_info(
    session_id: str, title: str = "untitled", model: SessionModelRef | None = None
) -> SessionInfo:
    """Build a real ``SessionInfo`` handy for seeding or assertions."""
    return SessionInfo(id=session_id, projectID="p1", title=title, model=model)


__all__ = [
    "FakeKilo",
    "FuncCall",
    "_FakeSession",
    "_FakePermission",
    "make_session_info",
]
