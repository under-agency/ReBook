# Модель данных и скелет репозитория

## Схема Postgres

Каждая «клиентская» таблица несёт `salon_id` — мультитенантность на уровне строк. Все FK — с `ON DELETE RESTRICT`, кроме явно помеченных.

```sql
-- Наши клиенты (салоны)
CREATE TABLE salons (
  id            serial PRIMARY KEY,
  name          text NOT NULL,
  status        text NOT NULL DEFAULT 'onboarding', -- onboarding|active|paused
  tg_bot_token  text,               -- секреты в проде выносим в секрет-хранилище
  max_bot_token text,
  channel_priority text[] NOT NULL DEFAULT '{tg,max,sms}',
  avg_check     numeric(10,2),      -- для расчёта «возвращено N ₽»
  work_hours    jsonb NOT NULL,     -- {"mon":["10:00","20:00"],...}
  remind_offsets_h int[] NOT NULL DEFAULT '{24,3}',
  sms_limit_month int NOT NULL DEFAULT 300,
  texts         jsonb NOT NULL,     -- шаблоны сообщений салона
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- Пользователи кабинета
CREATE TABLE users (
  id         serial PRIMARY KEY,
  salon_id   int REFERENCES salons(id),  -- NULL для superadmin
  email      text UNIQUE NOT NULL,
  pass_hash  text NOT NULL,              -- argon2
  role       text NOT NULL CHECK (role IN ('owner','superadmin')),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Услуги салона
CREATE TABLE services (
  id           serial PRIMARY KEY,
  salon_id     int NOT NULL REFERENCES salons(id),
  name         text NOT NULL,
  price        numeric(10,2) NOT NULL,
  duration_min int NOT NULL,
  repeat_cycle_days int,          -- NULL = без реактивации по этой услуге
  is_active    boolean NOT NULL DEFAULT true
);

-- Мастера
CREATE TABLE staff (
  id        serial PRIMARY KEY,
  salon_id  int NOT NULL REFERENCES salons(id),
  name      text NOT NULL,
  is_active boolean NOT NULL DEFAULT true
);

-- Клиенты салона
CREATE TABLE customers (
  id            serial PRIMARY KEY,
  salon_id      int NOT NULL REFERENCES salons(id),
  name          text,
  phone         text,               -- E.164
  tg_id         bigint,
  max_id        bigint,
  last_visit_at date,
  last_service_id int REFERENCES services(id),
  do_not_disturb boolean NOT NULL DEFAULT false,  -- кнопка «больше не присылать»
  last_outreach_at date,            -- антиспам-фильтр реактивации
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (salon_id, phone)
);

-- Записи
CREATE TABLE bookings (
  id          serial PRIMARY KEY,
  salon_id    int NOT NULL REFERENCES salons(id),
  customer_id int NOT NULL REFERENCES customers(id),
  service_id  int NOT NULL REFERENCES services(id),
  staff_id    int REFERENCES staff(id),
  starts_at   timestamptz NOT NULL,
  status      text NOT NULL DEFAULT 'new',
  -- new → reminded_24h → reminded_sms → reminded_2h →
  -- confirmed | rescheduled | cancelled | no_show | done
  source      text NOT NULL DEFAULT 'bot',  -- bot|manual|yclients
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON bookings (salon_id, starts_at, status);

-- Лист ожидания
CREATE TABLE waitlist (
  id          serial PRIMARY KEY,
  salon_id    int NOT NULL REFERENCES salons(id),
  customer_id int NOT NULL REFERENCES customers(id),
  service_id  int NOT NULL REFERENCES services(id),
  wanted_from timestamptz NOT NULL,
  wanted_to   timestamptz NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Лог сообщений (основа отчёта и биллинга SMS)
CREATE TABLE message_log (
  id          bigserial PRIMARY KEY,
  salon_id    int NOT NULL REFERENCES salons(id),
  customer_id int REFERENCES customers(id),
  booking_id  int REFERENCES bookings(id),
  channel     text NOT NULL CHECK (channel IN ('tg','max','sms')),
  kind        text NOT NULL,  -- reminder_24h|reminder_2h|sms_chase|reactivation|confirm|waitlist_offer|report|faq
  cost        numeric(8,2) NOT NULL DEFAULT 0,
  delivery_status text,       -- из колбэка SMS-агрегатора
  sent_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON message_log (salon_id, sent_at);

-- Состояние диалога (свободный ввод: имя, телефон)
CREATE TABLE dialog_state (
  salon_id   int NOT NULL REFERENCES salons(id),
  channel    text NOT NULL,
  ext_id     bigint NOT NULL,   -- tg_id или max_id
  step       text NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}',
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (salon_id, channel, ext_id)
);
```

