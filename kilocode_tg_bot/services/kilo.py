"""Owns the single long-lived ``kilocode_client.Kilo`` instance.

The client is created once when the bot starts and closed on shutdown. Keeping
it module-local (as a plain package-level singleton) lets every handler reach it
without threading the instance through the aiogram DI container. All client
exceptions are normalised here so handlers only have to deal with ``Kilo``
errors, never bare ``httpx`` failures.
"""

from __future__ import annotations

import logging

from kilocode_client import Kilo, KiloError

from kilocode_tg_bot.config import Settings

logger = logging.getLogger(__name__)

_client: Kilo | None = None


def get_client(settings: Settings | None = None) -> Kilo:
    """Return the process-wide :class:`Kilo` client, creating it on first use.

    The client is bound to the current event loop; aiogram runs the whole bot on
    one loop, so the singleton is safe. Pass ``settings`` only on first creation;
    later calls reuse the existing client.
    """
    global _client
    if _client is None:
        if settings is None:
            from kilocode_tg_bot.config import load_settings

            settings = load_settings()
        _client = _build_client(settings)
    return _client


def _build_client(settings: Settings) -> Kilo:
    logger.info("Connecting to Kilo server at %s", settings.kilo_server_url)
    return Kilo(
        base_url=settings.kilo_server_url,
        username=settings.kilo_server_username,
        password=settings.kilo_server_password,
        directory=settings.kilo_server_directory,
    )


async def close_client() -> None:
    """Close the underlying HTTP client and clear the singleton."""
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:  # noqa: BLE001 - never fail shutdown
            logger.exception("Error closing Kilo client")
        _client = None


def humanize_error(exc: Exception) -> str:
    """Turn any raised exception into a short, user-safe message."""
    if isinstance(exc, KiloError):
        detail = getattr(exc, "message", None) or str(exc)
        status = getattr(exc, "status_code", None)
        return f"Kilo server error: {detail}" + (f" (HTTP {status})" if status else "")
    return f"Kilo client error: {exc}"


__all__ = ["get_client", "close_client", "humanize_error"]
