# Test suite

Tests for the `kilocode_tg_bot` Telegram bot. Two flavours are provided:

- **Offline** (`pytest -m "not live"`) — run in clean CI with **no network, no
  Telegram, and no `kilo serve`**. The Telegram transport is a recording fake and
  the Kilo dependency is an in-memory fake, so everything is deterministic and fast.
- **Live** (`pytest -m live`) — a small subset that talks to a **real**
  `kilo serve` through the bot's own dispatcher chain (middleware → handler → real
  client → real server). Telegram stays mocked; they are skipped automatically when
  no server is reachable.

```
tests/
├── conftest.py                  shared fixtures (store, fake Kilo, bot, dispatcher, …)
├── fakes/
│   ├── fake_kilo.py             in-memory Kilo stand-in with call recording + error faking
│   ├── fake_telegram.py         RecordingSession + make_* builders (+ `records(bot)` helper)
│   └── events.py                KiloEvent stream builders (text delta / tool / permission / turn)
├── handlers/                    level-1 handler tests, one file per router
├── middlewares/                 auth middleware tests
├── unit/                        config, session store, streaming throttle
├── integration/                 level-2 dispatcher routing + full chat scenario
├── live/                        level-4 tests against a real `kilo serve`
├── test_bot_assembly.py         bot wiring (bot.py) on the fakes
├── test_error_handling.py       friendly-error translation across routers
└── test_integration_mocked.py   workflow against an in-memory fake client
```

## Requirements

The gate that must pass before merging:

```bash
.venv/bin/python -m pytest tests -m "not live"                  # all offline tests green
.venv/bin/ruff check kilocode_tg_bot tests                       # no lint errors
.venv/bin/ty check                                                # no type errors
.venv/bin/python -m pytest tests -m "not live" --cov=kilocode_tg_bot.handlers \
    --cov=kilocode_tg_bot.middlewares --cov=kilocode_tg_bot.state --cov-report=term
# coverage >= 85% on handlers/, middlewares/ and state/
```

## Running the tests

Offline (everything that matters for CI):

```bash
pytest tests -m "not live"
```

Run a single area:

```bash
pytest tests/handlers -m "not live"      # handler-level
pytest tests/integration -m "not live"   # dispatcher routing + full chat
pytest tests/unit       -m "not live"    # config / store / throttle
pytest -k history -m "not live"          # just the new /history coverage tests
```

Live (optional, requires a server):

```bash
kilo serve --port 4096          # start in another terminal
KILO_SERVER_URL=http://127.0.0.1:4096 pytest -m live
```

If `KILO_SERVER_URL` is unreachable the live tests skip with a clear message; they
never fail just because a server is down.

## How offline tests work

### Transport: the `RecordingSession` (`tests/fakes/fake_telegram.py`)

Level-3 of the plan asks us to observe *exactly which Telegram API calls the bot
made* (`sendMessage`, `editMessageText`, `sendDocument`, …). We swap the bot's HTTP
transport for a `RecordingSession` — a real
`aiogram.client.session.base.BaseSession` — that:

- records every `make_request` into `calls` as `CallRecord(method, data)`, and
- returns an inert, **bot-bound** `Message` for message-returning methods.

Because returned messages keep their `_bot`, handlers can keep chaining
`answer(...)` / `edit_text(...)` and those calls land in the same recording. One
mechanism therefore covers handler-level (1), dispatcher-level (2) and
call-counting (3) tests.

There is a small typing wrinkle: aiogram types `Bot.session` as the abstract
`BaseSession`, which has no `calls`. Use the `records(bot)` helper to get it typed
as the `RecordingSession` it really is:

```python
from tests.fakes.fake_telegram import records
texts = [c.text() for c in records(bot).calls if c.method == "sendMessage"]
```

### The `FakeKilo` (`tests/fakes/fake_kilo.py`)

