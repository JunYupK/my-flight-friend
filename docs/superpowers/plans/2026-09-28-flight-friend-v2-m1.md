# Flight Friend V2 — M1 (Google Flights) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trip 중심·스냅샷 기반 V2를 Google Flights 단일 제공자로 끝까지 동작시킨다 (Trip 생성 → 자동/수동 검색 → 결과·대표 후보·추적 요약·알림 → 예약 링크).

**Architecture:** 새 파이썬 패키지 `flight_friend/`(types · repo · providers · domain · worker · api)를 V1(`flight_monitor/`, `flight_front/api/`) 옆에 만든다. 도메인 로직은 DB·크롤러 없는 순수 함수로 두고, 상주 `search-worker`가 PostgreSQL `search_runs` 큐를 소비해 GF 어댑터를 실행한다. API는 enqueue·조회만 하며, React 앱(`flight_front/web/`)은 화면을 새로 작성한다. V1 삭제는 M1 실사용 확인 후 마지막 task에서 한다.

**Tech Stack:** Python 3.11, FastAPI, psycopg2, crawl4ai(worker 전용), PostgreSQL 16, pytest, React 18 + TypeScript + Vite + Tailwind + react-router, Recharts, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-28-flight-friend-v2-design.md` (이하 "스펙 §N")

## Global Constraints

- **작업 로그:** 모든 task의 마지막 커밋에 `log.md` 항목 추가를 포함한다 (형식은 `log.md` 상단). 작업 시작 전 `log.md`의 "현재 상태"와 최신 항목을 읽는다. Claude Code와 Codex가 task 단위로 교대한다.
- 출발지는 `ICN` 고정. 통화 `KRW`, 성인 1명·일반석이 기본값 (스펙 §3).
- 시각 기준은 KST (`Asia/Seoul`). DB 컬럼은 `TIMESTAMPTZ`.
- V2 테이블은 전부 append-only: `snapshots`, `leg_quotes`, `rt_quotes`는 INSERT만 한다 (스펙 §9.3). V1의 `LEAST` 누적·최저가 덮어쓰기 금지 (스펙 §4.1).
- **V1 수집기(`main.py`, `scripts/collect_and_diagnose.sh`)를 실행하지 않는다** — `cleanup_old_data()`가 `raw_legs`를 삭제한다 (스펙 §10.2).
- 테스트에서 실제 외부 호출 금지 (crawl4ai/HTTP/Telegram은 fake 또는 monkeypatch). DB 테스트는 PostgreSQL + TRUNCATE 격리 (기존 `tests/` 패턴).
- `flight_friend` 안의 crawl4ai import는 `providers/google_flights.py`와 `worker.py`에서만, 그리고 함수 내부 또는 `try/except ImportError`로 — CI는 crawl4ai 없이 돈다.
- 파이썬: 함수 파라미터·반환 타입 힌트 필수, `Any` 금지 (AGENTS.md §4). `ruff check .` 통과.
- TypeScript: `any`·`as` 단언 금지, 컴포넌트에서 직접 `fetch` 금지(`api.ts` 경유), 전역 상태 라이브러리 추가 금지 (AGENTS.md §4).
- 스펙이 잠정으로 둔 값은 상수 한 곳에 모은다: 갱신 주기 6h/2h/1h, W = 주기 × 2, 수동 쿨다운 5분, stuck run 10분, 조건 밖 힌트 임계(≥10% 또는 ≥30,000원), 알림 하락 임계(≥3% 또는 ≥10,000원), 추적 통계 최소 3일.

## Review Focus

- **자정 넘는 도착·출발:** `arr_time < dep_time`인 편(예: 23:40→02:10)은 다음날 도착이다. 현지 체류시간·시간대 필터가 음수나 오판을 내면 안 된다 → Task 8 `test_stay_minutes_overnight_arrival`.
- **선호 조건을 만족하는 편이 한쪽 방향에 0개:** 대표 후보·추적 값이 예외 없이 "없음"을 반환하고, 조건 밖 힌트는 여전히 계산된다 → Task 8 `test_pareto_empty_when_one_side_filtered_out`, Task 7 `test_near_miss_when_no_in_condition_leg`.
- **모든 스냅샷이 W를 넘어 오래됨 (수일간 worker 정지):** 카드는 보이되 헤드라인·추적 현재값은 `None`이며 화면이 깨지지 않는다 → Task 7 `test_all_stale_best_price_none`, Task 11 `test_trip_view_all_stale`.
- **출발일이 지난 Trip / 오늘 출발 Trip:** 자동 갱신 대상에서 빠지고, `days_to_departure`가 0 이하에서도 주기 계산이 예외를 내지 않는다 → Task 6 `test_not_due_after_departure`, `test_interval_on_departure_day`.
- **GF가 같은 편을 한 페이지에 두 번 반환 / 편명 없는 카드:** 중복 없이 1건, 편명 없는 카드는 항공사명 정규화로 키를 만든다(병합 실패 시 중복 쪽으로) → Task 5 `test_dedupe_same_flight`, Task 4 `test_flight_key_without_flight_number`.

---

## File Structure

```
flight_friend/
  __init__.py
  types.py              # dataclass: Trip, Preferences, Run, LegQuote, RtQuote, ProviderResult, Snapshot
  config.py             # 잠정 상수 (Global Constraints 목록)
  db.py                 # get_conn(), init_schema() — V2 테이블
  repo.py               # trips / runs / snapshots / alerts CRUD
  providers/
    __init__.py
    airlines.py         # 항공사 정규화, flight_key()
    google_flights.py   # URL 생성, 카드 추출 JS·파싱, search_oneway/search_roundtrip
  domain/
    __init__.py
    schedule.py         # 갱신 주기, W, due 판정, 쿨다운
    results.py          # 현재 편도 병합, 선호 조건, 조건 밖 힌트, 조합·파레토, 왕복 참고가
    tracking.py         # run별 추적 값, 일별 시리즈, 통계, 알림 판정
  worker.py             # 큐 소비·실행·스케줄러·알림 (python -m flight_friend.worker)
  api/
    __init__.py
    views.py            # 도메인 → 응답 dict 조립 (Service 레이어)
    main.py             # FastAPI 라우트 + SPA 정적 서빙
tests/v2/
  conftest.py           # V2 DB fixture
  test_*.py
