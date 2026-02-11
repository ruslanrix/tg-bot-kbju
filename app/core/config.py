"""Application configuration via Pydantic Settings.

Reads environment variables (and optional .env file) and validates them
at startup. Use ``get_settings()`` to obtain a cached singleton.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # --- Required --------------------------------------------------------
    BOT_TOKEN: str
    DATABASE_URL: str
    OPENAI_API_KEY: str

    # --- Webhook mode (optional — leave empty for polling/local dev) ----
    PUBLIC_URL: str = ""
    WEBHOOK_SECRET: str = ""

    # --- Optional (with defaults) ----------------------------------------
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT_SECONDS: int = 30
    LOG_LEVEL: str = "INFO"
    MAX_PHOTO_BYTES: int = 5 * 1024 * 1024  # 5 MB
    RATE_LIMIT_PER_MINUTE: int = 6
    MAX_CONCURRENT_PER_USER: int = 1
    PORT: int = 8000

    # --- Validators ------------------------------------------------------
    @property
    def use_webhook(self) -> bool:
        """True when PUBLIC_URL is configured (webhook mode)."""
        return bool(self.PUBLIC_URL)

    @field_validator("PUBLIC_URL")
    @classmethod
    def _validate_public_url(cls, v: str) -> str:
        if not v:  # empty = polling mode
            return v
        if not v.startswith("https://"):
            raise ValueError("PUBLIC_URL must start with https://")
        if v.endswith("/"):
            raise ValueError("PUBLIC_URL must not end with /")
        return v

    @field_validator("WEBHOOK_SECRET")
    @classmethod
    def _validate_webhook_secret(cls, v: str) -> str:
        if not v:  # empty = polling mode, no secret needed
            return v
        if len(v) < 8:
            raise ValueError("WEBHOOK_SECRET must be at least 8 characters")
        return v

    @model_validator(mode="after")
    def _validate_webhook_pair(self) -> Settings:
        """Require WEBHOOK_SECRET when PUBLIC_URL is set (webhook mode)."""
        if self.PUBLIC_URL and not self.WEBHOOK_SECRET:
            raise ValueError("WEBHOOK_SECRET is required when PUBLIC_URL is set")
        return self

    @field_validator("OPENAI_TIMEOUT_SECONDS", "MAX_PHOTO_BYTES", "RATE_LIMIT_PER_MINUTE", "PORT")
    @classmethod
    def _validate_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Value must be positive")
        return v

    @field_validator("MAX_CONCURRENT_PER_USER")
    @classmethod
    def _validate_concurrency(cls, v: int) -> int:
        if v < 1:
            raise ValueError("MAX_CONCURRENT_PER_USER must be at least 1")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()  # type: ignore[call-arg]
