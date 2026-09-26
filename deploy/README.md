# Развёртывание ReBook на Ubuntu Server

Один VPS в РФ, Docker Compose, HTTPS через Caddy. Данные клиентов салона по
152-ФЗ хранятся в России — провайдер только российский.

## Сервер

Ubuntu 24.04 (или 22.04), 2 vCPU, от 40 ГБ NVMe, снапшоты у хостера. Памяти
хватает 2 ГБ: `provision.sh` добавляет 2 ГБ swap, иначе сборка фронта
(`npm run build`) упадёт от нехватки памяти. 4 ГБ — с запасом, если на том же
сервере будут мониторинг и другие служебные сервисы.

При создании сервера добавьте в панели хостера свой SSH-ключ. Пароль root не
понадобится, а `provision.sh` без ключа не станет трогать SSH.

## Первый запуск — одной командой

A-запись домена должна указывать на сервер (можно добавить и позже: Caddy
получит сертификат, когда домен начнёт резолвиться).

```bash
scp deploy/provision.sh root@<сервер>:
ssh root@<сервер> 'DOMAIN=app.example.ru bash provision.sh'
```

Скрипт по шагам:

1. обновляет систему;
2. заводит пользователя `deploy` с sudo и копирует ему SSH-ключи root;
3. включает ufw: наружу открыты только SSH, 80 и 443;
4. настраивает SSH: вход только по ключу, root не пускают, вход разрешён только `deploy`;
5. включает fail2ban для SSH;
6. включает автоматические обновления безопасности;
7. добавляет swap, если его нет;
8. ставит Docker с ротацией логов и добавляет `deploy` в группу `docker`;
9. клонирует репозиторий в `/opt/rebook`, создаёт `deploy/.env` со случайными
   `DB_PASSWORD` и `SESSION_SECRET` (права 600) и запускает `docker compose up -d --build`.

Сделанные шаги при повторном запуске пропускаются, а существующий `.env` скрипт не
перезаписывает. Без `DOMAIN` выполняются только шаги 1–8: получится защищённый
сервер без ReBook.

Необязательные переменные: `SSH_PORT` (нестандартный порт SSH), `SSH_PUBKEY`
(ещё один ключ для `deploy`), `TELEGRAM_BOT_TOKEN`, `BOT_SALON_ID`,
`LLM_API_KEY` (попадут в новый `.env`), `REPO_URL`/`REPO_REF`. Если
репозиторий закрыт, заранее скопируйте его в `/opt/rebook` (`rsync`): тогда
скрипт не станет его клонировать.

**Не закрывайте окно**, в котором шёл скрипт, пока в новом окне не проверите:
`ssh deploy@<сервер>` пускает, `ssh root@<сервер>` — нет. Дальше работаем только
под `deploy`.

Затем в `/opt/rebook/deploy/.env` (при необходимости):

- `TELEGRAM_BOT_TOKEN` — токен бота от @BotFather;
- `LLM_API_KEY` — ключ OpenRouter (или другого OpenAI-совместимого API) для
  ИИ-ассистента; пусто — бот работает только кнопками.

После правки: `sudo docker compose up -d` в `/opt/rebook/deploy`. На первом стенде:

```bash
sudo docker compose exec backend python -m app.seed
```

Сиды на проде создают учётки со случайными паролями и печатают их один раз —
сохраните вывод. Демо-пароли из README работают только локально.

Схема накатывается автоматически при старте `backend` (`alembic upgrade head`).

### Проверка перед сдачей клиенту

```bash
sudo bash /opt/rebook/deploy/check.sh
```

Скрипт проверяет SSH (вход по паролю и под root выключен), ufw, fail2ban, автообновления,
swap, что все четыре контейнера запущены, что Postgres не опубликован наружу, права на
`.env` и ответ `https://<домен>/api/health`. Код выхода — число проваленных
проверок.

### Вручную, без скрипта

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo git clone <репозиторий> /opt/rebook && cd /opt/rebook/deploy
cp .env.example .env    # DOMAIN, DB_PASSWORD и SESSION_SECRET (openssl rand -hex 32)
sudo docker compose up -d --build
```

Защиту сервера в этом случае настраивайте сами — по шагам в `provision.sh`.

## Что где

| Сервис | Роль |
|---|---|
| `db` | PostgreSQL 17, данные в томе `db_data` |
| `backend` | API кабинета и админки, отдаёт собранный фронт |
| `worker` | Telegram-бот и планировщик: напоминания, автозакрытие, биллинг-статусы |
| `caddy` | HTTPS, единственный контейнер с портами наружу |

Docker публикует порты в обход ufw, поэтому порты наружу публикует только `caddy`.
Postgres доступен только во внутренней сети compose — не добавляйте ему `ports:`.

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