flight_front/web/src/   # V2 화면 (Task 12–15에서 교체)
```

---

### Task 1: V2 패키지 골격 · 타입 · 스키마

**Files:**
- Create: `flight_friend/__init__.py`, `flight_friend/types.py`, `flight_friend/config.py`, `flight_friend/db.py`
- Create: `tests/v2/__init__.py`, `tests/v2/conftest.py`, `tests/v2/test_db.py`

**Interfaces:**
- Produces:
  - `flight_friend.db.get_conn()` — 기존 `flight_monitor.storage.get_conn`과 동일 동작(컨텍스트 매니저, commit/rollback, `SET TIME ZONE 'Asia/Seoul'`), `DATABASE_URL` 사용.
  - `flight_friend.db.init_schema() -> None` — 스펙 §9.3 테이블(`trips`, `search_runs`, `snapshots`, `leg_quotes`, `rt_quotes`, `alerts`)을 `CREATE TABLE IF NOT EXISTS`로 생성. 멱등.
  - `flight_friend.types`:
    - `Preferences(out_dep_window: tuple[str,str] | None = None, in_dep_window: tuple[str,str] | None = None, nonstop_only: bool = False, include_airlines: list[str] = [], exclude_airlines: list[str] = [], max_price: int | None = None, max_duration_min: int | None = None)` + `to_dict()` / `from_dict(d)`
    - `Trip(id: int, origin: str, destination: str, out_date: date, ret_date: date, adults: int, cabin: str, prefs: Preferences, target_price: int | None, tracking: bool, created_at: datetime, archived_at: datetime | None)`
    - `Run(id: int, trip_id: int, trigger: str, status: str, requested_at: datetime, started_at: datetime | None, finished_at: datetime | None)`
    - `LegQuote(flight_key: str, airline_iata: str, airline_name: str, flight_numbers: list[str], dep_airport: str, arr_airport: str, dep_time: str, arr_time: str, duration_min: int | None, stops: int | None, price: int, booking_url: str | None, search_url: str | None)`
    - `RtQuote(airline_iata: str, out_flight_key: str, total_price: int)`
    - `ProviderResult(status: Literal["ok","empty","blocked","error"], legs: list[LegQuote], rts: list[RtQuote], error: str | None, seconds: float)`
    - `Snapshot(id: int, run_id: int, trip_id: int, provider: str, kind: Literal["oneway","roundtrip"], direction: Literal["out","in"] | None, date: date, status: str, card_count: int, observed_at: datetime, error: str | None, legs: list[LegQuote], rts: list[RtQuote])`
  - `flight_friend.config`: `ORIGIN="ICN"`, `MANUAL_COOLDOWN=timedelta(minutes=5)`, `STUCK_RUN_AFTER=timedelta(minutes=10)`, `NEAR_MISS_MIN_PCT=0.10`, `NEAR_MISS_MIN_KRW=30_000`, `ALERT_DROP_PCT=0.03`, `ALERT_DROP_KRW=10_000`, `MIN_TRACKING_DAYS=3`.
  - `tests/v2/conftest.py`: autouse fixture `v2_db` — `init_schema()` 후 yield, 종료 시 V2 6개 테이블 `TRUNCATE ... RESTART IDENTITY CASCADE`.

- [ ] **Step 1: Write the failing test** — `tests/v2/test_db.py::test_init_schema_idempotent` (두 번 호출해도 예외 없음, `information_schema.tables`에 6개 테이블 존재), `test_leg_quotes_cascade_on_snapshot` (FK `ON DELETE CASCADE`: snapshot 삭제 시 leg_quotes 삭제).
- [ ] **Step 2: Run** `pytest tests/v2/test_db.py -v` → FAIL (`ModuleNotFoundError: flight_friend`).
- [ ] **Step 3: Implement** `types.py`, `config.py`, `db.py`. 스키마 세부: `trips.prefs JSONB NOT NULL DEFAULT '{}'`, `trips.tracking BOOL NOT NULL DEFAULT TRUE`, `search_runs.status DEFAULT 'queued'`, `leg_quotes.flight_numbers TEXT[]`, 인덱스 `search_runs(status, requested_at)`, `snapshots(trip_id, observed_at)`, `leg_quotes(snapshot_id)`, `rt_quotes(snapshot_id)`, `alerts(trip_id, kind, sent_at)`. 모든 FK `ON DELETE CASCADE`.
- [ ] **Step 4: Run** `pytest tests/v2/test_db.py -v` → PASS; `ruff check flight_friend tests/v2` → clean.
- [ ] **Step 5: Commit** (`log.md` 항목 포함) — `feat(v2): add flight_friend package skeleton, types and schema`

### Task 2: Repository — trips · runs

**Files:**
- Create: `flight_friend/repo.py`, `tests/v2/test_repo_trips_runs.py`

**Interfaces:**
- Consumes: Task 1 `get_conn`, `Trip`, `Run`, `Preferences`.
- Produces (`flight_friend.repo`):
  - `create_trip(destination: str, out_date: date, ret_date: date, prefs: Preferences, target_price: int | None = None) -> int`
  - `get_trip(trip_id: int) -> Trip | None`, `list_trips() -> list[Trip]` (출국일 오름차순)
  - `update_trip(trip_id: int, *, prefs: Preferences | None = None, tracking: bool | None = None, target_price: int | None = None, clear_target: bool = False) -> None`
  - `enqueue_run(trip_id: int, trigger: Literal["schedule","manual"]) -> int`
  - `get_run(run_id: int) -> Run | None`, `latest_run(trip_id: int) -> Run | None` (requested_at 최신)
  - `claim_next_run() -> Run | None` — 가장 오래된 `queued` 1건을 `FOR UPDATE SKIP LOCKED`로 잡아 `running`, `started_at=now()`로 바꾸고 반환
  - `finish_run(run_id: int, status: Literal["done","error"]) -> None`
  - `expire_stuck_runs(older_than: timedelta) -> int` — `running`이고 `started_at < now()-older_than`인 것을 `error`로
  - `has_open_run(trip_id: int) -> bool` — `queued` 또는 `running` 존재 여부

- [ ] **Step 1: Write failing tests:** `test_create_and_get_trip_roundtrips_prefs` (시간창 `("08:00","14:00")`가 그대로 복원), `test_list_trips_ordered_by_out_date`, `test_update_trip_partial` (prefs만 바꿔도 tracking 유지), `test_claim_is_fifo_and_single` (두 번 enqueue → 첫 claim이 먼저 요청된 run, 두 번째 claim이 다른 run, 세 번째 `None`), `test_expire_stuck_runs` (started_at을 11분 전으로 UPDATE 후 `expire_stuck_runs(timedelta(minutes=10)) == 1`, status `error`), `test_has_open_run`.
- [ ] **Step 2: Run** `pytest tests/v2/test_repo_trips_runs.py -v` → FAIL.
- [ ] **Step 3: Implement** 위 함수들 (`RealDictCursor` → dataclass 변환 헬퍼 1개).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): trips and search run queue repository`

### Task 3: Repository — snapshots · quotes · alerts · admin

