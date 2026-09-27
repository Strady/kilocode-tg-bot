"""Live error handling: real server errors surface as typed KiloErrors.

The bot turns these into friendly messages; the offline ``tests/test_error_handling.py``
verifies that translation deterministically. Here we only pin the real server's
behaviour for the missing-session cases that don't involve waiting on a live SS
stream (which is timing-dependent and not suitable for a CI test).
"""

from __future__ import annotations

import pytest
from kilocode_client import Kilo, KiloError


@pytest.mark.live
async def test_live_get_missing_session_raises_typed_error(real_kilo: Kilo) -> None:
    with pytest.raises(KiloError):
        await real_kilo.session.get("definitely-not-a-session")


@pytest.mark.live
async def test_live_export_missing_session_raises_typed_error(real_kilo: Kilo) -> None:
    with pytest.raises(KiloError):
        await real_kilo.export_session_to_file("missing-session", "/tmp/nope.json")
