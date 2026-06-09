#!/usr/bin/env python3
"""
크롤링 완료 후 데이터 품질 자동 진단 에이전트.

Anthropic API의 native MCP client 지원으로 mcp_server 툴을 직접 호출해
DB 조회·소스코드 참조·텔레그램 발송까지 수행한다.
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg2
from dotenv import load_dotenv

load_dotenv()

_KST = timezone(timedelta(hours=9))

_SYSTEM_PROMPT = """\
당신은 ICN↔일본 항공권 모니터링 시스템의 자동 진단 에이전트입니다.
크롤링 완료 후 데이터 품질을 점검하고 텔레그램으로 리포트를 보냅니다.

[시스템 구조]
- 수집 소스: GoogleFlights (crawl4ai headless), Naver (crawl4ai GraphQL)
- 실행: 3시간마다 cron → docker compose --profile collect run --rm collector python main.py
- DB 흐름: raw_legs(수집 원본, append-only) → flight_legs(현재 상태, UPSERT) → price_events(가격 변동, trigger 자동 기록)
- 수집 이력: collection_runs 테이블 (status: "success" | "partial" | "error" | "running")
- 파싱 함수:
  - _parse_flight_cards() — collector_google_flights.py:338, DOM regex + JSON.loads, 실패 시 [] 반환
  - _parse_cards()        — collector_naver.py:146, 동일 패턴
  - 가격 유효범위: 20,000 ≤ price ≤ 3,000,000 원 (JS injection 단계에서 필터)

[진단 순서]
1. get_collection_status() — 최근 실행 이력 + 자동 감지된 anomalies 확인
2. get_collection_stats() — 노선별 수집량 drop + stale 노선 확인
3. anomalies 또는 stale/drop 이상이 있으면:
   - collection_runs.error_log 분석 (runs 목록에 포함됨)
   - 의심 노선에 compare_sources() 호출하여 소스별 격차 확인
   - 파싱 실패 의심 시 read_source_file()로 관련 함수 범위 확인
4. send_telegram_report()로 리포트 전송 — 이상 없어도 반드시 전송

[리포트 형식]

이상 없음:
✅ [YYYY-MM-DD HH:MM KST] 데이터 정상
- 수집: GoogleFlights N건 / Naver N건 (총 N건)
- 노선 커버리지: N개 노선, stale 없음

이상 있음:
🚨 [YYYY-MM-DD HH:MM KST] 데이터 이상 감지

[이상 요약]
- (항목별)

[데이터 샘플]
- (관련 DB 조회 결과 발췌, 숫자/날짜 포함)

[원인 가설]
- 가설 1: (내용) — 확신도: 높음/중간/낮음
- 가설 2: ...

[관련 파일·함수]
- 파일명:줄번호 함수명()

[Claude Code 지시문]
> (한 줄, 예: "collector_google_flights.py:338 _parse_flight_cards()에서 id='__fl__' 셀렉터를 확인하고 DOM 변경 여부에 따라 정규식 수정")
"""


def _wait_for_collection(timeout_sec: int = 900, poll_sec: int = 30) -> None:
    """최근 collection_run이 'running'이면 완료까지 대기 (최대 15분)."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(dsn)
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT status, started_at
                    FROM collection_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
            finally:
                conn.close()
        except Exception as e:
            print(f"[diagnosis] DB 연결 실패, 대기 생략: {e}", flush=True)
            return

        if not row or row[0] != "running":
            return

        started_at = row[1]
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - started_at

        if age >= timedelta(minutes=30):
            print(
                f"[diagnosis] run이 {int(age.total_seconds() // 60)}분째 'running' 상태 — "
                "진단 강제 진행 (크래시 의심, 이상 항목으로 포함됨)",
                flush=True,
            )
            return

        elapsed = int(age.total_seconds() // 60)
        print(
            f"[diagnosis] 수집 진행 중 ({elapsed}분 경과), {poll_sec}초 후 재확인...",
            flush=True,
        )
        time.sleep(poll_sec)

    print("[diagnosis] 대기 시간 초과 — 진단 강제 진행", flush=True)


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[diagnosis] ANTHROPIC_API_KEY 미설정 — 종료", file=sys.stderr, flush=True)
        sys.exit(1)

    _wait_for_collection()

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    domain = os.environ.get("DOMAIN", "localhost")
    mcp_key = os.environ.get("MCP_API_KEY", "")
    mcp_url = f"https://{domain}/mcp/sse"

    now_kst = datetime.now(_KST).strftime("%Y-%m-%d %H:%M KST")

    print(f"[diagnosis] 진단 시작 — {now_kst} / MCP: {mcp_url}", flush=True)

    try:
        response = client.beta.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    f"현재 시각: {now_kst}\n"
                    "크롤링이 완료됐습니다. 데이터 품질을 진단하고 텔레그램으로 리포트를 보내주세요."
                ),
            }],
            betas=["mcp-client-2025-04-04"],
            mcp_servers=[{
                "type": "url",
                "url": mcp_url,
                "name": "flight-friend",
                "authorization_token": mcp_key,
            }],
        )
    except Exception as e:
        print(f"[diagnosis] Anthropic API 호출 실패: {e}", file=sys.stderr, flush=True)
        sys.exit(1)

    print(f"[diagnosis] 완료 — stop_reason={response.stop_reason}", flush=True)

    for block in response.content:
        if hasattr(block, "text"):
            print(f"[diagnosis] 응답:\n{block.text}", flush=True)
            break


if __name__ == "__main__":
    main()
