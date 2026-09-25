#!/usr/bin/env bash
# Установка/обновление ReBook на Ubuntu 24.04 без домена: сайт по http://<IP>/.
# Запуск от root:
#   curl -fsSL https://raw.githubusercontent.com/under-agency/ReBook/<ветка>/deploy/install-ip.sh | bash
# Повторный запуск безопасен: код обновится, секреты и база сохранятся.
set -euo pipefail

# Всё в функции: при `curl | bash` bash сначала дочитывает скрипт целиком,
# и команды, читающие stdin (docker compose exec), не съедят его остаток.
main() {

REPO=https://github.com/under-agency/ReBook.git
BRANCH=${BRANCH:-claude/clever-cannon-wfgwz5}
DIR=/opt/rebook
LOG=/root/rebook-install.log

exec > >(tee -a "$LOG") 2>&1
echo "=== ReBook install $(date -Is), ветка $BRANCH"
[ "$(id -u)" = 0 ] || { echo "Запустите от root"; exit 1; }

echo "--- пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git curl openssl
# Docker уже стоит (например, docker-ce из download.docker.com) — не трогаем:
# docker.io из Ubuntu конфликтует с containerd.io
if docker compose version >/dev/null 2>&1; then
  echo "Docker уже установлен: $(docker --version)"
else
  apt-get install -y -q docker.io docker-compose-v2
fi
systemctl enable --now docker

docker ps --format '{{.Names}}\t{{.Ports}}' || true

echo "--- код"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$BRANCH"
  git -C "$DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q -b "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR/deploy"

echo "--- .env"
[ -f .env ] || cp .env.example .env
cp .env ".env.bak.$(date +%s)"
chmod 600 .env .env.bak.*
getv() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
setv() {
  if grep -qE "^$1=" .env; then
    python3 - "$1" "$2" <<'PY'
import sys
k, v = sys.argv[1], sys.argv[2]
lines = open(".env").read().splitlines()
lines = [f"{k}={v}" if l.startswith(k + "=") else l for l in lines]
open(".env", "w").write("\n".join(lines) + "\n")
PY
  else
    echo "$1=$2" >> .env
  fi
}
# без домена: Caddy слушает только :80
setv DOMAIN ""
# секреты генерируем только если пусты — иначе потеряем доступ к существующей базе
[ -n "$(getv DB_PASSWORD)" ] || setv DB_PASSWORD "$(openssl rand -hex 32)"
case "$(getv SESSION_SECRET)" in ""|dev_secret|change_me_to_random_string)
  setv SESSION_SECRET "$(openssl rand -hex 32)";; esac

# токены спрашиваем с терминала (не попадают в лог и историю)
if [ -z "$(getv TELEGRAM_BOT_TOKEN)" ] && [ -r /dev/tty ]; then
  read -rsp "TELEGRAM_BOT_TOKEN (Enter — пропустить): " t </dev/tty; echo
  [ -z "$t" ] || setv TELEGRAM_BOT_TOKEN "$t"
fi
if [ -z "$(getv LLM_API_KEY)" ] && [ -r /dev/tty ]; then
  read -rsp "LLM_API_KEY / ключ OpenRouter (Enter — пропустить): " t </dev/tty; echo
  [ -z "$t" ] || setv LLM_API_KEY "$t"
fi
unset t

echo "--- порт"
# На сервере могут жить другие проекты со своими 80/443 — их не трогаем:
# ReBook слушает отдельный порт (по умолчанию первый свободный от 8081).
port_busy() { ss -ltnH "( sport = :$1 )" | grep -q .; }
PORT=$(getv HTTP_PORT)
if [ -z "$PORT" ]; then
  for p in $(seq 8081 8099); do port_busy "$p" || { PORT=$p; break; }; done
  [ -n "$PORT" ] || { echo "!!! нет свободного порта 8081-8099"; exit 1; }
  setv HTTP_PORT "$PORT"
fi
echo "HTTP_PORT=$PORT"
# только HTTP-порт наружу, 443 не публикуем (он занят чужим Caddy)
cat > docker-compose.override.yml <<YML
# создан install-ip.sh: режим без домена на отдельном порту
services:
  caddy:
    ports: !override
      - "\${HTTP_PORT}:80"
YML
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow "$PORT/tcp" >/dev/null && echo "ufw: открыт $PORT/tcp"
fi
echo "TELEGRAM_BOT_TOKEN: $([ -n "$(getv TELEGRAM_BOT_TOKEN)" ] && echo задан || echo ПУСТО)"
echo "LLM_API_KEY:        $([ -n "$(getv LLM_API_KEY)" ] && echo задан || echo ПУСТО)"

echo "--- сборка и запуск (несколько минут)"
docker compose up -d --build --remove-orphans

echo "--- ждём backend"
for i in $(seq 1 60); do
  if docker compose exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')" </dev/null 2>/dev/null; then
    echo "backend жив"; break
  fi
  [ "$i" = 60 ] && { echo "!!! backend не поднялся"; docker compose logs --tail 80 backend; exit 1; }
  sleep 5
done

echo "--- демо-данные (пароли выводятся только на экран, не в лог)"
# -w не годится: /dev/tty доступен на запись, но без управляющего терминала не открывается
OUT=/dev/tty; { : >/dev/tty; } 2>/dev/null || OUT=/dev/stdout
docker compose exec -T backend python -m app.seed </dev/null >"$OUT"
# если данные были от прошлой установки, в них могли остаться demo-пароли — меняем на случайные
(docker compose exec -T backend python - <<'PY'
import secrets
from sqlalchemy import select
from app.auth import hash_password
from app.db import SessionLocal
from app.models import User
db = SessionLocal()
print("\nДЕЙСТВУЮЩИЕ пароли (пароли выше уже не работают), сохраните их:")
for email in ("admin@rebook.ru", "owner@demo.ru", "staff@demo.ru"):
    u = db.scalar(select(User).where(User.email == email))
    if u:
        p = secrets.token_urlsafe(12)
        u.pass_hash = hash_password(p)
        print(f"  {email} / {p}")
db.commit()
PY
) >"$OUT"

echo "--- состояние"
docker compose ps
IP=$(curl -fsS -m 5 https://api.ipify.org || hostname -I | awk '{print $1}')
echo "Проверка: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/api/health) (ожидается 200)"
echo "=== Готово: http://$IP:$PORT/   Лог: $LOG"
}

main "$@"
