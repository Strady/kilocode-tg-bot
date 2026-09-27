"""Live permission-flow tests against a real ``kilo serve``.

The server only raises a permission prompt when the acting agent/configuration
requests it. We verify the permission API directly (deterministic) and, when a
permission event actually surfaces, the full reply cycle."
"""

from __future__ import annotations

from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from kilocode_client import Kilo, KiloError
from tests.live.conftest import feed


def _raw_msg(user_id: int, text: str) -> dict[str, Any]:
    return {
        "message_id": 1,
        "date": 0,
        "text": text,
        "chat": {"id": 200, "type": "private", "first_name": "Owner", "username": "owner"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Owner", "username": "owner"},
    }


def _raw_callback(user_id: int, data: str) -> dict[str, Any]:
    return {
        "id": f"cq-{data}",
        "from": {"id": user_id, "is_bot": False, "first_name": "Owner", "username": "owner"},
        "chat_instance": "ci1",
        "data": data,
        "message": {
            "message_id": 999,
            "date": 0,
            "text": "base",
            "chat": {"id": 200, "type": "private"},
        },
    }


@pytest.mark.live
async def test_live_permission_endpoints(real_kilo: Kilo) -> None:
    # list_pending must succeed against any reachable server
    pending = await real_kilo.permission.list_pending()
    assert isinstance(pending, list)

    # allow_everything is config-dependent on the server; skip (not fail) when the
    # headless server does not support toggling it, so the live suite stays green
    # on servers that reject it (e.g. some older `kilo serve` builds).
    try:
        enabled = await real_kilo.permission.allow_everything(True)
    except KiloError:
        pytest.skip("server does not support permission.allow_everything")
    assert enabled is True
    try:
        pending_after = await real_kilo.permission.list_pending()
        assert isinstance(pending_after, list)
    finally:
        await real_kilo.permission.allow_everything(False)


@pytest.mark.live
async def test_live_permission_reply_rejects_unknown_request(real_kilo: Kilo) -> None:
    # replying to a request id that is not pending must be a *typed* error the bot
    # renders as a friendly message, not an unexpected crash
    from kilocode_client import KiloError

    with pytest.raises(KiloError):
        await real_kilo.permission.reply("no-such-request", "once")


@pytest.mark.live
async def test_live_permission_flow_via_dispatcher(
    live_dispatcher: tuple[Bot, Dispatcher, Any, Any], real_kilo: Kilo
) -> None:
    bot, dp, rec, store = live_dispatcher
    await feed(dp, bot, {"update_id": 1, "message": _raw_msg(42, "/new permflow")})
    active = await store.get_active(42)
    assert active is not None
    try:
        from kilocode_tg_bot.keyboards.inline import PermissionReplyCD

        await feed(dp, bot, {"update_id": 2, "message": _raw_msg(42, "/shell echo hi")})
        # the shell action may or may not prompt for a permission depending on the
        # server config/agent; handle both so the test stays green but still proves
        # the full button→reply cycle when a prompt does appear.
        pending = await real_kilo.permission.list_pending()
        if not pending:
            pytest.skip("server did not raise a permission prompt for /shell")
        request_id = str(
            pending[0].get("id") if isinstance(pending[0], dict) else getattr(pending[0], "id", "")
        )
        if not request_id:
            pytest.skip("pending permission had no id")
        # answer it through the bot's own callback handler path
        cd = PermissionReplyCD(request_id=request_id, reply="once")
        await feed(
            dp,
            bot,
            {"update_id": 3, "callback_query": _raw_callback(42, data=cd.pack())},
        )
        replies = await real_kilo.permission.list_pending()
        ids = {
            str(r.get("id")) if isinstance(r, dict) else getattr(r, "id", "")
            for r in replies
        }
        assert request_id not in ids, "the answered request should no longer be pending"
    finally:
        try:
            await real_kilo.session.delete(active)
        except Exception:  # noqa: BLE001 - best effort
            pass
