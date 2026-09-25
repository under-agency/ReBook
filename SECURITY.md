# Безопасность

Если вы нашли уязвимость, не создавайте публичный issue. Сообщите о ней
приватно через [GitHub Security Advisories](https://github.com/under-agency/ReBook/security/advisories/new).
Мы ответим и договоримся о сроках исправления до публикации деталей.

## Перед боевым запуском

- `SESSION_SECRET` и `DB_PASSWORD` — свои, случайные (`openssl rand -hex 32`).
- Известные демо-пароли (`admin12345` и т.п.) работают только в dev-режиме, пока
  `SESSION_SECRET` — заглушка из `.env.example`. На проде `python -m app.seed` генерирует случайные
  пароли и печатает их один раз.
- `.env` в репозиторий не коммитится (см. `.gitignore`).