Расчёт «возвращено ≈ N ₽» за месяц: `confirmed` после напоминания × ожидаемый % неявок без системы (консервативно 15%) × `avg_check` + визиты из перепроданных окон листа ожидания × `avg_check` + визиты с `kind='reactivation'` × `avg_check`. Формула и коэффициент показываются владельцу в отчёте открыто — честность продаёт продление.

## Скелет репозитория

```
antiprostoy/
├── docker-compose.yml        # postgres, backend, worker, web, caddy, uptime-kuma
├── Caddyfile                 # HTTPS, роутинг /webhook/* и app.домен.ru
├── .env.example              # DB_URL, токены, ключи SMS/OpenRouter
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI: API кабинета + приём вебхуков
│   │   ├── auth.py           # сессии, argon2, роли owner/superadmin
│   │   ├── deps.py           # проверка salon_id в КАЖДОМ запросе
│   │   ├── api/              # роуты: dashboard, bookings, customers, settings, admin
│   │   ├── bots/
│   │   │   ├── telegram.py   # aiogram: диалог записи, кнопки, FAQ
│   │   │   ├── max.py        # HTTP-клиент platform-api2.max.ru (тот же интерфейс)
│   │   │   └── dialogs.py    # общий конечный автомат записи (канал-агностичный)
│   │   ├── channels.py       # единый send(salon, customer, kind, text) с каскадом
│   │   ├── sms.py            # SMS-агрегатор: отправка + колбэк статусов
│   │   ├── llm.py            # OpenRouter: FAQ, промпт без ПДн, порог уверенности
│   │   ├── models.py         # SQLAlchemy-модели (схема выше)
│   │   └── reports.py        # расчёт «возвращено N ₽», генерация PDF
│   ├── worker/
│   │   ├── scheduler.py      # APScheduler: регистрация задач
│   │   ├── reminders.py      # каскад: выборки T-24/T-3, догоны, waitlist
│   │   ├── reactivation.py   # циклы услуг, SMS-волны порциями
│   │   ├── yclients_sync.py  # для салонов с YCLIENTS
│   │   └── monthly_report.py
│   └── tests/                # каскад и изоляция тенантов — приоритет тестов
├── web/                      # Next.js: кабинет владельца + админка (по ролям)
│   └── ...
└── ops/
    ├── backup.sh             # ночной pg_dump → S3 РФ
    └── restore_check.md      # регламент ежемесячной проверки восстановления
```

Ключевые архитектурные решения в коде:

- `dialogs.py` канал-агностичен: один автомат записи обслуживает и TG, и MAX — адаптеры каналов только переводят апдейты в общий формат.
- `channels.py` — единственная точка отправки: сама решает TG → MAX → SMS по приоритету салона, пишет в `message_log`, уважает `do_not_disturb` и лимит SMS. Никто больше не шлёт сообщения напрямую.
- `deps.py` — каждый API-запрос получает salon_id из сессии, а не из параметров запроса. Тест «пользователь салона А запросил запись салона Б → 403» входит в обязательный набор.
