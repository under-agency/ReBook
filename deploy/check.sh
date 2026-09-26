#!/usr/bin/env bash
# Проверка сервера перед сдачей клиенту: защита SSH, файрвол, стек ReBook, HTTPS.
#   sudo bash /opt/rebook/deploy/check.sh
# Код выхода 0 — всё в порядке, иначе число проваленных проверок.
set -uo pipefail

APP_DIR="${APP_DIR:-/opt/rebook}"
COMPOSE=(docker compose -f "$APP_DIR/deploy/docker-compose.yml")
fails=0

ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fails=$((fails + 1)); }
check() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$name"; else bad "$name"; fi; }

[ "$(id -u)" -eq 0 ] || { echo "Запустите через sudo" >&2; exit 1; }

# shellcheck disable=SC2329  # вызываются через check
running()        { [ -n "$("${COMPOSE[@]}" ps -q --status running "$1")" ]; }
# shellcheck disable=SC2329
pg_port_closed() { [ -z "$(docker ps -q --filter publish=5432)" ]; }
sshd_opt() { sshd -T 2>/dev/null | awk -v k="$1" '$1==k{print $2; exit}'; }

echo "SSH"
check "вход по паролю выключен"      test "$(sshd_opt passwordauthentication)" = no
check "keyboard-interactive выключен" test "$(sshd_opt kbdinteractiveauthentication)" = no
check "root не пускают"              test "$(sshd_opt permitrootlogin)" = no
ssh_port="$(sshd_opt port)"

echo "Сервер"
check "ufw включён"                  sh -c 'ufw status | grep -q "Status: active"'
check "ufw пускает SSH на ${ssh_port:-?}" sh -c "ufw status | grep -qE '^${ssh_port:-22}/tcp +ALLOW'"
check "fail2ban сторожит sshd"       fail2ban-client status sshd
check "автообновления включены"      sh -c 'apt-config dump | grep -q "APT::Periodic::Unattended-Upgrade \"1\""'
check "swap есть"                    sh -c 'swapon --show --noheadings | grep -q .'
check "Postgres не слушает наружу"   sh -c '! ss -ltnH "sport = :5432" | grep -vqE "127\.0\.0\.1|\[::1\]"'

echo "ReBook"
if [ ! -f "$APP_DIR/deploy/docker-compose.yml" ]; then
  bad "нет $APP_DIR/deploy/docker-compose.yml"
else
  env_file="$APP_DIR/deploy/.env"
  check ".env доступен только владельцу" test "$(stat -c %a "$env_file" 2>/dev/null)" = 600
  for svc in db backend worker caddy; do
    check "контейнер $svc запущен" running "$svc"
  done
  check "порт 5432 не опубликован"     pg_port_closed
  domain="$(awk -F= '$1=="DOMAIN"{print $2}' "$env_file" 2>/dev/null)"
  if [ -n "$domain" ]; then
    check "https://$domain/api/health отвечает" \
      sh -c "curl -fsS --max-time 10 'https://$domain/api/health' | grep -q ok"
  else
    bad "DOMAIN не задан в $env_file"
  fi
fi

echo
if [ "$fails" -eq 0 ]; then echo "Всё в порядке."; else echo "Провалено проверок: $fails"; fi
exit "$fails"
