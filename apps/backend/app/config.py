from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # apps/backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://rebook:rebook_dev@localhost:5432/rebook"
    database_url_test: str = "postgresql+psycopg://rebook:rebook_dev@localhost:5432/rebook_test"
    session_secret: str = "dev_secret"
    telegram_bot_token: str = ""
    bot_salon_id: int | None = None

    @field_validator("bot_salon_id", mode="before")
    @classmethod
    def _empty_as_none(cls, v):
        return None if v == "" else v

    session_ttl_days: int = 30
    invite_ttl_hours: int = 72
    # Коэффициент неявок по умолчанию для расчёта «возвращено ≈ N ₽» (10-crm-logic.md)
    no_show_rate: float = 0.15
    sms_cost: float = 4.00


settings = Settings()