**Files:**
- Modify: `flight_friend/repo.py`
- Create: `tests/v2/test_repo_snapshots.py`

**Interfaces:**
- Consumes: Task 1 types, Task 2 `create_trip`/`enqueue_run`.
- Produces:
  - `save_snapshot(run_id: int, trip_id: int, provider: str, kind: str, direction: str | None, date_: date, result: ProviderResult, observed_at: datetime) -> int` — snapshot 1행 + legs/rts 일괄 INSERT, 한 트랜잭션.
  - `load_snapshots(trip_id: int, since: datetime | None = None) -> list[Snapshot]` — 관측 시각 오름차순, legs/rts 채워서.
  - `record_alert(trip_id: int, kind: Literal["new_low","target","ops"], price: int | None) -> None`, `last_alert(trip_id: int, kind: str) -> tuple[int | None, datetime] | None`
  - `recent_runs(limit: int = 50) -> list[dict]` (run + trip destination + 스냅샷 상태 요약), `provider_stats(days: int = 7) -> list[dict]` (`{provider, day, total, ok, empty, blocked, error}`)

- [ ] **Step 1: Write failing tests:** `test_save_and_load_snapshot_with_quotes` (LegQuote 2건·RtQuote 1건 저장 후 동일 값 복원, `flight_numbers` 리스트 포함), `test_load_snapshots_since_filter`, `test_error_snapshot_has_no_quotes` (status `error`, legs 0), `test_last_alert_returns_latest`, `test_provider_stats_counts_by_status`.
- [ ] **Step 2: Run** `pytest tests/v2/test_repo_snapshots.py -v` → FAIL.
- [ ] **Step 3: Implement** (`psycopg2.extras.execute_values`로 quotes 일괄 INSERT).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): snapshot, quote and alert repository`

### Task 4: 항공사 정규화 · 항공편 식별키

**Files:**
- Create: `flight_friend/providers/__init__.py`, `flight_friend/providers/airlines.py`, `tests/v2/test_airlines.py`

**Interfaces:**
- Produces:
  - `normalize_airline(name: str) -> str | None` — 한글/영문/리브랜딩 표기 → IATA. 공백 제거·소문자 비교. 모르면 `None`.
  - `airline_iata(name: str, flight_numbers: list[str]) -> str` — 편명이 있으면 첫 편명의 항공사 코드(`"RS 727"` → `"RS"`), 없으면 `normalize_airline(name)`, 그것도 없으면 `"?" + 공백 제거한 name`.
  - `flight_key(date_: date, dep_airport: str, arr_airport: str, dep_time: str, arr_time: str, stops: int | None, airline: str) -> str` → `"2026-10-21|ICN|FUK|14:25|16:00|0|RS"` (stops None → `"?"`).
- 매핑 시작점: V1 `collector_google_flights._AIRLINE_IATA` 전체 + 스펙 §13 실측 표기 차이: 스쿳항공/스쿠트항공→TR, 필리핀항공/필리핀 항공→PR, Trinity Airways/티웨이항공→TW, 말레이항공/말레이시아 항공→MH, 홍콩 익스프레스항공/홍콩익스프레스→UO, 세부퍼시픽/세부 퍼시픽 에어→5J, 홍콩항공/홍콩 항공→HX, Batik Air/바틱에어말레이시아→OD, 샤먼항공/하문항공→MF, 동방항공/중국동방항공→MU, Aero K Airlines/에어로케이→RF, Sun PhuQuoc Airways/선 푸꾸옥 항공→9G. `한 에어 시스템`은 매핑하지 않는다(발권사 — 운항사가 아님).

- [ ] **Step 1: Write failing tests:** `test_normalize_variants` (위 쌍 각각 같은 코드), `test_normalize_unknown_returns_none`, `test_airline_from_flight_number_wins` (`airline_iata("아무이름", ["LJ 357"]) == "LJ"`), `test_flight_key_without_flight_number` (편명 없음 + 미지 항공사 → 키 끝이 `?항공사명`; 서로 다른 미지 항공사는 다른 키), `test_flight_key_format`.
- [ ] **Step 2: Run** `pytest tests/v2/test_airlines.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): airline normalization and flight identity key`

### Task 5: Google Flights 어댑터

**Files:**
- Create: `flight_friend/providers/google_flights.py`, `tests/v2/test_google_flights.py`, `tests/v2/fixtures/gf_cards.html`

**Interfaces:**
- Consumes: Task 1 `LegQuote`/`RtQuote`/`ProviderResult`, Task 4 `airline_iata`/`flight_key`.
- Produces:
  - `build_oneway_url(dep: str, arr: str, date_: date) -> str`, `build_roundtrip_url(dep: str, arr: str, out_date: date, ret_date: date) -> str` — 템플릿 없는 protobuf `tfs` (스펙 §5.2). outer 필드: `1:28, 2:2, 3:<FlightData>…, 8:1, 9:1, 14:1, 16:{08 ff×9 01}, 19:<2 편도 | 1 왕복>`; FlightData `2:date, 13:{1:1,2:dep}, 14:{1:1,2:arr}`. URL 접미 `&curr=KRW&hl=ko`.
  - `build_booking_url(...)` — V1 `_build_booking_tfs`/`_build_booking_url`을 옮긴다.
  - `extract_js() -> str`, `parse_cards(html: str) -> list[dict]` — V1 `_extract_js`/`_parse_flight_cards`를 그대로 옮긴다.
  - `cards_to_legs(cards: list[dict], date_: date, dep: str, arr: str, search_url: str) -> list[LegQuote]` — `flight_key`로 dedupe(같은 키면 최저가 1건), 가격 오름차순.
  - `cards_to_rts(cards: list[dict], out_date: date, dep: str, arr: str) -> list[RtQuote]` — 왕복 페이지 카드(가격=왕복 총액)를 출국편 키로.
  - `async search_oneway(crawler, dep: str, arr: str, date_: date) -> ProviderResult`, `async search_roundtrip(crawler, dep: str, arr: str, out_date: date, ret_date: date) -> ProviderResult` — crawler는 `arun(url, config)`을 가진 객체. `CrawlerRunConfig(magic=True, js_code=[scroll_js, extract_js()], wait_for="js:() => !!document.querySelector('li.pIav2d')", delay_before_return_html=4.0, cache_mode="bypass", page_timeout=15000)`. 상태: 카드>0 → `ok`; 카드 0 + HTML에 `unusual traffic`/`sorry/index`/`recaptcha` → `blocked`; 카드 0 → `empty`; 예외·`success=False` → `error`. (`captcha` 단독 문자열은 정상 페이지에도 있어 판정에 쓰지 않는다 — 스펙 §9.2.)
- 스크롤 JS는 V1 `crawler_utils.make_scroll_js()`를 옮긴다.

- [ ] **Step 1: Write failing tests:**
  - `test_oneway_url_structure` — `tfs`를 base64 디코드해 날짜 `2026-10-21`, `ICN`, `FUK`, 필드 19=2 확인, `tfs`가 `CBwQAh`로 시작.
  - `test_roundtrip_url_has_two_legs_and_trip_1`.
  - `test_parse_cards_from_fixture` — fixture HTML(`<div id="__fl__">[…JSON…]</div>`, 스펙 §13의 FUK 샘플 3건 + LJ 357 중복 1건) 파싱.
  - `test_dedupe_same_flight` — 중복 카드 → LegQuote 1건.
  - `test_legs_sorted_by_price_and_airline_from_flight_number`.
  - `test_status_mapping` — fake crawler로 (카드 있음 → ok), (카드 0 + `unusual traffic` → blocked), (카드 0 + `captcha`만 → empty), (예외 → error, `error` 메시지 보존).
- [ ] **Step 2: Run** `pytest tests/v2/test_google_flights.py -v` → FAIL.
- [ ] **Step 3: Implement.** crawl4ai `CrawlerRunConfig`는 함수 안에서 import (없으면 `status="error", error="crawl4ai not installed"`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): template-free Google Flights adapter`

