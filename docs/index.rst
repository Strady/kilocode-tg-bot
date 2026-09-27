kilocode-tg-bot
================

A Telegram bot (``aiogram`` 3.x) that acts as a remote control for a KiloCode
headless server (``kilo serve``), talking to it only through the
``kilocode-client`` library.

Features at a glance:

- **Owner-only access** — every update is gated by ``TELEGRAM_ALLOWED_USER_ID``.
- **Streaming chat** — plain-text messages prompt the active session and stream
  deltas back into a single Telegram message, throttled to respect the edit
  rate limit.
- **Sessions** — create, list/switch, rename, fork and delete (with inline
  confirmation).
- **Model/agent switching** — interactive provider → model pickers and agent
  selection.
- **Tools** — compact, context, todo, run, shell (confirmed), revert, unrevert.
- **Permissions** — reply Once/Always/Reject to pending requests.
- **Export/import** — send a session as JSON, or import an uploaded file.

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api