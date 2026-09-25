"""Тонкий клиент LLM: OpenAI-совместимый /chat/completions (OpenRouter по умолчанию).

Единственная точка выхода в LLM. Что уходит в промпт, решает вызывающий код
(app/bots/assistant.py) — там же вычищаются ПДн. Здесь только транспорт.
"""
import json
import logging
from typing import Callable

import httpx

from app.config import settings

log = logging.getLogger("rebook.llm")

# (messages) -> ответ модели строкой; в тестах подменяется фейком
Completer = Callable[[list[dict]], str]


class LLMError(Exception):
    pass


def enabled() -> bool:
    return bool(settings.llm_api_key)


def complete(messages: list[dict]) -> str:
    try:
        r = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=settings.llm_timeout_s,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        log.warning("LLM недоступна: %s", e)
        raise LLMError(str(e)) from e


def parse_json(raw: str) -> dict:
    """Достаёт JSON-объект из ответа модели (иногда он обёрнут в ```json)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise LLMError(f"в ответе нет JSON: {raw[:200]!r}")
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"битый JSON: {raw[:200]!r}") from e
    if not isinstance(data, dict):
        raise LLMError("ожидался JSON-объект")
    return data