### Task 6: 도메인 — 갱신 스케줄

**Files:**
- Create: `flight_friend/domain/__init__.py`, `flight_friend/domain/schedule.py`, `tests/v2/test_schedule.py`

**Interfaces:**
- Produces:
  - `refresh_interval(days_to_departure: int) -> timedelta` — `>60` → 6h, `15..60` → 2h, `<=14` → 1h (0·음수 포함).
  - `freshness_window(days_to_departure: int) -> timedelta` = `refresh_interval × 2`.
  - `days_to_departure(out_date: date, today: date) -> int`.
  - `is_due(trip: Trip, last_requested_at: datetime | None, now: datetime) -> bool` — `tracking` 참, `archived_at` 없음, `out_date >= today`, 그리고 (`last_requested_at` 없음 또는 `now - last_requested_at >= refresh_interval`).
  - `cooldown_remaining(last_requested_at: datetime | None, now: datetime) -> timedelta` — `MANUAL_COOLDOWN` 기준, 음수면 0.

- [ ] **Step 1: Write failing tests:** `test_interval_tiers` (61→6h, 60→2h, 15→2h, 14→1h), `test_interval_on_departure_day` (0, -1 → 1h, 예외 없음), `test_window_is_double`, `test_due_when_never_run`, `test_not_due_within_interval`, `test_not_due_when_tracking_off`, `test_not_due_after_departure`, `test_cooldown_remaining`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): refresh schedule rules`

### Task 7: 도메인 — 현재 편도 병합 · 선호 조건 · 조건 밖 힌트

**Files:**
- Create: `flight_friend/domain/results.py`, `tests/v2/test_results_legs.py`

**Interfaces:**
- Consumes: Task 1 `Snapshot`, `LegQuote`, `Preferences`; Task 6 `freshness_window`.
- Produces:
  - `ProviderPrice(provider: str, price: int, observed_at: datetime, booking_url: str | None, stale: bool)`
  - `MergedLeg(flight_key: str, direction: str, leg: LegQuote, prices: list[ProviderPrice], best_price: int | None, best_provider: str | None)` — `leg`는 대표 속성(시각·항공사 등), `best_*`는 stale 아닌 가격 중 최저 (없으면 `None`).
  - `current_legs(snapshots: list[Snapshot], now: datetime, window: timedelta) -> dict[str, list[MergedLeg]]` — 키 `"out"`/`"in"`. 규칙(스펙 §4.1): (provider, kind=oneway, direction)별 **최신 `ok` 스냅샷만** 사용; 그 안의 legs를 `flight_key`로 제공자 병합; `observed_at < now - window`면 `stale=True`. 정렬: `best_price` 오름차순, `None`은 뒤.
  - `violations(m: MergedLeg, direction: str, prefs: Preferences) -> list[str]` — 이름: `"time_window"`, `"nonstop"`, `"airline"`, `"duration"`. 시간창은 해당 방향 출발시각 기준, 양끝 포함. (`max_price`는 조합 단위 → Task 8.)
  - `NearMiss(direction: str, leg: MergedLeg, violated: str, combo_price: int, saving: int)`
  - `near_miss(legs: dict[str, list[MergedLeg]], prefs: Preferences) -> NearMiss | None` — 후보 = 한 방향의 **위반이 정확히 1개**인 최저가 편 + 반대 방향의 **조건 내** 최저가 편 (`best_price` 있는 편만). 규칙:
    1. 조건 내 최저 조합가 `M`이 있으면: 후보 중 `saving = M - combo_price`가 `>= NEAR_MISS_MIN_KRW` 또는 `>= NEAR_MISS_MIN_PCT × M`인 것 중 절감이 가장 큰 것을 반환, 없으면 `None`.
    2. `M`이 없으면(조건 내 조합 없음): 후보 중 가장 싼 것을 `saving=0`으로 반환("조건 하나만 풀면 선택지가 생김"), 후보도 없으면 `None`.

- [ ] **Step 1: Write failing tests:**
  - `test_latest_ok_snapshot_only` — 같은 방향 ok 스냅샷 2개(구·신) 중 신 것의 가격만 쓰고, 구 스냅샷에만 있던 편은 결과에 없음 (스펙 §4.1-2).
  - `test_failed_provider_keeps_previous_ok` — 최신이 `error`면 직전 `ok` 사용.
  - `test_stale_excluded_from_best` — W 밖 가격은 `stale=True`, `best_price`에 미반영.
  - `test_all_stale_best_price_none`.
  - `test_violations_time_window_inclusive` (`08:00` 포함, `14:01` 위반), `test_violations_nonstop_airline_duration`.
  - `test_near_miss_one_violation_with_saving` — 조건 내 최저 조합 300,000, 07:30 편으로 248,000 → `saving=52000`, `violated="time_window"`.
  - `test_near_miss_ignores_two_violations`, `test_near_miss_below_threshold_none` (절감 5,000).
  - `test_near_miss_when_no_in_condition_leg` — 조건 내 조합 없음 + 1-위반 존재 → `saving=0`으로 반환.
- [ ] **Step 2: Run** `pytest tests/v2/test_results_legs.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): current leg merge, preferences and near-miss hint`

### Task 8: 도메인 — 조합 · 파레토 대표 후보 · 왕복 참고가

**Files:**
- Modify: `flight_friend/domain/results.py`
- Create: `tests/v2/test_results_combos.py`

**Interfaces:**
- Consumes: Task 7 `MergedLeg`, `violations`; Task 1 `RtQuote`, `Snapshot`.
- Produces:
  - `stay_minutes(out: LegQuote, out_date: date, inn: LegQuote, ret_date: date) -> int` — 출국편 도착 시각(`arr_time < dep_time`이면 +1일)부터 귀국편 출발 시각까지 분.
  - `Candidate(out: MergedLeg, inn: MergedLeg, price: int, stay_min: int)`
  - `in_condition(legs: dict[str, list[MergedLeg]], prefs: Preferences) -> dict[str, list[MergedLeg]]` — 위반 0개 & `best_price` 있는 편만.
  - `pareto_candidates(legs_in_condition: dict[str, list[MergedLeg]], out_date: date, ret_date: date, max_price: int | None, limit: int = 4) -> list[Candidate]` — 모든 조합 중 `max_price` 이하, 가격 오름차순으로 훑으며 체류시간이 지금까지 최대보다 긴 것만 채택. `limit` 초과 시 첫(최저가)·마지막(최장 체류)을 반드시 포함하고 나머지는 가격 기준 균등 간격으로 선택. 가격 오름차순 반환.
  - `cheapest_combo(legs_in_condition: dict[str, list[MergedLeg]], max_price: int | None) -> tuple[MergedLeg, MergedLeg, int] | None`
  - `RtReference(airline_iata: str, rt_min: int, ow_sum: int | None, diff: int | None)` — `diff = ow_sum - rt_min` (양수 = 왕복이 쌈).
  - `rt_reference(snapshots: list[Snapshot], legs: dict[str, list[MergedLeg]], now: datetime, window: timedelta) -> list[RtReference]` — 최신 `ok` roundtrip 스냅샷(W 안)의 항공사별 최저 `total_price` vs 같은 항공사 출국·귀국 `best_price` 합. `rt_min` 오름차순.

- [ ] **Step 1: Write failing tests:**
  - `test_stay_minutes_same_day` — 출국 10/21 도착 16:00, 귀국 10/25 출발 10:30 → `(4*24*60) - 330` = 5430.
  - `test_stay_minutes_overnight_arrival` — 출국 23:40→02:10은 10/22 02:10 도착으로 계산.
  - `test_pareto_frontier` — 조합 (231,000/3일20h), (263,000/4일1h), (250,000/3일10h), (302,000/4일5h) → 250,000은 제외, 나머지 3개 가격순.
  - `test_pareto_limit_keeps_extremes` — 프론티어 7개, `limit=4` → 첫·끝 포함 4개.
  - `test_pareto_respects_max_price`, `test_pareto_empty_when_one_side_filtered_out`.
  - `test_rt_reference_matches_spec_example` — 스펙 §6.4 FUK 값: 제주 rt 360,600 / 편도 합 376,031 → diff 15,431; 에어서울 rt 372,300 / 364,317 → diff −7,983.
  - `test_rt_reference_ignores_stale_roundtrip`.
- [ ] **Step 2: Run** `pytest tests/v2/test_results_combos.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): combos, pareto candidates and round-trip reference`

### Task 9: 도메인 — 추적 값 · 통계 · 알림 판정

**Files:**
- Create: `flight_friend/domain/tracking.py`, `tests/v2/test_tracking.py`

**Interfaces:**
- Consumes: Task 7 `current_legs`, `violations`; Task 8 `in_condition`, `cheapest_combo`; Task 1 `Snapshot`, `Preferences`.
- Produces:
  - `RunValue(run_id: int, observed_at: datetime, combo: int | None, out_min: int | None, in_min: int | None, partial: bool)` — 한 run의 스냅샷만으로(W 무시, run 시점 기준) 조건 내 최저값. `partial` = 그 run에 `ok`가 아닌 oneway 스냅샷이 있음.
  - `run_values(snapshots: list[Snapshot], prefs: Preferences) -> list[RunValue]` — run_id별 그룹, 관측 시각 오름차순. 조합 최대가는 `prefs.max_price`.
  - `DayPoint(day: date, combo: int | None, out_min: int | None, in_min: int | None, partial: bool)` — 하루 최저 (KST 날짜), `partial`은 그날 선택된 최저값의 run이 partial이면 참.
  - `daily_series(values: list[RunValue]) -> list[DayPoint]`
  - `Stats(current: int | None, start: int | None, start_day: date | None, low: int | None, low_day: date | None, median: int | None, days: int, comparable: bool)` — `comparable = days >= MIN_TRACKING_DAYS`; `comparable`이 거짓이면 start/low/median은 `None`.
  - `tracking_stats(series: list[DayPoint], current: int | None) -> Stats` — `current`는 호출자가 Task 7/8로 계산한 W 적용 현재값.
  - `should_alert_new_low(series: list[DayPoint], current: int | None, last_alert_price: int | None) -> bool` — `comparable`, 그리고 `current`가 (오늘 제외 이전 최저) 대비 `ALERT_DROP_PCT` 또는 `ALERT_DROP_KRW` 이상 낮음, 그리고 `last_alert_price`가 있으면 그보다도 같은 임계 이상 낮음.
  - `should_alert_target(current: int | None, target: int | None, last_alert_price: int | None) -> bool` — `current <= target`, 그리고 이전 target 알림이 없거나 그보다 임계 이상 낮음.

- [ ] **Step 1: Write failing tests:**
  - `test_run_values_partial_flag`, `test_run_values_respect_prefs` (시간창 밖 최저 편 제외).
  - `test_daily_series_takes_daily_min` — 같은 날 수동 3회(250k, 240k, 260k) → 240k 1점.
  - `test_stats_not_comparable_under_3_days`, `test_stats_start_low_median` (5일: 312k, 298k, 301k, 274k, 249k → start 312k, low 249k, median 298k).
  - `test_stats_recomputed_with_new_prefs` — 같은 스냅샷, 다른 prefs → 다른 start.
  - `test_new_low_alert_threshold` (이전 최저 250,000: 245,000 → 5,000/2%라 False, 240,000 → True), `test_new_low_not_before_3_days`, `test_new_low_dedup_against_last_alert`, `test_target_alert_once_then_further_drop`.
- [ ] **Step 2: Run** `pytest tests/v2/test_tracking.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): tracking series, stats and alert rules`

### Task 10: search-worker

**Files:**
- Create: `flight_friend/worker.py`, `tests/v2/test_worker.py`

**Interfaces:**
- Consumes: Task 2/3 repo, Task 5 `search_oneway`/`search_roundtrip`, Task 6 schedule, Task 7–9 domain, `flight_monitor.notifier.send_alert(message: str) -> str | None` (V1 모듈 재사용; Task 17에서 이동).
- Produces:
  - `async execute_run(run: Run, trip: Trip, crawler, search_oneway=..., search_roundtrip=...) -> None` — GF oneway out(출국일, ICN→dest), oneway in(귀국일, dest→ICN), roundtrip을 `asyncio.gather`로 동시 실행 → 각각 `save_snapshot(... observed_at=now)` → `finish_run(done)`. 예외 시 `finish_run(error)`. 검색 함수는 인자로 주입(테스트용).
  - `schedule_due_trips(now: datetime) -> int` — `list_trips()` 중 `is_due` 이고 `has_open_run` 아닌 Trip에 `enqueue_run(schedule)`.
  - `evaluate_alerts(trip: Trip, now: datetime, send=send_alert) -> list[str]` — Task 9 규칙으로 new_low/target 판정 → 메시지 전송 → `record_alert`. 반환: 보낸 kind 목록. 메시지: `"[Flight Friend] {destination} {out:%m/%d}→{ret:%m/%d} · 추적 시작 이후 최저 {price:,}원 ({pct:+.0%})"` / 목표가: `"... · 목표가 {target:,}원 이하 진입 {price:,}원"`, 끝에 Trip 경로 `/trips/{id}`.
  - `evaluate_ops(now: datetime, send=send_alert) -> bool` — 최근 3개 run의 GF oneway 스냅샷이 모두 `ok`가 아니면 ops 알림 1회 (마지막 ops 알림 후 6시간 내 재전송 없음).
  - `async main_loop() -> None` — 2초마다 `claim_next_run` → `execute_run`(하나의 `AsyncWebCrawler` 재사용), 60초마다 `expire_stuck_runs(STUCK_RUN_AFTER)`·`schedule_due_trips`·`evaluate_ops`. 각 run 완료 후 `evaluate_alerts`. `if __name__ == "__main__": asyncio.run(main_loop())`.

- [ ] **Step 1: Write failing tests** (fake search 함수 주입, DB 사용):
  - `test_execute_run_saves_three_snapshots` — out/in/roundtrip 각 1개, run `done`.
  - `test_execute_run_partial_failure_still_done` — in이 `error` 결과여도 run `done`, 스냅샷 status 보존.
  - `test_execute_run_exception_marks_error`.
  - `test_schedule_due_trips_skips_open_run_and_off_tracking`.
  - `test_evaluate_alerts_sends_once` — 4일치 스냅샷으로 new_low 조건 충족 → fake send 1회, 즉시 재호출 시 0회.
  - `test_evaluate_ops_after_three_failures`.
- [ ] **Step 2: Run** `pytest tests/v2/test_worker.py -v` → FAIL.
- [ ] **Step 3: Implement.** `main_loop`은 테스트하지 않는다 (얇은 루프).
- [ ] **Step 4: Run** → PASS; 로컬에서 `python -c "import flight_friend.worker"`가 crawl4ai 없이도 import 성공.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): search worker with scheduler and alerts`

