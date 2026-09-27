"""Application settings loaded from environment variables / ``.env``.

Everything the bot needs to know up front lives here: the Telegram token, the
single allowed owner user id, and the ``kilocode_client.Kilo`` connection
options. Settings are validated at construction time so a misconfigured bot
fails fast on startup instead of mid-conversation.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the bot.

    ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_ALLOWED_USER_ID`` are mandatory; the
    bot refuses to start without them. The Kilo server options default to a
    local unauthenticated ``kilo serve``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(..., description="Telegram bot token from @BotFather")
    telegram_allowed_user_id: int = Field(
        ..., description="Telegram user id of the single allowed owner"
    )

    kilo_server_url: str = Field(default="http://127.0.0.1:4096")
    kilo_server_username: str | None = None
    kilo_server_password: str | None = None
    kilo_server_directory: str | None = None

    telegram_edit_throttle_seconds: float = Field(
        default=1.0, description="Minimum interval between streaming edits (rate-limit guard)"
    )
    message_file_threshold: int = Field(
        default=3900, description="Send long text as a .txt file above this character count"
    )
    session_store_path: str = Field(
        default="kilocode_bot_state.db",
        description="SQLite database path for the active-session store",
    )

    def require_token(self) -> str:
        """Return the required bot token (fails loudly if unset)."""
        return self.telegram_bot_token


def load_settings() -> Settings:
    """Construct and validate settings from the environment / ``.env``."""
    return Settings()
