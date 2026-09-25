# Развёртывание ReBook на Ubuntu Server

Один VPS в РФ (2 vCPU / 2 ГБ достаточно), Docker Compose, HTTPS через Caddy.

Без домена, по IP — одной командой от root (ставит Docker, генерирует секреты,
спрашивает токены, поднимает стек, меняет демо-пароли на случайные):

```bash
curl -fsSL https://raw.githubusercontent.com/under-agency/ReBook/claude/clever-cannon-wfgwz5/deploy/install-ip.sh | bash
```

## Первый запуск

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo git clone <репозиторий> /opt/rebook && cd /opt/rebook/deploy
cp .env.example .env
```

В `.env` заполнить:

- `DOMAIN` — домен кабинета, A-запись уже должна указывать на этот сервер.
  Пока домена нет, оставьте пустым: Caddy отдаёт сайт по `http://<IP>/` на :80
  без TLS. Пароли и куки тогда идут открытым текстом — это временный режим;
- `DB_PASSWORD` и `SESSION_SECRET` — `openssl rand -hex 32` на каждый;
- `TELEGRAM_BOT_TOKEN` — токен бота от @BotFather;
- `LLM_API_KEY` — ключ OpenRouter (или другого OpenAI-совместимого API) для
  ИИ-ассистента; пусто — бот работает только кнопками.

Затем:

```bash
sudo docker compose up -d --build
sudo docker compose exec backend python -m app.seed   # только на первом стенде
```

Сиды на проде создают учётки со случайными паролями и печатают их один раз —
сохраните вывод. Демо-пароли из README работают только локально.

Схема накатывается автоматически при старте `backend` (`alembic upgrade head`).
Caddy сам получит сертификат Let's Encrypt, как только домен резолвится на сервер.

## Что где

| Сервис | Роль |
|---|---|
| `db` | PostgreSQL 17, данные в томе `db_data` |
| `backend` | API кабинета и админки, отдаёт собранный фронт |
| `worker` | Telegram-бот и планировщик: напоминания, автозакрытие, биллинг-статусы |
| `caddy` | HTTPS, единственный контейнер с портами наружу |

Бот вынесен в отдельный контейнер намеренно: на один токен допустим только один
полинг, а API при этом можно перезапускать сколько угодно.

## Обновление

```bash
cd /opt/rebook && sudo git pull
sudo docker compose -f deploy/docker-compose.yml up -d --build
```

## Эксплуатация

```bash
sudo docker compose logs -f backend worker     # логи
sudo docker compose exec db psql -U rebook     # консоль базы
sudo docker compose ps                         # состояние и healthcheck
```

Бэкапы: `ops/backup.sh` в cron (`0 3 * * *`), переменные хранилища — в
`/etc/rebook-backup.env`. Проверка восстановления — `ops/restore_check.md`.

## Что ещё нужно для боевой эксплуатации

- Вебхуки ботов вместо полинга (`POST /webhook/tg/<salon_id>`) — сейчас воркер
  работает полингом, это упрощает запуск, но хуже масштабируется.
- SMTP для писем-приглашений владельцам.
- Мониторинг (Uptime Kuma) на `/api/health` и алерты в мессенджер.