### Task 11: API — views · 엔드포인트

**Files:**
- Create: `flight_friend/api/__init__.py`, `flight_friend/api/views.py`, `flight_friend/api/main.py`, `tests/v2/test_api.py`

**Interfaces:**
- Consumes: Task 2/3 repo, Task 6–9 domain.
- Produces — 스펙 §9.4 엔드포인트, 응답 JSON (프론트 Task 12–15의 `types.ts`가 이 형태를 그대로 따른다):
  - `GET /api/trips` → `[{id, destination, out_date, ret_date, days_to_departure, tracking, current, current_observed_at, change_vs_start_pct | null, archived}]`
  - `POST /api/trips` body `{destination, out_date, ret_date, prefs?, target_price?}` → `201 {id, run_id}` (첫 manual run enqueue). 검증: `ret_date > out_date`, `out_date >= today`, destination `^[A-Z]{3}$` → 아니면 422.
  - `GET /api/trips/{id}` → `{trip, run: {id, status, requested_at} | null, providers: [{provider, status, observed_at}], stats: Stats, legs: {out: [MergedLegView], in: [...]}, candidates: [CandidateView], near_miss: NearMissView | null, rt_reference: [RtReference], window_minutes}`; `MergedLegView` = `{flight_key, dep_time, arr_time, airline_name, airline_iata, flight_numbers, stops, duration_min, dep_airport, arr_airport, best_price, best_provider, in_condition, violations, prices: [{provider, price, observed_at, booking_url, stale}]}` — `legs`는 **전체**(조건 밖 포함)이고 `in_condition`/`violations`로 표시한다 (필터 바가 즉시 동작하도록).
  - `PATCH /api/trips/{id}` body `{prefs?, tracking?, target_price? | null}` → 200 갱신된 `GET` 응답.
  - `POST /api/trips/{id}/runs` → `202 {run_id}`; 열린 run이 있으면 그 run_id로 202; 쿨다운 중이면 `429 {retry_after_seconds}`.
  - `GET /api/runs/{id}` → `{id, status, snapshots: [{provider, kind, direction, status}]}`
  - `GET /api/trips/{id}/history` → `[DayPoint]` (조건 적용)
  - `GET /api/admin/runs`, `GET /api/admin/providers?days=7`
  - `GET /healthz` → `{"ok": true}`; 그 외 비-API 경로는 `flight_front/web/dist/index.html` (SPA).
