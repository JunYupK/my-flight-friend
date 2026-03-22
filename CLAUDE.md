# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## Project: my-flight-friend

ICN 출발 일본 항공권 최저가 모니터링 도구. 복수 데이터 소스에서 편도 항공편을 수집해 왕복 조합을 만들고, 목표가 이하 딜을 알림으로 전송한다.

### Commands

```bash
# PostgreSQL DB 시작 (필수)
docker compose up -d

# 항공권 수집 실행
python main.py

# FastAPI 백엔드 실행 (루트에서)
uvicorn flight_front.api.main:app --reload

# React 프론트엔드 개발 서버 (flight_front/web/)
cd flight_front/web && npm run dev

# 테스트 실행
pytest tests/

# 단일 테스트 클래스/함수
pytest tests/test_flight_monitor.py::TestShouldNotify
pytest tests/test_flight_monitor.py::TestShouldNotify::test_price_drop_triggers_realert
```

### Environment Variables

`DATABASE_URL` is required. Others are optional (gracefully skipped if missing):
```
DATABASE_URL=postgresql://flight_user:flight_pass@localhost:5432/flights
AMADEUS_CLIENT_ID=...
AMADEUS_CLIENT_SECRET=...
CALLMEBOT_PHONE=...
CALLMEBOT_API_KEY=...
GMAIL_ADDRESS=...
GMAIL_APP_PASSWORD=...
ALERT_EMAIL=...
```

### Architecture

**Data flow:** `main.py` → collectors → `storage.save_prices()` → alert check → `notifier.notify()`

**Data sources** (all produce the same offer dict shape):
- `collector_amadeus.py` — Amadeus REST API (FSC carriers KE/OZ only). Requires `AMADEUS_CLIENT_ID`/`AMADEUS_CLIENT_SECRET`.
- `collector_google_flights.py` — crawl4ai headless browser. Scrapes `li.pIav2d` cards via JS injection. Encodes date into base64 `tfs=` URL parameter by replacing bytes in `_TFS_TEMPLATES`. Only ICN↔TYO is registered; other routes need new tfs= values added.
- `collector_lcc.py` — Naver flight GraphQL API (pagination via `galileoFlag`/`travelBizFlag`). Not wired into `main.py` (only `fetch_fsc_offers` + `fetch_google_flights_offers` are called), but its internal functions `_index_topk_by_date` and `_combine_roundtrips` are covered by tests.

**Offer dict shape** (all collectors must produce these fields):
```python
{
  "source", "trip_type", "origin", "destination", "destination_name",
  "departure_date", "return_date", "stay_nights", "price", "currency",
  "out_airline", "in_airline", "is_mixed_airline", "checked_at",
  "out_url", "in_url",   # Google Flights 검색 URL (Amadeus는 None)
  # optional: out_dep_time, out_arr_time, out_duration_min, out_stops,
  #           in_dep_time,  in_arr_time,  in_duration_min,  in_stops,
  #           out_arr_airport, in_dep_airport
}
```

**Storage** (`storage.py`): PostgreSQL via psycopg2. Uses `DATABASE_URL` env var. Tables:
- `price_history`: 수집된 항공권 append-only (out_url, in_url 포함)
- `alert_state`: 알림 dedup/cooldown
- `app_config`: JSONB, search_config만 저장
- `airports`: 목적지 공항 관리 (code PK, name, tfs_out, tfs_in)

View: `v_best_observed` — 노선/항공사 조합별 최저가 + 최신 url.

**Alert logic**: `should_notify()` blocks re-alerts within `alert_cooldown_hours` unless price drops by ≥ `alert_realert_drop_krw`.

**Web UI** (`flight_front/`): FastAPI backend (`flight_front/api/main.py`) + React/Vite frontend (`flight_front/web/`). API endpoints:
- `GET/PUT /api/config` — search_config만 read/write
- `GET /api/airports`, `POST /api/airports`, `DELETE /api/airports/{code}` — airports 테이블 CRUD
- `POST /api/run` — spawn `main.py` as subprocess (UTF-8 인코딩 강제); `GET /api/run/status`; `WS /ws/run` live log
- `GET /api/results` — top-5 deals per destination from `v_best_observed`

Frontend stack: React 18, TypeScript, Tailwind CSS, Vite. Two tabs: "수집 결과" (results) and "설정" (config + run control).
- `AirportList.tsx`: 독립 컴포넌트, `/api/airports` 직접 연동. 공항별 개별 저장/삭제, 하단 추가 폼. tfs= 값 또는 전체 URL 모두 허용.
- `Results.tsx`: url 있는 딜에 "출발편 검색 ↗" / "복귀편 검색 ↗" 버튼 표시.