A drop-in for `kilocode_client.Kilo` mirroring the same namespaces the handlers
call (`session.*`, `permission.*`, `model/agent`, tools, export/import, health,
interrupt, `stream_session_events`, …). It:

- **records** every call (flat `calls` list of `FuncCall`, plus per-namespace lists)
  for later assertions — use `fake_kilo.called("session.delete")` /
  `calls_for("permission.reply")`.
- **simulates errors** per method via `fake_kilo.fail("session.create", TimeoutError(...))`.
- **replays an SSE stream** via `set_stream_events(session_id, [events…])` +
  `event_delay` so tests drive the throttling / tool / permission / turn-close paths.

Seed data with `seed_session`, `seed_message`, `seed_todo`, `seed_pending_permission`,
`provide_model_state`.

### Shared fixtures (`tests/conftest.py`)

| fixture          | purpose                                                        |
|------------------|----------------------------------------------------------------|
| `settings`       | `Settings` with a fake token and owner id                       |
| `store`          | a fresh `SessionStore` (tmp sqlite)                             |
| `fake_kilo`      | a fresh `FakeKilo` per test                                     |
| `bot`            | a `Bot` on a `RecordingSession`                                 |
| `dispatcher`     | real `Dispatcher` with Auth + Context middleware + all routers  |
| `make_message`   | build a bot-bound `Message`                                     |
| `make_callback`  | build a bot-bound `CallbackQuery`                               |
| `make_command`   | build a `CommandObject` for router args                          |
| `active_store`   | store pre-populated with an active session                      |
| `fsm`            | `FSMContext` bound to owner id                                  |
| `feed`           | synchronous `feed_raw_update` for dispatcher-level tests        |

Direct handler calls take `kilo=cast(Kilo, fake_kilo)` to satisfy the runtime DI
annotation; exact handler surces are imported inside each test.

## Adding / extending tests

**Extend a router's test file** for a new branch in `handlers/*.py`. Each router
has its own file under `tests/handlers/` (`test_sessions.py`, `test_chat.py`,
…): build a message, call the handler (or `feed` a raw update for the dispatcher
path), and assert on the recorded Telegram calls plus the fake's recorded Kilo
calls.

**Extend `FakeKilo`** when a handler calls a client method the fake doesn't mirror
yet: record the call, expose a `_do_*` that mutates the in-memory DB, seed helpers
as needed, and wire `self._call("namespace.method", ...)` so `fail(...)` keeps
working. Keep returning real kilocode models so handlers exercise identical
attribute paths.

**Extend the stream coverage**: add event sequences to `tests/fakes/events.py`
(reuse `text_delta` / `tool_event` / `permission_event` / `turn_close` / `text_turn`)
and point `set_stream_events` at them in `tests/handlers/test_chat.py` or
`tests/unit/test_streaming_throttle.py`.

**Live tests** (`tests/live/`) mirror the important flows against a real server.
They need a `real_kilo` (function-scoped on purpose — a shared client would bind
HTTP primitives to one event loop and trip a *"bound to a different event loop"*),
a `live_dispatcher` and the async `feed` in `tests/live/conftest.py`. Environment:
`KILO_SERVER_URL` (default `http://127.0.0.1:4096`), optional
`KILO_SERVER_USERNAME` / `KILO_SERVER_PASSWORD`. Avoid awaiting a long-lived SSE
stream through `feed()` in error tests against a real server — that is timing
dependent; assert deterministic typed errors via the client instead (the friendly
translation is covered offline in `tests/test_error_handling.py`).

## Why not `aiogram_tests` / an external framework?

An external framework adds a dependency and a second way to express the same
assertions. One in-repo `RecordingSession` + the fakes cover all of:
handler-level direct calls, dispatcher routing via `feed_raw_update`, and
outgoing-call counting — with no network, no plugin, and full visibility into both
Telegram and Kilo call surfaces. This is documented here so future readers know the
choice was deliberate.