- `views.py`는 FastAPI를 import하지 않는다 (Service 레이어 규칙). `main.py`는 SQL을 쓰지 않는다.

- [ ] **Step 1: Write failing tests** (`fastapi.testclient.TestClient`, 스냅샷은 repo로 직접 주입):
  - `test_create_trip_enqueues_manual_run`, `test_create_trip_validation_422` (귀국일 ≤ 출국일, 과거 날짜, 소문자 코드).
  - `test_trip_view_shape` — 위 키 전부 존재, 조건 밖 편은 `in_condition=false` + `violations` 채워짐.
  - `test_trip_view_all_stale` — W 밖 스냅샷만 있을 때 200, `stats.current is None`, legs의 `best_price is None`, `prices[].stale == true`.
  - `test_patch_prefs_changes_candidates`.
  - `test_manual_run_cooldown_429` 와 `test_manual_run_returns_open_run`.
  - `test_history_daily_points`.
- [ ] **Step 2: Run** `pytest tests/v2/test_api.py -v` → FAIL.
- [ ] **Step 3: Implement.** CI 설치 목록에 `httpx`가 없으면 `requirements.txt`에 `httpx` 추가.
- [ ] **Step 4: Run** `pytest tests/v2 -v` → 전부 PASS; `ruff check .` clean.
- [ ] **Step 5: Commit** (+`log.md`) — `feat(v2): trip API and views`

### Task 12: 프론트 — 앱 셸 · Trip 목록 · 새 Trip

