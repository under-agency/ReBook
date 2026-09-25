# ReBook CRM — бэкенд

FastAPI + PostgreSQL + SQLAlchemy 2. Здесь живут API кабинета и админки,
Telegram-бот записи и воркер (каскад напоминаний, автозакрытие, биллинг-статусы).

Целевая платформа — Ubuntu Server 22.04/24.04.

## Установка

Проще всего одной командой из корня репозитория — она поставит Postgres, Python,
Node, заведёт базы и накатит схему с демо-данными:

```bash
sudo ./scripts/setup.sh
```

Вручную, если окружение уже подготовлено:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m app.seed
```

Нужна PostgreSQL с базами `rebook` и `rebook_test` (владелец — роль `rebook`):

```bash
sudo -u postgres psql -c "CREATE USER rebook PASSWORD 'rebook_dev'"
sudo -u postgres psql -c "CREATE DATABASE rebook OWNER rebook ENCODING 'UTF8' TEMPLATE template0"
sudo -u postgres psql -c "CREATE DATABASE rebook_test OWNER rebook ENCODING 'UTF8' TEMPLATE template0"
```

Сиды создают учётки: `admin@rebook.ru / admin12345` (superadmin),
`owner@demo.ru / owner12345` (владелец), `staff@demo.ru / staff12345` (админ салона).
Пересоздать демо-данные: `./.venv/bin/python -m app.seed --reset`.

## Запуск

```bash
./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Бот и воркер — отдельный процесс (без `--reload`, иначе два полинга на один токен):

```bash
./.venv/bin/python -m app.run_bot
```

Всё сразу вместе с фронтом: `./scripts/dev.sh` из корня репозитория.

Бот берёт салон из `BOT_SALON_ID` или первый салон с токеном. Токен задаётся
в `.env` (`TELEGRAM_BOT_TOKEN`, попадает в салон при сидировании) либо через
админку в карточке салона. **Не используйте токен legacy-бота `apps/telegram-bot`** —
Telegram отдаёт 409 на два полинга с одним токеном.

## ИИ-ассистент

Клиент может писать боту обычным текстом: «к Лене в четверг после 6 на маникюр».
Включается ключом в `.env` (`LLM_API_KEY`, при необходимости `LLM_BASE_URL` и
`LLM_MODEL` — подходит любой OpenAI-совместимый API) и флагом салона
`llm_assistant` в админке (у демо-салона включён). Без ключа бот работает только
кнопками. Адрес, оплату и правила ассистент берёт из текста «О салоне»
в настройках → «Тексты».

## Тесты

```bash
./.venv/bin/python -m pytest
```

Покрыты: изоляция тенантов (чужой объект → 404), расчёт свободных окон,
статусная модель и автозакрытие, каскад напоминаний с фейковым транспортом,
формула отчёта, совпадение SQL- и Python-веток статуса клиента, гонка при
одновременной записи на один слот, auth и приглашения, ИИ-ассистент
(с подменённой LLM).

Разбор 20 реальных фраз на настоящей модели — отдельно, нужен ключ:
`LLM_API_KEY=... ./.venv/bin/python -m pytest tests/test_assistant_live.py -v`.

## Структура

| Файл | Что внутри |
|---|---|
| `app/models.py` | вся схема БД (docs/08-data-model.md + дельта) |
| `app/deps.py` | `salon_id` из сессии, роли, `get_owned_or_404` |
| `app/channels.py` | единственная точка отправки: каскад каналов, `message_log`, гейты |
| `app/services/slots.py` | свободные окна — чистые функции |
| `app/services/bookings.py` | создание записей, конфликты, статусы, перенос |
| `app/reports.py` | «возвращено ≈ N ₽» |
| `app/bots/dialogs.py` | канал-агностичный автомат записи |
| `app/bots/assistant.py` | ИИ-ассистент: свободный текст → запись/перенос/отмена/ответ |
| `app/worker/reminders.py` | каскад T−24 / T−3 и автозакрытие |

## Заметки по окружению

- Схема меняется только через Alembic: правим `app/models.py`, затем
  `alembic revision --autogenerate -m "что изменили"` и `alembic upgrade head`.
- SMS-агрегатор не подключён: SMS-звено каскада пишется в `message_log`
  с `delivery_status='stub'` и реальной стоимостью — расчёты и лимиты работают.
- Прод-развёртывание (Docker + Caddy + HTTPS) — `deploy/README.md`.
