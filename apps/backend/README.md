# ReBook CRM — бэкенд

FastAPI + PostgreSQL + SQLAlchemy 2. Здесь живут API кабинета и админки,
Telegram-бот записи и воркер (каскад напоминаний, автозакрытие, биллинг-статусы).

## Установка

```bash
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Нужна PostgreSQL с базами `rebook` и `rebook_test` (владелец `rebook`).
Если Postgres стоит в WSL, поднимите его перед работой:

```bash
wsl -d Ubuntu -u root service postgresql start
```

Схема и демо-данные:

```bash
python -m alembic upgrade head
python -m app.seed --reset
```

Сиды создают учётки: `admin@rebook.ru / admin12345` (superadmin),
`owner@demo.ru / owner12345` (владелец), `staff@demo.ru / staff12345` (админ салона).

## Запуск

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Бот и воркер — отдельный процесс (без `--reload`, иначе два полинга на один токен):

```bash
python -m app.run_bot
```

Бот берёт салон из `BOT_SALON_ID` или первый салон с токеном. Токен задаётся
в `.env` (`TELEGRAM_BOT_TOKEN`, попадает в салон при сидировании) либо через
админку в карточке салона. **Не используйте токен legacy-бота `apps/telegram-bot`** —
Telegram отдаёт 409 на два полинга с одним токеном.

## Тесты

```bash
python -m pytest
```

Покрыты: изоляция тенантов (чужой объект → 404), расчёт свободных окон,
статусная модель и автозакрытие, каскад напоминаний с фейковым транспортом,
формула отчёта, auth и приглашения.

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
| `app/worker/reminders.py` | каскад T−24 / T−3 и автозакрытие |

## Заметки по окружению

- Windows: пакет `tzdata` обязателен (иначе `ZoneInfo("Europe/Moscow")` падает).
- Кириллица в консоли: `$env:PYTHONUTF8=1`.
- SMS-агрегатор не подключён: SMS-звено каскада пишется в `message_log`
  с `delivery_status='stub'` и реальной стоимостью — расчёты и лимиты работают.
