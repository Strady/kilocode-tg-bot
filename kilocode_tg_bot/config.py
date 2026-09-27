"""Application settings loaded from environment variables / ``.env``.

Everything the bot needs to know up front lives here: the Telegram token, the
single allowed owner user id, and the ``kilocode_client.Kilo`` connection
options. Settings are validated at construction time so a misconfigured bot
fails fast on startup instead of mid-conversation.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the bot.

    ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_ALLOWED_USER_ID`` are mandatory; the
    bot refuses to start without them. Telegram API traffic can be routed through
    an HTTP/SOCKS proxy via ``TELEGRAM_PROXY_URL`` (plus optional
    ``TELEGRAM_PROXY_USERNAME`` / ``TELEGRAM_PROXY_PASSWORD``). The Kilo server
    options default to a local unauthenticated ``kilo serve``.
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

    telegram_proxy_url: str | None = Field(
        default=None,
        description="HTTP/SOCKS proxy URL for Telegram API traffic (e.g. http://host:9999). "
        "Credentials may be embedded in the URL or given separately.",
    )
    telegram_proxy_username: str | None = None
    telegram_proxy_password: str | None = None

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

    def telegram_proxy(self) -> str | None:
        """Return the proxy URL with credentials embedded, or ``None``.

        If ``telegram_proxy_username``/``telegram_proxy_password`` are set, they
        are merged into ``telegram_proxy_url`` (explicit userinfo in the URL, if
        any, takes precedence). Returns ``None`` when no proxy is configured.
        """
        if not self.telegram_proxy_url:
            return None
        userinfo = ""
        if self.telegram_proxy_username and self.telegram_proxy_password:
            userinfo = (
                f"{self.telegram_proxy_username}:{self.telegram_proxy_password}@"
            )
        if not userinfo:
            return self.telegram_proxy_url
        parts = urlsplit(self.telegram_proxy_url)
        if parts.username:
            return self.telegram_proxy_url
        parts = parts._replace(netloc=f"{userinfo}{parts.netloc}")
        return urlunsplit(parts)


def load_settings() -> Settings:
    """Construct and validate settings from the environment / ``.env``."""
    return Settings()
