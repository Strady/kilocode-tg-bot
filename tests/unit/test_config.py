"""Unit tests for :class:`~kilocode_tg_bot.config.Settings` validation and defaults."""

from __future__ import annotations

import pytest
from kilocode_tg_bot.config import Settings
from pydantic import ValidationError


class TestDefaults:
    def test_kilo_server_url_defaults_to_local(self) -> None:
        settings = Settings(
            telegram_bot_token="tok",
            telegram_allowed_user_id=42,
            _env_file=None,
        )
        assert settings.kilo_server_url == "http://127.0.0.1:4096"
        assert settings.telegram_edit_throttle_seconds == 1.0
        assert settings.message_file_threshold == 3900

    def test_optional_kilo_fields_default_to_none(self) -> None:
        settings = Settings(
            telegram_bot_token="tok", telegram_allowed_user_id=1, _env_file=None
        )
        assert settings.kilo_server_username is None
        assert settings.kilo_server_password is None
        assert settings.kilo_server_directory is None

    def test_require_token_returns_token(self) -> None:
        settings = Settings(
            telegram_bot_token="abc", telegram_allowed_user_id=1, _env_file=None
        )
        assert settings.require_token() == "abc"


class TestValidation:
    def test_missing_token_fails(self) -> None:
        with pytest.raises(ValidationError):
            Settings(telegram_allowed_user_id=42, _env_file=None)  # type: ignore[call-arg]

    def test_missing_allowed_user_fails(self) -> None:
        with pytest.raises(ValidationError):
            Settings(telegram_bot_token="tok", _env_file=None)  # type: ignore[call-arg]

    def test_extra_env_vars_are_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "7")
        monkeypatch.setenv("SOMETHING_UNRELATED", "x")
        settings = Settings(_env_file=None)
        assert settings.telegram_allowed_user_id == 7

    def test_env_overrides_default_server(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "7")
        monkeypatch.setenv("KILO_SERVER_URL", "http://kilo.example:7777")
        settings = Settings(_env_file=None)
        assert settings.kilo_server_url == "http://kilo.example:7777"


class TestTelegramProxy:
    def _settings(self, **kwargs):
        return Settings(
            telegram_bot_token="tok", telegram_allowed_user_id=1, _env_file=None, **kwargs
        )

    def test_proxy_defaults_to_none(self) -> None:
        assert self._settings().telegram_proxy() is None

    def test_proxy_url_without_credentials_is_used_as_is(self) -> None:
        s = self._settings(telegram_proxy_url="http://proxy.example.com:9999")
        assert s.telegram_proxy() == "http://proxy.example.com:9999"

    def test_proxy_credentials_are_embedded(self) -> None:
        s = self._settings(
            telegram_proxy_url="http://proxy.example.com:9999",
            telegram_proxy_username="proxyuser",
            telegram_proxy_password="secret",
        )
        assert s.telegram_proxy() == "http://proxyuser:secret@proxy.example.com:9999"

    def test_explicit_credentials_in_url_take_precedence(self) -> None:
        s = self._settings(
            telegram_proxy_url="http://user:pass@proxy.example.com:9999",
            telegram_proxy_username="other",
            telegram_proxy_password="otherpw",
        )
        assert s.telegram_proxy() == "http://user:pass@proxy.example.com:9999"

    def test_username_without_password_keeps_url(self) -> None:
        s = self._settings(
            telegram_proxy_url="http://proxy.example.com:9999",
            telegram_proxy_username="proxyuser",
        )
        assert s.telegram_proxy() == "http://proxy.example.com:9999"

    def test_proxy_env_vars_are_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "1")
        monkeypatch.setenv("TELEGRAM_PROXY_URL", "http://proxy.example.com:9999")
        monkeypatch.setenv("TELEGRAM_PROXY_USERNAME", "proxyuser")
        monkeypatch.setenv("TELEGRAM_PROXY_PASSWORD", "secret")
        settings = Settings(_env_file=None)
        assert settings.telegram_proxy() == "http://proxyuser:secret@proxy.example.com:9999"