**Config persistence** (`flight_monitor/config_db.py`): `apply_db_config()`이 `airports` 테이블에서 `JAPAN_AIRPORTS`/`TFS_TEMPLATES` 패치, `app_config`에서 `SEARCH_CONFIG` 패치. `config.py` 기본값은 fallback.

**MCP server** (`mcp_server.py`): Three query functions (`get_best_deals`, `get_price_history`, `explain_deal`) for use with Claude Desktop. Uses `%s` placeholders and `psycopg2.extras.RealDictCursor`. Date filtering uses `LEFT(departure_date, 7)` (dates stored as TEXT 'YYYY-MM-DD').

**Config** (`config.py`): All tunable parameters live in `SEARCH_CONFIG`. Key settings:
- `lcc_max_days`: set to `None` for full-month collection
- `search_months`: list of `"YYYY-MM"` strings
- `target_price_krw`: alert threshold in KRW
- `JAPAN_AIRPORTS` / `TFS_TEMPLATES`: 런타임에 `airports` 테이블로 채워짐 — 웹 UI 설정 탭에서 관리

**Tests** (`tests/test_flight_monitor.py`): PostgreSQL 기반. `clean_db` fixture가 각 테스트 전 `init_db()`, 후 `TRUNCATE ... RESTART IDENTITY CASCADE`로 격리. `pytest` 설치 필요 (`.venv/Scripts/pip install pytest`).

**Windows 주의사항**: subprocess로 `main.py` 실행 시 `PYTHONIOENCODING=utf-8` + `encoding="utf-8"` 필수 (crawl4ai가 `✓` 등 특수문자 출력으로 cp949 오류 발생).

### Known Issues

1. Foreign LCC airlines (Peach, Zipair, etc.) missing from `AIRLINES` list in `_extract_js()` in `collector_google_flights.py`
2. `collector_lcc.py` is not wired into `main.py` — only `fetch_fsc_offers` + `fetch_google_flights_offers` are called

---

### Portfolio

**[my-flight-friend — ICN↔일본 항공권 최저가 모니터링]**

- **상황:**
  일본 항공권을 수동으로 비교 검색하는 데 시간이 과도하게 소요.
  여러 사이트(Google Flights, Amadeus, Skyscanner, Naver)마다 가격이 다르고,
  최저가 타이밍을 놓치면 수만 원 차이 발생.
  자동으로 복수 소스를 수집해 왕복 조합 최저가를 추적하고, 목표가 이하일 때 즉시 알림받는 시스템이 필요했음.

- **내 역할:**
  아키텍처 설계 + 전체 구현 (단독 프로젝트)
  데이터 수집 파이프라인, 왕복 조합 알고리즘, 알림 시스템, FastAPI 백엔드,
  React 프론트엔드, CI/CD, 클라우드 인프라 운영까지 전 레이어 담당.

- **행동:**
  1. 4개 데이터 소스별 collector 설계 — Amadeus REST API, Google Flights headless 크롤링(crawl4ai + JS injection), Naver GraphQL(pagination), Skyscanner RapidAPI — 모두 동일한 offer dict 형태로 정규화
  2. Google Flights 크롤러 속도 병목 발견 (12개월 × 5공항 순차 수집) → `arun_many` 배치 병렬 크롤링으로 전환, OCI 한국 리전 이전으로 레이턴시 추가 개선
  3. 편도 항공편 수집 후 왕복 조합 생성 알고리즘 구현, 알림 dedup/cooldown 로직으로 중복 알림 방지 + 가격 하락 시 재알림 트리거
  4. FastAPI + React(TypeScript, Tailwind) 웹 UI 구축 — 수집 결과 조회, 검색 설정, 공항 관리, 실시간 수집 로그(WebSocket), Google Flights 예약 페이지 직접 링크
  5. Docker Compose 멀티 컨테이너 구성 (app, db, collector, caddy) + GitHub Actions CI/CD 파이프라인 구축 — push 시 pytest + React build 검증 후 SSH 자동 배포 + 헬스체크
  6. Caddy 리버스 프록시로 자동 HTTPS, cron 기반 3시간 주기 수집 + DB 백업 자동화

- **결과:**
  4개 소스 통합 수집 → 왕복 조합 → 목표가 알림까지 완전 자동화 파이프라인 운영 중
  28개 테스트 케이스 (PostgreSQL 기반 통합 테스트, 테스트 간 DB 격리)
  CI/CD 자동 배포 (CI 성공 시 무중단 배포 + 헬스체크)
  OCI 한국 리전 단일 서버에서 비용 최소화 운영
  커밋 80회, 13 PR (2026-03-03 ~ 현재, 지속 개발 중)

- **기술 스택:**
  Python, FastAPI, React 18, TypeScript, Tailwind CSS, PostgreSQL, Docker Compose,
  GitHub Actions, Caddy, OCI, crawl4ai, psycopg2, WebSocket