**Files:**
- Modify: `flight_front/web/src/App.tsx`, `flight_front/web/src/api.ts`, `flight_front/web/src/types.ts`, `flight_front/web/src/utils.ts`
- Create: `flight_front/web/src/pages/TripList.tsx`, `flight_front/web/src/pages/NewTrip.tsx`
- Modify: `flight_front/web/vite.config.ts` (dev proxy 대상이 V2 API면 유지)

**Interfaces:**
- Consumes: Task 11 응답 형태.
- Produces: `types.ts`에 `TripSummary`, `TripView`, `MergedLegView`, `ProviderPriceView`, `CandidateView`, `NearMissView`, `RtReference`, `Stats`, `DayPoint`, `RunStatus`, `Preferences` (Task 11 JSON 키 그대로). `api.ts`에 `listTrips()`, `createTrip(input)`, `getTrip(id)`, `patchTrip(id, patch)`, `startRun(id)` (429 → `{cooldownSeconds}` 반환), `getRun(id)`, `getHistory(id)`, `getAdminRuns()`, `getAdminProviders(days)`.
- 라우트: `/` TripList, `/trips/new` NewTrip, `/trips/:id` (Task 13 전까지 placeholder), `/admin` (Task 15). V1 라우트·내비 제거 (V1 컴포넌트 파일 삭제는 Task 17).
- TripList (스펙 §8.1): 추적 중 Trip 출발일순 행 `목적지 · 10/21→10/25 · D-23 · 231,000원 · 2시간 전 · 추적 시작 대비 −12%`; 추적 off·출발 경과는 접힌 섹션; Trip 0개면 NewTrip 폼을 바로 렌더.
- NewTrip: 필수 목적지(IATA 3자리 입력)·출국일·귀국일, 선택 선호 조건(시간창 2개, 직항만, 목표가). 제출 → `createTrip` → `/trips/:id`로 이동.
- `utils.ts`의 `timeAgo`, `formatDuration`, `formatDate` 재사용; `STALE_HOURS`는 제거(서버가 `stale` 제공).

- [ ] **Step 1:** `types.ts`/`api.ts` 작성 후 `cd flight_front/web && npm run build` → tsc 통과.
- [ ] **Step 2:** 페이지·라우팅 구현 → `npm run build` 통과.
- [ ] **Step 3: 수동 확인** — `uvicorn flight_friend.api.main:app` + `npm run dev`로 Trip 생성 → 목록 표시 → 생성 직후 이동 확인. 모바일 폭(390px)에서 가로 스크롤 없음.
- [ ] **Step 4: Commit** (+`log.md`) — `feat(v2-web): app shell, trip list and new trip form`

### Task 13: 프론트 — Trip 화면: 상태 헤더 · 확인 버튼 · 추적 요약 · 차트

**Files:**
- Create: `flight_front/web/src/pages/TripPage.tsx`, `flight_front/web/src/components/trip/StatusHeader.tsx`, `.../TrackingSummary.tsx`, `.../HistoryChart.tsx`
- Modify: `flight_front/web/src/App.tsx` (라우트 연결)

**Interfaces:**
- Consumes: Task 12 `api.ts`/`types.ts`.
- Produces: `TripPage`가 `TripView`를 로드·보관하고 하위 컴포넌트에 props로 전달 (Task 14가 결과 영역을 같은 페이지에 추가).
- StatusHeader (스펙 §4.1-5, §5.3): `마지막 확인 {timeAgo} · Google Flights ✓/✕(사유)`; `지금 확인` 버튼 → `startRun` → 2.5초 간격 `getRun` 폴링, 진행 중엔 기존 결과 유지 + 제공자별 상태 표시, `done/error` 시 `getTrip` 재조회로 **한 번에 교체**. 429면 `방금 확인됨` + 남은 초 동안 비활성. run이 없고 결과도 없으면(첫 검색) 빈 화면에 진행 상태.
- TrackingSummary (스펙 §7.1): `comparable`이면 현재/추적 시작(날짜)/추적 이후 최저(날짜)/중앙값 + 기준 명시 변화율; 아니면 `추적 {days}일째 · 비교 이력 수집 중`. `current`가 null이면 `확인가 없음 (오래된 관측만 있음)`.
- HistoryChart: 기존 `PriceChart`(Recharts) 패턴 재사용, 기본 접힘, 조합/출국/귀국 선 토글, `partial` 점은 속 빈 점.

- [ ] **Step 1:** 구현 → `npm run build` 통과.
- [ ] **Step 2: 수동 확인** — worker 없이 DB에 스냅샷을 넣은 Trip으로 요약·차트 표시; 버튼 → run `queued` 상태 표시 → (worker 실행 시) 완료 후 결과 교체; 5분 내 재클릭 시 쿨다운.
- [ ] **Step 3: Commit** (+`log.md`) — `feat(v2-web): trip status header, run polling and tracking summary`

### Task 14: 프론트 — Trip 화면: 결과 영역

**Files:**
- Create: `flight_front/web/src/components/trip/FilterBar.tsx`, `.../Candidates.tsx`, `.../NearMissHint.tsx`, `.../LegList.tsx`, `.../LegCard.tsx`, `.../SelectionBar.tsx`
- Modify: `flight_front/web/src/pages/TripPage.tsx`

**Interfaces:**
- Consumes: Task 13 `TripPage` 상태(`TripView`), Task 12 `patchTrip`.
- 동작 (스펙 §6, §8.2, §8.3):
  - FilterBar = 선호 조건 편집기. 변경 즉시 `patchTrip` → 응답 `TripView`로 교체 (재검색 없음).
  - Candidates: 2–4개, 첫 카드는 `최저가`, 나머지 `+{Δ가격}원 → 현지 +{Δ시간}`. 카드 클릭 → 두 목록에서 해당 편 선택.
  - NearMissHint: `조건 밖 · {사유 설명} · 조건 내 최저보다 {saving}원 저렴 [보기]` (`saving=0`이면 `조건 하나만 풀면 선택지가 있음`). [보기] → 해당 편이 보이도록 조건 밖 표시 토글.
  - LegList ×2: 데스크톱 2열, 모바일(`< sm`) `출국 | 귀국` 탭. 머리에 `출국편 · {n}개 · {timeAgo} 확인`. 기본은 `in_condition`만, 토글로 전체. 정렬: 가격/출발시각.
  - LegCard: 1단계 시각·가격(크게), 2단계 항공사·직항/소요(경유 주황)·`{best_provider} 외 {n}곳`, `▾`로 3단계(편명·제공자별 가격·관측 시각·예약 링크), stale 가격은 흐리게 `오래됨`. 카드 탭 = 선택, `▾` = 펼침.
  - SelectionBar (하단 고정): `{합계}원 · 현지 {d}일 {h}시간 [출국편 예약 ↗] [귀국편 예약 ↗]` + 해당 항공사 `rt_reference`가 있으면 `이 항공사 왕복으로 사면 총 {rt_min}원부터 (편도 합보다 {diff}원 저렴|비쌈)`.
  - 현지 체류시간 표시는 서버 `CandidateView.stay_min`을 쓰고, 임의 선택 조합은 `utils.ts`에 `stayMinutes(outDate, outArr, outDep, retDate, retDep)` 추가 (자정 넘김 처리, Task 8 규칙과 동일).

