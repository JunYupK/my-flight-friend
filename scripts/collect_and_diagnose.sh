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

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 수집 시작 ==="
docker compose --profile collect run --rm collector python main.py || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 진단 시작 ==="
docker compose --profile collect run --rm collector python diagnosis_agent.py

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 완료 ==="
