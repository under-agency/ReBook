<div align="center">
  <img src="assets/logo.png" width="140" height="140" alt="ReBook Logo" />
  <h1>ReBook</h1>
  <p><b>Система автоматизации для сервисного бизнеса: онлайн-запись, каскадные напоминания и реактивация клиентской базы.</b></p>
</div>

---

## О проекте

Сервисные бизнесы (салоны красоты, автосервисы, клиники) теряют выручку на трех основных утечках:
1. **Неявки клиентов (no-show)** — забронированное время сгорает впустую.
2. **Пропущенные и ночные заявки** — клиент уходит к конкурентам, если ему не ответили оперативно.
3. **«Спящая» база** — клиенты забывают записаться на повторную услугу вовремя.

**ReBook** устраняет эти утечки с помощью автоматизации и ежемесячно демонстрирует владельцу объем возвращенной выручки в рублях.

---

## Структура репозитория

```text
rebook/
├── apps/                    # Приложения и сервисы
│   ├── backend/             # CRM: FastAPI + PostgreSQL, бот записи, воркер
│   │   ├── app/             # API, модели, каналы, бот, воркер
│   │   ├── migrations/      # Alembic
│   │   ├── tests/           # pytest: изоляция тенантов, каскад, отчёты
│   │   └── README.md        # Установка и запуск бэкенда
│   ├── web/                 # Кабинет владельца и админка (React + Vite)
│   └── telegram-bot/        # Legacy демо-стенд (записи в CSV)
│       ├── tests/           # Модульные тесты бота
│       │   └── test_bot.py
│       ├── bot.py           # Исходный код бота
│       └── requirements.txt # Зависимости бота
├── assets/                  # Логотипы и графика (SVG, PNG)
├── docs/                    # Документация проекта
│   ├── templates/           # CSV-шаблон журнала записей
│   │   └── demo-bookings-template.csv
│   ├── 01-problem.md        # Анализ проблемы и экономика потерь
│   ├── 02-product.md        # Модули продукта и сценарии работы
│   ├── 03-architecture.md   # Техническая архитектура и безопасность
│   ├── 04-business-model.md # Юнит-экономика и ценообразование
│   ├── 05-go-to-market.md   # Стратегия продаж, скрипты и оффер
│   ├── 06-roadmap.md        # Дорожная карта проекта
│   ├── 07-risks.md          # Карта рисков и способы защиты
│   └── demo-setup-guide.md  # Инструкция по запуску демо-стенда
├── deploy/                  # Прод: Dockerfile, docker-compose, Caddy (HTTPS)
├── ops/                     # Эксплуатация: бэкапы и проверка восстановления
├── scripts/                 # setup.sh (установка) и dev.sh (запуск)
├── .env.example             # Пример конфигурации переменных окружения
├── .gitignore               # Исключения Git
└── README.md
```

Целевая платформа — **Ubuntu Server 22.04/24.04**.

---

## Быстрый запуск CRM

Установка на чистом Ubuntu Server (Postgres, Python, Node, базы, схема, демо-данные):

```bash
sudo ./scripts/setup.sh
```

Запуск для разработки — бэкенд `:8000`, кабинет `:5173`, бот с воркером:

```bash
./scripts/dev.sh
```

Демо-учётки: владелец `owner@demo.ru / owner12345`, администратор салона
`staff@demo.ru / staff12345`, superadmin `admin@rebook.ru / admin12345`.

Подробности по бэкенду — [apps/backend/README.md](apps/backend/README.md),
боевое развёртывание за HTTPS — [deploy/README.md](deploy/README.md).

---

## Демо-бот (legacy)

`apps/telegram-bot` — простой продающий демо-стенд: пишет записи в CSV,
своей базы не имеет. Рабочий бот записи живёт внутри CRM (`apps/backend/app/bots`).

```bash
pip install -r apps/telegram-bot/requirements.txt
echo "TELEGRAM_BOT_TOKEN=токен_от_BotFather" > .env
python3 apps/telegram-bot/bot.py
```

---

## Ключевые параметры

- **Рынок:** РФ, малый и средний сервисный бизнес с предварительной записью.
- **Модель:** Разовое внедрение (40–70 тыс. ₽) + абонентское обслуживание (8–15 тыс. ₽/мес).
- **Цель:** 100 000 ₽/мес recurring доход в течение 3–5 месяцев.
- **Стек:** Python 3 (FastAPI, pyTelegramBotAPI), React + Vite, PostgreSQL; развёртывание — Docker Compose за Caddy на Ubuntu Server.