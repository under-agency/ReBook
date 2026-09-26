#!/usr/bin/env bash
# Подготовка чистого VPS (Ubuntu 22.04 / 24.04) под ReBook одной командой:
# пользователь deploy, SSH только по ключу и без root, ufw, fail2ban,
# автообновления безопасности, swap, Docker — и, если задан DOMAIN, сам стек.
#
#   scp deploy/provision.sh root@<сервер>:
#   ssh root@<сервер> 'DOMAIN=app.example.ru bash provision.sh'
#
# Переменные (все необязательные):
#   DOMAIN       домен кабинета; без него ставится только защищённый сервер
#   SSH_PORT     порт SSH, по умолчанию 22
#   SSH_PUBKEY   ещё один публичный ключ для deploy (кроме ключей root)
#   DEPLOY_USER  по умолчанию deploy
#   REPO_URL     откуда клонировать, по умолчанию https://github.com/under-agency/ReBook.git
#   REPO_REF     ветка, по умолчанию main
#   APP_DIR      куда, по умолчанию /opt/rebook (если уже есть — не клонируем)
#   SWAP_SIZE    по умолчанию 2G; создаётся, только если swap ещё нет
#   TELEGRAM_BOT_TOKEN, BOT_SALON_ID, LLM_API_KEY — попадут в новый deploy/.env
#
# Повторный запуск безопасен: уже сделанные шаги пропускаются, .env не перезаписывается.
# Порядок шагов такой, чтобы не потерять доступ: SSH закрывается только после того,
# как у deploy появился ключ, а порт в ufw открыт до включения файрвола.
set -euo pipefail

DOMAIN="${DOMAIN:-}"
SSH_PORT="${SSH_PORT:-22}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
REPO_URL="${REPO_URL:-https://github.com/under-agency/ReBook.git}"
REPO_REF="${REPO_REF:-main}"
APP_DIR="${APP_DIR:-/opt/rebook}"
SWAP_SIZE="${SWAP_SIZE:-2G}"

say()  { printf '\n\033[36m→ %s\033[0m\n' "$1"; }
warn() { printf '\033[33m! %s\033[0m\n' "$1" >&2; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Запустите от root: sudo bash provision.sh"
. /etc/os-release
[ "${ID:-}" = ubuntu ] || warn "Скрипт проверялся на Ubuntu 22.04/24.04, здесь ${PRETTY_NAME:-неизвестная ОС}"
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] || die "SSH_PORT должен быть числом"

export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-y -qq -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

# ---------------------------------------------------------------- 1. пакеты
say "1/9 Обновление системы"
apt-get update -qq
apt-get "${APT_OPTS[@]}" upgrade
apt-get "${APT_OPTS[@]}" install ca-certificates curl git openssl ufw \
  fail2ban python3-systemd unattended-upgrades

# ------------------------------------------------------- 2. пользователь deploy
say "2/9 Пользователь $DEPLOY_USER"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG sudo "$DEPLOY_USER"
echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$DEPLOY_USER"
chmod 440 "/etc/sudoers.d/$DEPLOY_USER"
visudo -cq

HOME_DIR="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
AUTH_KEYS="$HOME_DIR/.ssh/authorized_keys"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$HOME_DIR/.ssh"
touch "$AUTH_KEYS"
# ключи root, того, кто запустил через sudo, и SSH_PUBKEY — без дублей
for src in /root/.ssh/authorized_keys "$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)/.ssh/authorized_keys"; do
  if [ -f "$src" ] && [ "$src" != "$AUTH_KEYS" ]; then
    cat "$src" >> "$AUTH_KEYS"
  fi
done
if [ -n "${SSH_PUBKEY:-}" ]; then
  echo "$SSH_PUBKEY" >> "$AUTH_KEYS"
fi
# Опции перед ключом отрезаем: облачные образы ставят root'у
# command="echo Please login as ubuntu", с ней deploy тоже не пустит.
tmp="$(mktemp)"
sed -nE 's/^.*((ssh-(rsa|ed25519|dss)|ecdsa-sha2-[a-z0-9]+|sk-[a-z0-9@.-]+) [A-Za-z0-9+\/=]+.*)$/\1/p' "$AUTH_KEYS" \
  | awk '!seen[$0]++' > "$tmp"
install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$tmp" "$AUTH_KEYS"
rm -f "$tmp"

# главная защита от потери доступа: без ключа дальше не идём
[ -s "$AUTH_KEYS" ] || die "У $DEPLOY_USER нет ни одного SSH-ключа. Добавьте ключ root'у в панели хостера или передайте SSH_PUBKEY='ssh-ed25519 ...' и запустите снова. SSH не тронут."
echo "Ключей у $DEPLOY_USER: $(wc -l < "$AUTH_KEYS")"

# ------------------------------------------------------------- 3. файрвол
say "3/9 Файрвол ufw"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow "$SSH_PORT/tcp" >/dev/null
# пока SSH ещё слушает 22 — держим открытым и его, закроем после переключения
[ "$SSH_PORT" = 22 ] || ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
# Docker публикует порты в обход ufw, поэтому наружу их публикует только caddy
# (80/443), а Postgres живёт во внутренней сети compose — см. docker-compose.yml.

# ------------------------------------------------------------------ 4. SSH
say "4/9 SSH: только ключи, без root, порт $SSH_PORT"
SSHD_CONF=/etc/ssh/sshd_config.d/10-rebook-hardening.conf
# 10- важно: sshd берёт первое значение, а облачные образы кладут
# 50-cloud-init.conf с PasswordAuthentication yes
grep -qiE '^\s*Include\s+/etc/ssh/sshd_config\.d/\*\.conf' /etc/ssh/sshd_config \
  || die "sshd_config не подключает sshd_config.d — настройте SSH вручную"
