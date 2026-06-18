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

# 좀비 청소: timeout/크래시로 --rm 정리가 안 된 one-off collector 컨테이너 제거.
# flock으로 직렬화되어 있으므로(여기 도달 = lock 보유) 살아있는 정상 수집은 없다 →
# 남아 있는 컨테이너는 전부 좀비. (이전 직렬화 미적용 시절 쌓인 잔재 포함)
docker ps -aq \
    --filter "label=com.docker.compose.service=collector" \
    --filter "label=com.docker.compose.oneoff=True" \
  | xargs -r docker rm -f >/dev/null 2>&1 || true

# 단일 run hard timeout: 크롤이 wedge 되어도 cron 주기를 넘기기 전에 강제 종료.
# flock은 중첩을 막지만, hang 한 run은 lock을 영원히 쥐어 수집을 영구 정지시킬 수 있다.
# SIGTERM 후 2분 내 미종료 시 SIGKILL. --rm + compose 시그널 전파로 컨테이너도 정리됨.
COLLECT_TIMEOUT="${COLLECT_TIMEOUT:-150m}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 수집 시작 (timeout ${COLLECT_TIMEOUT}) ==="
timeout --signal=SIGTERM --kill-after=2m "$COLLECT_TIMEOUT" \
    docker compose --profile collect run --rm collector python main.py || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 진단 시작 ==="
docker compose --profile collect run --rm collector python diagnosis_agent.py

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 완료 ==="
