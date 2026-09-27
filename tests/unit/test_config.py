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
        )
        assert settings.kilo_server_url == "http://127.0.0.1:4096"
        assert settings.telegram_edit_throttle_seconds == 1.0
        assert settings.message_file_threshold == 3900

    def test_optional_kilo_fields_default_to_none(self) -> None:
        settings = Settings(telegram_bot_token="tok", telegram_allowed_user_id=1)
        assert settings.kilo_server_username is None
        assert settings.kilo_server_password is None
        assert settings.kilo_server_directory is None

    def test_require_token_returns_token(self) -> None:
        settings = Settings(telegram_bot_token="abc", telegram_allowed_user_id=1)
        assert settings.require_token() == "abc"


class TestValidation:
    def test_missing_token_fails(self) -> None:
        with pytest.raises(ValidationError):
            Settings(telegram_allowed_user_id=42)  # type: ignore[call-arg]

    def test_missing_allowed_user_fails(self) -> None:
        with pytest.raises(ValidationError):
            Settings(telegram_bot_token="tok")  # type: ignore[call-arg]

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
