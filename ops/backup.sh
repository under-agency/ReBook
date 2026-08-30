#!/usr/bin/env bash
# Ночной дамп базы ReBook в объектное хранилище (S3 в РФ).
# Ставится в cron: 0 3 * * * /opt/rebook/ops/backup.sh >> /var/log/rebook-backup.log 2>&1
#
# Нужны переменные (положите в /etc/rebook-backup.env):
#   S3_BUCKET, S3_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
#   DB_NAME, DB_USER (по умолчанию rebook), KEEP_DAYS (по умолчанию 30)
set -euo pipefail

[ -f /etc/rebook-backup.env ] && . /etc/rebook-backup.env

DB_NAME="${DB_NAME:-rebook}"
DB_USER="${DB_USER:-rebook}"
KEEP_DAYS="${KEEP_DAYS:-30}"
DIR="${BACKUP_DIR:-/var/backups/rebook}"
STAMP="$(date +%Y-%m-%d_%H%M)"
FILE="$DIR/rebook_$STAMP.sql.gz"

mkdir -p "$DIR"

# Дамп: из контейнера, если стек в Docker, иначе локальным pg_dump
if docker compose -f /opt/rebook/deploy/docker-compose.yml ps db >/dev/null 2>&1; then
  docker compose -f /opt/rebook/deploy/docker-compose.yml exec -T db \
    pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILE"
else
  pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILE"
fi

SIZE=$(du -h "$FILE" | cut -f1)
echo "$(date '+%F %T') дамп готов: $FILE ($SIZE)"

if [ -n "${S3_BUCKET:-}" ]; then
  aws s3 cp "$FILE" "s3://$S3_BUCKET/$(basename "$FILE")" \
    ${S3_ENDPOINT:+--endpoint-url "$S3_ENDPOINT"}
  echo "$(date '+%F %T') выгружено в s3://$S3_BUCKET"
fi

# Локальная ротация; в хранилище настройте lifecycle-правило
find "$DIR" -name 'rebook_*.sql.gz' -mtime "+$KEEP_DAYS" -delete
echo "$(date '+%F %T') старше $KEEP_DAYS дней удалено"
