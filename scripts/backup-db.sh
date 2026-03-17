#!/usr/bin/env bash
# PostgreSQL 백업 — cron에서 호출
# 최근 7일 백업만 보존
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/backups"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="$BACKUP_DIR/flights_${TIMESTAMP}.sql.gz"

docker compose -f "$PROJECT_DIR/docker-compose.prod.yml" exec -T db \
  pg_dump -U flight_user -d flights | gzip > "$DUMP_FILE"

echo "[$(date)] 백업 완료: $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"

# 7일 이상 된 백업 삭제
find "$BACKUP_DIR" -name "flights_*.sql.gz" -mtime +7 -delete
