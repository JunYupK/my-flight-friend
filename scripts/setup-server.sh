#!/usr/bin/env bash
# OCI Ampere (Ubuntu 22.04/24.04 ARM64) 초기 셋업 스크립트
# 사용법: ssh ubuntu@<IP> 'bash -s' < scripts/setup-server.sh
set -euo pipefail

echo "=== 1. 시스템 업데이트 ==="
sudo apt-get update && sudo apt-get upgrade -y

echo "=== 2. Docker 설치 ==="
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "Docker 설치 완료. 재로그인 후 docker 명령 사용 가능."
else
  echo "Docker 이미 설치됨: $(docker --version)"
fi

echo "=== 3. 방화벽 설정 (iptables) ==="
# OCI는 기본적으로 iptables 사용. Security List도 별도 설정 필요.
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo iptables-save | sudo tee /etc/iptables/rules.v4 >/dev/null

echo "=== 4. 프로젝트 클론 ==="
PROJECT_DIR="$HOME/my-flight-friend"
if [ ! -d "$PROJECT_DIR" ]; then
  git clone https://github.com/JunYupK/my-flight-friend.git "$PROJECT_DIR"
else
  echo "프로젝트 디렉토리 이미 존재: $PROJECT_DIR"
fi

echo "=== 5. .env 파일 확인 ==="
if [ ! -f "$PROJECT_DIR/.env" ]; then
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  echo ">>> .env 파일이 생성되었습니다. 반드시 실제 값으로 수정하세요:"
  echo "    vi $PROJECT_DIR/.env"
fi

echo "=== 6. 수집 cron 등록 ==="
CRON_CMD="cd $PROJECT_DIR && docker compose -f docker-compose.prod.yml run --rm collector python -u main.py >> /var/log/flight-collector.log 2>&1"
CRON_LINE="0 0 * * * $CRON_CMD"
(crontab -l 2>/dev/null | grep -v 'flight-collector' ; echo "$CRON_LINE") | crontab -
echo "수집 cron 등록 완료 (매일 09:00 KST = 00:00 UTC)"

echo "=== 7. DB 백업 cron 등록 ==="
BACKUP_CMD="cd $PROJECT_DIR && bash scripts/backup-db.sh >> /var/log/flight-backup.log 2>&1"
BACKUP_LINE="0 18 * * * $BACKUP_CMD"
(crontab -l 2>/dev/null | grep -v 'flight-backup' ; echo "$BACKUP_LINE") | crontab -
echo "DB 백업 cron 등록 완료 (매일 03:00 KST = 18:00 UTC)"

echo ""
echo "=== 셋업 완료 ==="
echo "다음 단계:"
echo "  1. .env 파일 수정: vi $PROJECT_DIR/.env"
echo "  2. OCI Security List에서 80, 443 포트 Ingress 허용"
echo "  3. 도메인 DNS A 레코드를 이 서버 IP로 설정"
echo "  4. 서비스 시작: cd $PROJECT_DIR && docker compose -f docker-compose.prod.yml up -d"
