#!/usr/bin/env bash
# Запуск ReBook CRM для разработки на Ubuntu: бэкенд, фронт, бот с воркером.
#   ./scripts/dev.sh            — всё сразу (Ctrl+C останавливает всё)
#   ./scripts/dev.sh backend    — только API
#   ./scripts/dev.sh web        — только фронт
#   ./scripts/dev.sh bot        — только бот и воркер
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/apps/backend/.venv/bin/python"
WHAT="${1:-all}"

if [ ! -x "$PY" ]; then
  echo "Нет venv бэкенда. Сначала: sudo ./scripts/setup.sh" >&2
  exit 1
fi

# Postgres может быть не поднят после перезагрузки
if ! pg_isready -q 2>/dev/null; then
  echo "→ Запускаю PostgreSQL"
  sudo service postgresql start
fi

run_backend() { cd "$ROOT/apps/backend" && exec "$PY" -m uvicorn app.main:app --reload --port 8000; }
run_web()     { cd "$ROOT/apps/web" && exec npm run dev; }
# без --reload: два полинга на один токен → Telegram отвечает 409
run_bot()     { cd "$ROOT/apps/backend" && exec "$PY" -m app.run_bot; }

case "$WHAT" in
  backend) run_backend ;;
  web)     run_web ;;
  bot)     run_bot ;;
  all)
    pids=()
    trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT INT TERM
    ( run_backend ) & pids+=($!)
    ( run_web )     & pids+=($!)
    ( run_bot )     & pids+=($!)
    cat <<'MSG'

  Кабинет:  http://localhost:5173
  API:      http://localhost:8000/api/docs

  владелец    owner@demo.ru   / owner12345
  админ       staff@demo.ru   / staff12345
  superadmin  admin@rebook.ru / admin12345

  Ctrl+C — остановить всё.
MSG
    wait
    ;;
  *) echo "Использование: $0 [all|backend|web|bot]" >&2; exit 1 ;;
esac
