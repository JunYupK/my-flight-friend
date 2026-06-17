#!/bin/bash
# 크롤링 + 진단 에이전트를 순서대로 실행하는 cron 래퍼.
#
# 호스트 crontab 예시:
#   0 */3 * * * cd /path/to/my-flight-friend && bash scripts/collect_and_diagnose.sh >> /var/log/collector.log 2>&1
#
# main.py 실패(exit != 0) 시에도 diagnosis_agent.py는 실행됨 (|| true).
# 크래시 자체가 진단 대상이므로 진단은 항상 수행한다.
set -uo pipefail

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
cd "$SCRIPT_DIR/.."

# 동시 실행 방지: 이전 수집이 아직 돌고 있으면 이번 tick은 스킵.
# 수집이 cron 주기(3h)보다 오래 걸려 run이 중첩 누적되는 악순환을 끊는다.
# flock은 프로세스 종료 시 자동 해제 → 크래시 후 다음 tick은 정상 재시작.
LOCKFILE=/tmp/my-flight-friend-collector.lock
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 이전 수집이 아직 실행 중 — 이번 tick 스킵."
    exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 수집 시작 ==="
docker compose --profile collect run --rm collector python main.py || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 진단 시작 ==="
docker compose --profile collect run --rm collector python diagnosis_agent.py

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 완료 ==="