- [ ] **Step 1:** 구현 → `npm run build` 통과.
- [ ] **Step 2: 수동 확인** — 스펙 §13 FUK 수준 데이터(출국 46/귀국 40)로: 필터 변경 즉시 반영, 대표 후보 클릭 → 선택 동기화, 모바일 탭 전환, 선택 바 예약 링크가 GF booking URL.
- [ ] **Step 3: Commit** (+`log.md`) — `feat(v2-web): trip results, candidates and selection bar`

### Task 15: 프론트 — /admin

**Files:**
- Create: `flight_front/web/src/pages/Admin.tsx`
- Modify: `flight_front/web/src/App.tsx`

**Interfaces:**
- Consumes: Task 12 `getAdminRuns`, `getAdminProviders`.
- 화면: 최근 run 표(시각·Trip·트리거·상태·스냅샷 상태), 제공자별 일자 성공률(ok/empty/blocked/error). 메인 내비에 노출하지 않음 (URL 직접 접근).

- [ ] **Step 1:** 구현 → `npm run build` 통과. **Step 2: 수동 확인.**
- [ ] **Step 3: Commit** (+`log.md`) — `feat(v2-web): admin runs and provider health`

### Task 16: 배포 연결 · 문서

**Files:**
- Modify: `docker-compose.yml` (새 서비스 `worker`: `Dockerfile.collector` 빌드, `command: python -u -m flight_friend.worker`, `restart: unless-stopped`, `profiles: [full]`, db healthy 의존), `Dockerfile` (CMD → `flight_friend.api.main:app`), `.github/workflows/ci.yml` (`pip install ... pytest httpx` 확인), `.github/workflows/deploy.yml` (worker 빌드·기동 추가, collector 빌드 단계 제거), `AGENTS.md` (V2 기준 재작성: 레이어 표에 `flight_friend/*`, V2 테이블 역할표, 어댑터 인터페이스, 금지사항 — V1 전용 항목 제거), `tests/test_architecture.py` (V2 규칙 추가: `flight_friend/api/views.py`·`domain/*`는 fastapi import 금지, `api/main.py`는 `providers` import 금지, `domain/*`는 `db`/`repo` import 금지)
- Modify: `log.md` "현재 상태"

**Interfaces:**
- Consumes: 전 task.

- [ ] **Step 1: Write failing tests** — `tests/test_architecture.py`에 V2 규칙 3개 추가 → 위반 없는 현재 코드에서 PASS해야 하므로, 먼저 일부러 위반 import를 넣은 임시 파일로 FAIL 확인 후 제거.
- [ ] **Step 2: Run** `pytest tests/ -v` (V1+V2 전체) → PASS; `ruff check .` clean; `cd flight_front/web && npm run build` 통과.
- [ ] **Step 3:** `docker compose --profile full config`로 compose 문법 확인.
- [ ] **Step 4: 호스트 crontab 안내** — V1 수집 cron과 spike cron 제거는 사용자가 수행 (서버 작업). `log.md`에 명시.
- [ ] **Step 5: Commit** (+`log.md`) — `chore(v2): wire worker service, deploy and AGENTS.md for V2`

### Task 17: V1 은퇴 (게이트: 사용자 확인 후에만)

> M1 완료 기준(스펙 §11: 실제 Trip 1개 이상 며칠간 자동 추적 + 수동 확인 + 예약 이동)을 **사용자가 확인한 뒤에만** 시작한다. 태그 push와 DB 스키마 이동은 되돌리기 어려우므로 각 단계 전에 사용자 승인을 받는다.

**Files:**
- Create: `scripts/v1_freeze.sql` — V1 테이블을 `v1` 스키마로 `ALTER TABLE ... SET SCHEMA v1` (`raw_legs`, `flight_legs`, `price_events`, `price_history`, `deals`, `collection_runs`, `alert_state`, `airports`, `app_config`), 트리거 함수 포함. 실행 전 `pg_dump` 백업 명령을 파일 상단 주석에.
- Delete: `main.py`, `diagnosis_agent.py`, `mcp_server.py`, `Dockerfile.mcp`, `scripts/collect_and_diagnose.sh`, `scripts/repopulate_deals.py`, `scripts/diagnose_*`, `scripts/bench_gf_resource_block.py`, `flight_monitor/` (단 `notifier.py`는 `flight_friend/notifier.py`로 이동하고 import 갱신), `flight_front/api/`, V1 React 컴포넌트, V1 테스트(`tests/test_*.py` 중 V1 대상), docker-compose `collector`·`mcp` 서비스, `ISSUES.md`/`TODOS.md`의 V1 항목(정리 후 V2 기준으로 갱신).
- Modify: `tests/test_architecture.py` (V1 경로 제거), `CLAUDE.md` 포트폴리오 섹션은 사용자에게 갱신 여부를 묻는다.

- [ ] **Step 1:** 사용자 승인 후 `git tag v1-final <V2 시작 직전 커밋>` → push는 사용자 승인 시에만.
- [ ] **Step 2:** `notifier.py` 이동 + import 갱신 → `pytest tests/ -v` PASS.
- [ ] **Step 3:** V1 파일 삭제 → `pytest tests/ -v`, `ruff check .`, `npm run build` 모두 통과.
- [ ] **Step 4:** `scripts/v1_freeze.sql` 작성 (실행은 사용자가 서버에서, 백업 후).
- [ ] **Step 5: Commit** (+`log.md`) — `chore: retire V1 code (tagged v1-final)`

---

## 범위 밖 (별도 계획)

- **Naver spike / M2 Naver 어댑터** — 스펙 §11. spike 결과로 별도 계획을 쓴다. M1 코드는 `provider` 문자열과 제공자별 가격 목록을 이미 다중 제공자 전제로 다룬다.
- 왕복 2단계 확장, 관심 항공편 고정, 다중 목적지 Trip, V1 참고 이력, 하루 요약 알림 (스펙 §11 "이후 후보").
- 잠정 상수(갱신 주기·W) 확정 — OCI 반복 측정 결과가 오면 `flight_friend/config.py`/`domain/schedule.py` 값만 바꾼다.
