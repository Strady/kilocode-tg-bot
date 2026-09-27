"""Unit tests for :func:`kilocode_tg_bot.services.telegram_session.build_session`."""

from __future__ import annotations

from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp_socks import ProxyConnector
from kilocode_tg_bot.config import Settings
from kilocode_tg_bot.services.telegram_session import build_session


def _aiohttp(settings: Settings) -> AiohttpSession:
    """Assert the built session is an ``AiohttpSession`` and narrow its type."""
    session = build_session(settings)
    assert isinstance(session, AiohttpSession)
    return session


class TestBuildSession:
    def test_no_proxy_returns_plain_session(self) -> None:
        session = _aiohttp(
            Settings(
                telegram_bot_token="123456:TEST-TOKEN",
                telegram_allowed_user_id=1,
                _env_file=None,
            )
        )
        assert session._connector_type.__name__ == "TCPConnector"

    def test_proxy_returns_proxied_session(self) -> None:
        session = _aiohttp(
            Settings(
                telegram_bot_token="123456:TEST-TOKEN",
                telegram_allowed_user_id=1,
                telegram_proxy_url="http://proxy.example.com:9999",
                telegram_proxy_username="proxyuser",
                telegram_proxy_password="secret",
                _env_file=None,
            )
        )
        assert session._connector_type is ProxyConnector
        cfg = session._connector_init
        assert cfg["host"] == "proxy.example.com"
        assert cfg["port"] == 9999
        assert cfg["username"] == "proxyuser"
        assert cfg["password"] == "secret"

    def test_proxy_with_embedded_credentials(self) -> None:
        session = _aiohttp(
            Settings(
                telegram_bot_token="123456:TEST-TOKEN",
                telegram_allowed_user_id=1,
                telegram_proxy_url="http://user:pass@proxy.example.com:9999",
                _env_file=None,
            )
        )
        assert session._connector_type is ProxyConnector
        assert session._connector_init["username"] == "user"
        assert session._connector_init["password"] == "pass"

    def test_session_can_be_used_with_bot(self) -> None:
        # Constructing a Bot with the session should not raise.
        from aiogram import Bot

        bot = Bot(
            token="123456:TEST-TOKEN",
            session=build_session(
                Settings(
                    telegram_bot_token="123456:TEST-TOKEN",
                    telegram_allowed_user_id=1,
                    _env_file=None,
                )
            ),
        )
        assert isinstance(bot.session, AiohttpSession)


def test_build_session_needs_no_network() -> None:
    """The session object is created lazily; construction never opens a socket."""
    session = _aiohttp(
        Settings(
            telegram_bot_token="123456:TEST-TOKEN",
            telegram_allowed_user_id=1,
            telegram_proxy_url="http://proxy.example.com:9999",
            _env_file=None,
        )
    )
    # Merely building the session/connector must not connect anywhere.
    assert session._connector_init["host"] == "proxy.example.com"
