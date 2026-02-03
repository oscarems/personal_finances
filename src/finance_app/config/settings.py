from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


LOGGER = logging.getLogger("finance_app.config.settings")

load_dotenv(override=False)


class Settings(BaseSettings):
    telegram_bot_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "BOT_TOKEN"),
    )
    telegram_chat_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TELEGRAM_CHAT_ID",
            "TELEGRAM_ALLOWED_CHAT_ID",
            "CHAT_ID",
        ),
    )
    telegram_default_currency: str | None = Field(default=None, validation_alias="TELEGRAM_DEFAULT_CURRENCY")
    telegram_default_account: str | None = Field(default=None, validation_alias="TELEGRAM_DEFAULT_ACCOUNT")
    email_panama_account: str | None = Field(default=None, validation_alias="EMAIL_PANAMA_ACCOUNT")
    email_colombia_account: str | None = Field(default=None, validation_alias="EMAIL_COLOMBIA_ACCOUNT")
    email_mastercard_black_account: str | None = Field(
        default=None,
        validation_alias="EMAIL_MASTERCARD_BLACK_ACCOUNT",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@dataclass(frozen=True)
class TelegramConfig:
    token: str
    chat_id: str


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def get_telegram_config() -> TelegramConfig | None:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        LOGGER.error("Faltan variables TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID en .env")
        return None
    return TelegramConfig(token=settings.telegram_bot_token, chat_id=settings.telegram_chat_id)


def get_telegram_status() -> dict:
    settings = get_settings()
    configured = bool(settings.telegram_bot_token and settings.telegram_chat_id)
    message = ""
    if not configured:
        message = "Faltan variables TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID en .env"
        LOGGER.error(message)
    return {
        "configured": configured,
        "message": message,
        "masked_token": mask_secret(settings.telegram_bot_token) if configured else None,
        "masked_chat_id": mask_secret(settings.telegram_chat_id) if configured else None,
    }
