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

    db_pool_size: int = 10
    db_max_overflow: int = 20

    session_ttl_days: int = 30
    invite_ttl_hours: int = 72
    # Коэффициент неявок по умолчанию для расчёта «возвращено ≈ N ₽» (10-crm-logic.md)
    no_show_rate: float = 0.15
    sms_cost: float = 4.00

    # LLM-ассистент бота (docs/03-architecture.md). Любой OpenAI-совместимый
    # endpoint: по умолчанию OpenRouter; пустой ключ — ассистент выключен,
    # бот работает только кнопками.
    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "google/gemini-2.5-flash"
    llm_timeout_s: float = 12.0


settings = Settings()