cat > "$SSHD_CONF" <<EOF
Port $SSH_PORT
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
MaxAuthTries 3
AllowUsers $DEPLOY_USER
EOF
mkdir -p /run/sshd   # без него sshd -t падает, если ssh.service ещё не стартовал
if ! sshd -t; then
  rm -f "$SSHD_CONF"
  die "sshd -t нашёл ошибку в конфиге, изменения SSH откатаны"
fi

if systemctl is-active --quiet ssh.socket; then
  # Ubuntu 24.04: порт слушает ssh.socket, генератор берёт его из sshd_config
  systemctl daemon-reload
  systemctl restart ssh.socket
  systemctl reload-or-restart ssh.service 2>/dev/null || true
else
  systemctl reload-or-restart ssh
fi

if [ "$SSH_PORT" != 22 ]; then
  sleep 1
  if ss -ltnH "sport = :$SSH_PORT" | grep -q .; then
    ufw delete allow 22/tcp >/dev/null
  else
    warn "SSH не слушает порт $SSH_PORT — порт 22 оставлен открытым, проверьте вручную"
  fi
fi

# -------------------------------------------------------------- 5. fail2ban
say "5/9 fail2ban"
cat > /etc/fail2ban/jail.d/rebook-sshd.local <<EOF
[sshd]
enabled = true
port = $SSH_PORT
backend = systemd
maxretry = 5
bantime = 1h
EOF
systemctl enable --now fail2ban >/dev/null 2>&1
systemctl restart fail2ban

# ------------------------------------------------ 6. обновления безопасности
say "6/9 Автообновления безопасности"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now unattended-upgrades >/dev/null 2>&1

# ------------------------------------------------------------------ 7. swap
say "7/9 Swap"
if swapon --show --noheadings | grep -q .; then
  echo "swap уже есть, пропускаю"
else
  fallocate -l "$SWAP_SIZE" /swapfile 2>/dev/null \
    || dd if=/dev/zero of=/swapfile bs=1M count="$(numfmt --from=iec "$SWAP_SIZE" | awk '{print int($1/1048576)}')" status=none
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo 'vm.swappiness=10' > /etc/sysctl.d/90-rebook-swap.conf
  sysctl -q -p /etc/sysctl.d/90-rebook-swap.conf
fi

# ---------------------------------------------------------------- 8. Docker
say "8/9 Docker"
apt-get "${APT_OPTS[@]}" install docker.io docker-compose-v2
# без ротации json-логи контейнеров рано или поздно съедят диск
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
EOF
  systemctl restart docker
fi
systemctl enable --now docker >/dev/null 2>&1
# группа docker по правам равна root — только deploy
usermod -aG docker "$DEPLOY_USER"

# ---------------------------------------------------------------- 9. ReBook
if [ -z "$DOMAIN" ]; then
  say "9/9 ReBook пропущен: DOMAIN не задан"
else
  say "9/9 ReBook на $DOMAIN"
  if [ ! -d "$APP_DIR/.git" ] && [ ! -f "$APP_DIR/deploy/docker-compose.yml" ]; then
    install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
    sudo -u "$DEPLOY_USER" git clone --branch "$REPO_REF" "$REPO_URL" "$APP_DIR" \
      || die "Не удалось клонировать $REPO_URL. Если репозиторий закрыт — скопируйте его в $APP_DIR (rsync) и запустите снова."
  fi

  ENV_FILE="$APP_DIR/deploy/.env"
  if [ -f "$ENV_FILE" ]; then
    echo "$ENV_FILE уже есть, не трогаю"
  else
    umask 077
    cat > "$ENV_FILE" <<EOF
DOMAIN=$DOMAIN
DB_PASSWORD=$(openssl rand -hex 32)
SESSION_SECRET=$(openssl rand -hex 32)
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
BOT_SALON_ID=${BOT_SALON_ID:-}
LLM_API_KEY=${LLM_API_KEY:-}
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=google/gemini-2.5-flash
EOF
    umask 022
    chown "$DEPLOY_USER:$DEPLOY_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "Создан $ENV_FILE со случайными DB_PASSWORD и SESSION_SECRET"
  fi

  ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="src") print $(i+1)}')"
  resolved="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)"
  if [ -z "$resolved" ]; then
    warn "$DOMAIN пока не резолвится — Caddy получит сертификат, когда появится A-запись"
  elif [ -n "$ip" ] && [ "$resolved" != "$ip" ]; then
    warn "$DOMAIN указывает на $resolved, а у сервера $ip — проверьте A-запись"
  fi

  cd "$APP_DIR/deploy"
  docker compose up -d --build
fi

cat <<MSG

Готово. НЕ закрывайте текущее окно, пока не проверите вход в новом:
  ssh -p $SSH_PORT $DEPLOY_USER@<сервер>      # должно пустить
  ssh -p $SSH_PORT root@<сервер>              # не должно
Проверка всего сервера: sudo bash $APP_DIR/deploy/check.sh
MSG
if [ -n "$DOMAIN" ]; then
  cat <<MSG
Первый стенд: sudo docker compose -f $APP_DIR/deploy/docker-compose.yml exec backend python -m app.seed
(выведет пароли учёток один раз — сохраните)
MSG
fi
if [ -f /var/run/reboot-required ]; then
  warn "Обновилось ядро — перезагрузите сервер (sudo reboot), когда проверите вход под $DEPLOY_USER"
fi
