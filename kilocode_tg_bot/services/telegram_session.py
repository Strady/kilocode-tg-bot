"""Build the aiogram HTTP session, optionally routing Telegram traffic via a proxy.

aiogram's :class:`AiohttpSession` accepts a ``proxy`` argument (URL or ``(url,
auth)`` pair / chain) and builds an ``aiohttp_socks`` connector from it, so an
HTTP or SOCKS proxy with credentials is fully supported. When no proxy is
configured we fall back to the default session so behaviour is unchanged.
"""

from __future__ import annotations

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.base import BaseSession

from kilocode_tg_bot.config import Settings


def build_session(settings: Settings) -> BaseSession:
    """Return an :class:`AiohttpSession`, proxied when configured."""
    proxy = settings.telegram_proxy()
    if proxy is None:
        return AiohttpSession()
    return AiohttpSession(proxy=proxy)


__all__ = ["build_session"]
