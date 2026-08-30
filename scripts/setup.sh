#!/usr/bin/env bash
# Первичная установка ReBook CRM на Ubuntu Server (22.04 / 24.04).
#   sudo ./scripts/setup.sh
# Ставит Postgres, Python, Node, заводит базы и роль, накатывает схему и демо-данные.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${DB_NAME:-rebook}"
DB_TEST="${DB_TEST:-rebook_test}"
DB_USER="${DB_USER:-rebook}"
DB_PASS="${DB_PASS:-rebook_dev}"

say() { printf '\n\033[36m→ %s\033[0m\n' "$1"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите через sudo: sudo ./scripts/setup.sh" >&2
  exit 1
fi
# от чьего имени создавать venv и ставить npm-пакеты
OWNER="${SUDO_USER:-root}"

say "Пакеты системы"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq postgresql python3 python3-venv python3-pip curl ca-certificates

if ! command -v node >/dev/null 2>&1; then
  say "Node.js 20 LTS"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y -qq nodejs
fi

say "PostgreSQL: роль и базы"
service postgresql start
run_psql() { su postgres -c "psql -tAc \"$1\""; }
run_psql "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
  run_psql "CREATE USER $DB_USER PASSWORD '$DB_PASS'"
for db in "$DB_NAME" "$DB_TEST"; do
  run_psql "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 || \
    run_psql "CREATE DATABASE $db OWNER $DB_USER ENCODING 'UTF8' TEMPLATE template0"
done

say "Бэкенд: venv и зависимости"
sudo -u "$OWNER" bash -c "
  set -e
  cd '$ROOT/apps/backend'
  [ -d .venv ] || python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
  [ -f .env ] || cp .env.example .env
"

say "Схема и демо-данные"
sudo -u "$OWNER" bash -c "
  set -e
  cd '$ROOT/apps/backend'
  ./.venv/bin/python -m alembic upgrade head
  ./.venv/bin/python -m app.seed
"

say "Фронт: зависимости"
sudo -u "$OWNER" bash -c "cd '$ROOT/apps/web' && (npm ci --no-fund --no-audit || npm install --no-fund --no-audit)"

cat <<'MSG'

Готово. Запуск для разработки:
  ./scripts/dev.sh

Прод-развёртывание (Docker + Caddy + HTTPS): см. deploy/README.md
MSG
