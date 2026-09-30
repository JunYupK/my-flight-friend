# Flight Friend M2 — Naver 제공자 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Naver를 두 번째 제공자로 붙여 GF와 항공편 단위로 가격을 비교하고, 조건부(카드) 요금을 함께 보여준다.

**Architecture:** `providers/naver.py`가 Naver 내부 API(`searchFlights`, SSE)를 httpx로 직접 호출해 M1과 같은 `ProviderResult`를 돌려준다. 조건부 요금은 기존 견적 행의 `cond_*` 칸에 저장하고, 병합은 `flight_key` 1차 + 편명 2차 매칭으로 확장한다. 추적·알림·후보 계산은 조건 없는 `price` 그대로다.

**Tech Stack:** Python 3.11, httpx(이미 requirements), psycopg2, FastAPI, React+TS.

**Spec:** `docs/superpowers/specs/2026-09-30-flight-friend-m2-naver-design.md` (상위: `2026-09-28-flight-friend-v2-design.md` §13.1)

## Global Constraints

- 테스트는 실제 Naver/GF를 호출하지 않는다 — `httpx.MockTransport`와 `tests/fixtures/naver_*.sse`만 쓴다.
- `snapshots`/`leg_quotes`/`rt_quotes`는 append-only. 스키마 변경은 `init_schema()`의 `ADD COLUMN IF NOT EXISTS`.
- 계산 기준 가격은 조건 없는 `price`(Naver는 `A01` 최저). `cond_*`는 표시·참고용.
- 레이어 규칙(`tests/test_architecture.py`): providers/domain/views/db/repo는 fastapi 금지, domain은 db/repo 금지, api/main은 providers 금지.
- Naver 요청 헤더: `content-type: application/json`, `accept: text/event-stream`, `origin: https://flight.naver.com`, `referer: https://flight.naver.com/`, `accept-language: ko-KR`, `user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36`.
- 타임아웃: 편도 45초, 왕복 60초 (`config.py`).
- 린트는 `python -m ruff check .` (CI와 같은 ruff 0.16.9). 테스트는 `DATABASE_URL=postgresql://flight_user:flight_pass@localhost:5432/flights python -m pytest tests/ -q`.
- 각 task 끝에 `log.md`에 항목 추가 (AGENTS/log.md 형식).

## Review Focus

1. Naver `flightNumber`가 숫자만이 아닐 때(예: `"0080A"`, `""`) 파서가 죽지 않고 앞의 0만 떼어 `"XX 80A"`로 만든다 — Task 3 테스트.
2. 스트림이 완료 전에 끊겨 마지막 줄이 `isCompleted: false`여도 항공편이 있으면 `ok` + `error="partners 3/20"` — Task 3 테스트.
3. GF 쪽에 같은 편명의 견적이 시각만 다르게 2건 있고 Naver가 1건일 때, 셋이 한 묶음이 되고 제공자별 가격은 제공자마다 최저 1건 — Task 5 테스트.
4. 기존(M1) 행은 `cond_*`가 NULL — 로드가 `None`으로 복원되고 병합·뷰가 깨지지 않는다 — Task 2 테스트.
5. Naver 스냅샷이 오래됐고(stale) GF만 신선할 때 `best_cond`는 비어야 한다 (오래된 조건부 가격을 최저로 보이지 않게) — Task 5 테스트.

---

### Task 1: OCI 게이트 — Naver API 동작 확인 (사용자 작업)

**Files:** `log.md`만.

- [ ] **Step 1:** 사용자에게 OCI 서버에서 아래 실행을 요청하고 결과를 받는다.

```bash
cd ~/my-flight-friend && git fetch origin claude/dazzling-shannon-4x04v7
git show origin/claude/dazzling-shannon-4x04v7:scripts/naver_spike.py > naver_spike.py
docker compose --profile full run --rm -v ./naver_spike.py:/app/naver_spike.py worker \
  python naver_spike.py --dep ICN --arr FUK --date <30일 뒤 YYYY-MM-DD>
```

Expected: 첫 줄 `http 201 … error -`, 둘째 줄 `completed True  partners 20/20 …`.

- [ ] **Step 2:** 결과를 `log.md`에 기록. **`http 403/429`, HTML, 타임아웃이면 여기서 멈추고** 사용자와 브라우저 재시도 방식(설계 D7 재논의)을 정한다. 통과하면 Task 2로.

---

### Task 2: 조건부 가격 칸 — 타입·스키마·repo

**Files:**
- Modify: `flight_friend/types.py` (`LegQuote`, `RtQuote`)
- Modify: `flight_friend/db.py` (`init_schema`)
- Modify: `flight_friend/repo.py` (`save_snapshot`, `_row_to_leg`, `_row_to_rt`, `record_alert`)
- Test: `tests/test_db.py`, `tests/test_repo_snapshots.py`

**Interfaces:**
- Produces: `LegQuote.cond_price: int | None = None`, `LegQuote.cond_label: str | None = None`, `LegQuote.cond_booking_url: str | None = None`; `RtQuote.cond_total_price: int | None = None`, `RtQuote.cond_label: str | None = None` (모두 필드 끝에, 기본값 None). `repo.record_alert(trip_id: int | None, kind: str, price: int | None)` — kind 타입을 `str`로 넓힘 (Task 7이 `"ops:naver"` 사용).

- [ ] **Step 1: 실패 테스트**
  - `test_db.py::test_cond_columns_exist` — `information_schema.columns`에 `leg_quotes.cond_price/cond_label/cond_booking_url`, `rt_quotes.cond_total_price/cond_label` 존재.
  - `test_repo_snapshots.py::test_cond_fields_roundtrip` — `cond_price=161700, cond_label="하나카드(이용실적 충족시)", cond_booking_url="https://x"`인 LegQuote와 `cond_total_price=299000, cond_label="하나카드(이용실적 충족시)"`인 RtQuote를 저장 후 `load_snapshots`로 같은 값 복원.
  - `test_repo_snapshots.py::test_cond_fields_default_none` — cond 칸을 안 준 LegQuote/RtQuote(M1 형태)가 `None`으로 복원 (Review Focus 4).
- [ ] **Step 2:** `pytest tests/test_db.py tests/test_repo_snapshots.py -q` → 새 테스트 FAIL.
- [ ] **Step 3:** 구현 — 데이터클래스 필드, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 5개, INSERT/SELECT 매핑, `record_alert` kind 타입.
- [ ] **Step 4:** 전체 `pytest tests/ -q` PASS, `python -m ruff check .` 통과.
- [ ] **Step 5: Commit** `feat(m2): conditional price columns on quotes` (+ log.md)

---

### Task 3: Naver provider — 편도

**Files:**
- Create: `flight_friend/providers/naver.py`
- Modify: `flight_friend/config.py` (`NAVER_ONEWAY_TIMEOUT: float = 45.0`, `NAVER_ROUNDTRIP_TIMEOUT: float = 60.0`)
- Test: `tests/test_naver.py` (fixture: `tests/fixtures/naver_oneway_icn_fuk.sse` — 이미 커밋됨)

**Interfaces:**
- Consumes: Task 2의 `LegQuote` cond 칸, `providers.airlines.flight_key(date_, dep, arr, dep_time, arr_time, stops, airline) -> str`.
- Produces:
  - `PROVIDER = "naver"`
  - `API_URL = "https://flight-api.naver.com/flight/international/searchFlights"`
  - `async def search_oneway(client: httpx.AsyncClient, dep: str, arr: str, date_: date) -> ProviderResult`
  - `def build_booking_url(dep: str, arr: str, date_: date, itinerary_id: str, fare_type: str, airline: str) -> str`
  - `def build_search_url(dep: str, arr: str, date_: date) -> str`
  - 내부 공용(Task 4 재사용): `_post_search(client, body: dict, timeout: float) -> tuple[status, dict | None, str | None]` (상태 판정 포함), `_itinerary_ok(segments, dep, arr) -> bool`, `_fares(fares, fare_type_map) -> tuple[int | None, int | None, str | None, str | None]` = (A01 최저, 더 싼 조건부 최저 또는 None, 조건 라벨, 조건 fareType)

- [ ] **Step 1: 실패 테스트** (`tests/test_naver.py`, `httpx.MockTransport`로 fixture 본문을 `201`, `content-type: text/event-stream`으로 반환)
  - `test_oneway_parses_final_snapshot` — 결과 `status == "ok"`, `error is None`, legs 8개 (첫 `data:` 줄의 부분 스냅샷 2건이 아니라 마지막 줄 기준).
  - `test_oneway_drops_codeshare` — 편명 `"KE 5481"`(운항 OZ) 없음.
  - `test_oneway_leg_fields` — 가격 오름차순 첫 leg: `flight_key == "2026-11-12|ICN|FUK|18:15|19:35|0|ZE"`, `flight_numbers == ["ZE 649"]`, `airline_name == "이스타항공"`, `duration_min == 80`, `price == 141947`, `cond_price == 139934`, `cond_label == "현대 M2/M3 Edition2(이용실적 충족시)"`.
  - `test_oneway_cond_only_when_cheaper` — `7C 1407` leg: `price == 151700`, `cond_price is None`, `cond_label is None`, `cond_booking_url is None`.
  - `test_oneway_connection_and_same_fare` — `UO 627/UO 600` leg: `stops == 1`, `duration_min == 845`, `price == 514758`, `cond_price is None`; `sameFareMappings`의 `["UO 627", "UO 668"]` leg도 존재.
  - `test_booking_urls` — `RS 433` leg: `booking_url`이 `https://flight.naver.com/flights/international/detail/ICN:airport-FUK:airport-20261112?adult=1&isDirect=false&fareType=Y&selectType=concurrent&selectedFlight=`로 시작하고 `urllib.parse.unquote` 후 `1:20261112ICNFUKRS0433:A01:HK:RS:`로 끝남; `cond_booking_url`은 `...:A01/B16:HK:RS:`로 끝남; `search_url == build_search_url("ICN","FUK",date(2026,11,12)) == "https://flight.naver.com/flights/international/ICN:airport-FUK:airport-20261112?adult=1&isDirect=false&fareType=Y&tripType=OW"`.
  - `test_request_body_and_headers` — MockTransport가 받은 요청: POST `API_URL`, 본문 `tripType == "OW"`, `itineraries[0] == {"departureLocationCode":"ICN","arrivalLocationCode":"FUK","departureLocationType":"airport","arrivalLocationType":"airport","departureDate":"20261112"}`, 헤더 `accept == "text/event-stream"`, `user-agent`는 Global Constraints 값.
  - `test_status_table` (parametrize) — 403 → `blocked`/`error == "http 403"`; 429 → `blocked`; 200 `text/html` 본문 `<html>` → `blocked`/`"non-json response"`; 500 → `error`; transport가 `httpx.ConnectTimeout` 발생 → `error`; 완료 스냅샷에 fareMappings 0개 → `empty`.
  - `test_partial_stream_ok_with_partner_note` — 첫 `data:` 줄만 보낸 스트림(`isCompleted: false`, 3/20) → `ok`, legs 2개, `error == "partners 3/20"` (Review Focus 2).
  - `test_flight_number_not_numeric` — fixture를 로드해 한 구간 `flightNumber`를 `"0080A"`로 바꾼 본문 → 해당 leg `flight_numbers[0].endswith(" 80A")`, 예외 없음 (Review Focus 1).
- [ ] **Step 2:** `pytest tests/test_naver.py -q` → FAIL (모듈 없음).
- [ ] **Step 3:** 구현. 규칙은 스펙 §3.1·3.2·3.4 그대로:
  - SSE는 `data:`로 시작하는 줄 중 **마지막**을 JSON 파싱. 본문이 비었거나 `data:` 줄이 없으면 `blocked`/`"non-json response"`.
  - 편명은 `f"{code} {num.lstrip('0') or '0'}"`.
  - `cond_label`은 `fareTypesCodeMap[ft]["name"]`에서 앞의 `"성인/"` 제거, 맵에 없으면 `ft`.
  - 같은 `flight_key`는 `price` 최저 1건, 결과는 `price` 오름차순.
  - `seconds`는 `time.perf_counter()` 경과.
- [ ] **Step 4:** `pytest tests/ -q` PASS (아키텍처 테스트가 `providers/naver.py`의 fastapi 금지 검사 포함), ruff 통과.
- [ ] **Step 5: Commit** `feat(m2): naver provider oneway` (+ log.md)

---

### Task 4: Naver provider — 왕복

**Files:**
- Modify: `flight_friend/providers/naver.py`
- Test: `tests/test_naver.py` (fixture: `tests/fixtures/naver_roundtrip_icn_fuk.sse` — 이미 커밋됨)

**Interfaces:**
- Consumes: Task 3 내부 공용 함수, Task 2 `RtQuote` cond 칸.
- Produces: `async def search_roundtrip(client: httpx.AsyncClient, dep: str, arr: str, out_date: date, ret_date: date) -> ProviderResult` (legs 빈 리스트, rts 채움).

- [ ] **Step 1: 실패 테스트**
  - `test_roundtrip_parses_pairs` — `status == "ok"`, rts 5개(운항 OZ인 `KE5481` 가는편 조합 제외), `total_price` 오름차순.
  - `test_roundtrip_fields` — 첫 rt: `airline_iata == "TW"`, `out_flight_key == "2026-11-12|ICN|FUK|17:50|19:20|0|TW"`, `total_price == 303485`, `cond_total_price is None`(같은 가격). `RS` rt: `total_price == 311165`, `cond_total_price == 299000`, `cond_label == "하나카드(이용실적 충족시)"`.
  - `test_roundtrip_request_body` — `tripType == "RT"`, 여정 2개(두 번째 `FUK→ICN`, `"20261116"`), 타임아웃은 `NAVER_ROUNDTRIP_TIMEOUT`.
- [ ] **Step 2:** FAIL 확인.
- [ ] **Step 3:** 구현 — `itineraryIds.split("-")` → (가는편, 오는편) id, 두 쪽 모두 `_itinerary_ok`(코드셰어·공항·시각). 오는 편 검증은 `arr → dep` 방향.
- [ ] **Step 4:** `pytest tests/ -q` PASS, ruff 통과.
- [ ] **Step 5: Commit** `feat(m2): naver provider roundtrip` (+ log.md)

---

### Task 5: 병합 — 편명 보조 매칭과 조건부 최저가

**Files:**
- Modify: `flight_friend/domain/results.py` (`ProviderPrice`, `MergedLeg`, 신규 `CondPrice`, `_merge`)
- Test: `tests/test_results_legs.py`

**Interfaces:**
- Consumes: Task 2 `LegQuote.cond_*`.
- Produces:
  - `@dataclass class CondPrice: price: int; label: str; provider: str; booking_url: str | None`
  - `ProviderPrice`에 `cond_price: int | None = None`, `cond_label: str | None = None`, `cond_booking_url: str | None = None` (끝에 추가)
  - `MergedLeg.best_cond: CondPrice | None = None` (끝에 추가)
  - `current_legs(...)` 시그니처 불변.

- [ ] **Step 1: 실패 테스트** (GF 스냅샷 provider `"google_flights"`, Naver `"naver"`)
  - `test_merge_by_flight_number_when_times_differ` — GF `RS 433` 07:20→09:00 171,700 / Naver `RS 433` 07:20→09:01 171,000 → out 묶음 1개, `leg.arr_time == "09:00"`(GF 대표), `flight_key`는 GF 키, `best_price == 171000`, `best_provider == "naver"`, `prices` 2건.
  - `test_no_number_match_when_flight_numbers_empty` — 두 견적 모두 `flight_numbers=[]`, 키 다름 → 묶음 2개.
  - `test_same_provider_deduped_in_group` — GF `RS 433` 09:00(171,700)과 09:02(170,000) + Naver `RS 433` 09:01 → 묶음 1개, `prices`의 GF 항목 1건(`price == 170000`) (Review Focus 3). 대표 `leg`는 GF 중 최저(09:02).
  - `test_best_cond_only_when_cheaper` — Naver `price=171000, cond_price=161700, cond_label="하나카드(이용실적 충족시)"` → `best_cond == CondPrice(161700, "하나카드(이용실적 충족시)", "naver", <cond_booking_url>)`. GF 최저가가 160,000이면 `best_cond is None`.
  - `test_best_cond_ignores_stale` — Naver 스냅샷이 window 밖(stale), GF 신선 → `best_cond is None`, `best_price`는 GF (Review Focus 5).
- [ ] **Step 2:** FAIL 확인.
- [ ] **Step 3:** 구현 — 1차 `flight_key` 묶음 → 2차 `(date, dep_airport, arr_airport, tuple(flight_numbers))` 같은 묶음 union(편명 비면 불참; date는 `flight_key.split("|")[0]`). 대표: GF 견적 중 `price` 최저, 없으면 전체 최저. 제공자별 최저 1건으로 `prices` 구성(정렬 기존 규칙). `best_*`는 기존 규칙, `best_cond`는 신선한 `prices` 중 `cond_price` 최저 < `best_price`일 때.
- [ ] **Step 4:** `pytest tests/ -q` PASS (M1 병합·추적·후보 테스트 무변경 통과), ruff 통과.
- [ ] **Step 5: Commit** `feat(m2): flight-number secondary matching and conditional best price` (+ log.md)

---

### Task 6: 왕복 참고가 조건부·제공자 + API 뷰

**Files:**
- Modify: `flight_friend/domain/results.py` (`RtReference`, `rt_reference`)
- Modify: `flight_friend/api/views.py` (`_leg_view`, `_rt_view`)
- Test: `tests/test_results_combos.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: Task 5 `MergedLeg.best_cond`, `ProviderPrice.cond_*`; Task 2 `RtQuote.cond_*`.
- Produces:
  - `RtReference`에 `rt_provider: str`, `cond_rt_min: int | None = None`, `cond_label: str | None = None` (`rt_provider`는 `rt_min`을 낸 제공자; 동가면 provider 이름 오름차순 첫 번째). 필드 순서: `airline_iata, rt_min, ow_sum, diff, rt_provider, cond_rt_min, cond_label`.
  - JSON: 편도 항목 `best_cond: {price, label, provider, booking_url} | null`; `prices[]` 항목에 `cond_price`, `cond_label`, `cond_booking_url`; `rt_reference[]` 항목에 `rt_provider`, `cond_rt_min`, `cond_label`.

- [ ] **Step 1: 실패 테스트**
  - `test_rt_reference_takes_cheaper_provider` — 같은 항공사 GF 왕복 320,000 / Naver 311,165 → `rt_min == 311165`, `rt_provider == "naver"`.
  - `test_rt_reference_cond_only_when_cheaper` — Naver `cond_total_price=299000` → `cond_rt_min == 299000`, `cond_label` 전달; `cond_total_price`가 `rt_min` 이상이면 `None`.
  - `test_api.py::test_trip_view_exposes_cond_fields` — GF+Naver 스냅샷을 심고 `GET /api/trips/{id}` → 편도 항목에 `best_cond`(dict 또는 null), `prices[i]`에 `cond_*` 키, `rt_reference[i]`에 `rt_provider` 키.
- [ ] **Step 2:** FAIL 확인.
- [ ] **Step 3:** 구현. 기존 JSON 키 이름·의미는 유지.
- [ ] **Step 4:** `pytest tests/ -q` PASS, ruff 통과.
- [ ] **Step 5: Commit** `feat(m2): roundtrip reference per provider and conditional fields in API` (+ log.md)

---

### Task 7: worker — 다중 제공자 실행, 제공자별 운영 알림

**Files:**
- Modify: `flight_friend/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: Task 3·4 `naver.search_oneway/search_roundtrip(client, ...)`, GF `google_flights.search_oneway/search_roundtrip(crawler, ...)`, Task 2 `repo.record_alert(kind: str)`, Task 5 `MergedLeg.best_cond`.
- Produces:
  - `@dataclass(frozen=True) class ProviderSpec: name: str; oneway: Callable[[str, str, date], Awaitable[ProviderResult]]; roundtrip: Callable[[str, str, date, date], Awaitable[ProviderResult]]`
  - `async def execute_run(run: Run, trip: Trip, providers: list[ProviderSpec]) -> None`
  - `async def run_with_timeout(run: Run, trip: Trip, providers: list[ProviderSpec], timeout: timedelta = RUN_TIMEOUT) -> bool` (시간 초과면 True — 기존 의미)
  - `PROVIDER_LABELS = {"google_flights": "Google Flights", "naver": "Naver"}`
  - `def evaluate_ops(now: datetime, send: Sender = send_alert, providers: tuple[str, ...] = ("google_flights", "naver")) -> list[str]` (알림 보낸 제공자 이름 목록)

- [ ] **Step 1: 테스트 변경·추가** (기존 `fake_searches`/`run_execute` 헬퍼를 `ProviderSpec` 기반으로 바꾼다)
  - `test_execute_run_saves_six_snapshots` — 제공자 2개 → 스냅샷 6개 `(provider, kind, direction)` = 각 제공자 `("oneway","out")`, `("oneway","in")`, `("roundtrip", None)`, run `done`.
  - `test_provider_exception_becomes_error_snapshot` — naver oneway가 예외 → naver out 스냅샷 `status == "error"`, `error`에 예외 메시지, GF 스냅샷 3개 `ok`, run `done`. (기존 `test_execute_run_exception_marks_error`는 이 동작으로 대체 — 설계 §7.1)
  - `test_execute_run_missing_trip_marks_error` — 유지(시그니처만 갱신).
  - `test_run_with_timeout_*` 2개 — 유지(시그니처만 갱신).
  - `test_evaluate_ops_per_provider` — 최근 끝난 run 3개에서 naver 편도만 전부 비-ok, GF는 ok → 반환 `["naver"]`, 메시지 `"[Flight Friend] Naver 최근 3회 검색 연속 실패 — /admin 확인"`, `alerts.kind == "ops:naver"`; 곧바로 다시 호출 → `[]`(쿨다운). GF도 3회 실패로 바꾸면 → `["google_flights"]`(naver 쿨다운과 독립).
  - 기존 `evaluate_ops` 테스트 4개 — 반환형(`list[str]`)과 제공자 인자에 맞게 갱신, 판정 규칙(끝난 run 3건, error run+스냅샷 없음=실패, done run+스냅샷 없음=판정 불가) 유지.
  - `test_alert_message_mentions_cond_total` — 최저 조합 두 편 중 하나에 `best_cond`(161,700, 조건 "하나카드(이용실적 충족시)")가 있으면 메시지에 `카드 조건 시 {합계:,}원 (하나카드(이용실적 충족시) 등)` 포함; 합계 = 각 편 `min(best_cond.price, best_price)`의 합. 없으면 그 문구 없음.
- [ ] **Step 2:** FAIL 확인.
- [ ] **Step 3:** 구현.
  - `execute_run`: 제공자마다 3건, 전부 `asyncio.gather`. 각 호출을 감싸 예외를 `ProviderResult(status="error", legs=[], rts=[], error=str(e), seconds=0.0)`로 바꾼 뒤 저장. trip 없음만 run `error`.
  - `main_loop`: 시작 시 `httpx.AsyncClient()` 열고 `finally`에서 `aclose()`. 매 run마다 현재 crawler로 `ProviderSpec("google_flights", partial(google_flights.search_oneway, crawler), partial(google_flights.search_roundtrip, crawler))`와 `ProviderSpec("naver", partial(naver.search_oneway, client), partial(naver.search_roundtrip, client))`를 만든다.
  - `evaluate_ops`: 제공자별로 기존 판정 → 쿨다운은 `repo.last_alert(None, f"ops:{name}")`, 기록 `repo.record_alert(None, f"ops:{name}", None)`. 모듈 상수 `PROVIDER`/`OPS_MESSAGE` 제거.
- [ ] **Step 4:** `pytest tests/ -q` PASS, ruff 통과, `python -c "import flight_friend.worker"`(crawl4ai 없이) 성공.
- [ ] **Step 5: Commit** `feat(m2): run google flights and naver together, per-provider ops alerts` (+ log.md)

---

### Task 8: 화면 — 조건부 가격 표시, 상세 기본 펼침

**Files:**
- Modify: `flight_front/web/src/types.ts`, `components/trip/LegCard.tsx`, `components/trip/SelectionBar.tsx`, `components/trip/providers.ts`(표시명에 `naver: "Naver"`가 없으면 추가)
- Test: `npm run build` + 브라우저 확인

**Interfaces:**
- Consumes: Task 6 JSON 키.
- Produces: `types.ts` — `CondPriceView { price: number; label: string; provider: string; booking_url: string | null }`, `MergedLegView.best_cond: CondPriceView | null`, `ProviderPriceView`에 `cond_price: number | null; cond_label: string | null; cond_booking_url: string | null`, `RtReference`에 `rt_provider: string; cond_rt_min: number | null; cond_label: string | null`.

- [ ] **Step 1:** `types.ts` 갱신 → `npm run build`가 사용처 타입 오류 없이 통과하는지 확인.
- [ ] **Step 2: `LegCard`**
  - 상세 영역 `useState(true)` (기본 펼침). 토글 버튼을 크게: 최소 `h-8 px-3 text-base`, 라벨 `상세 ▴`/`상세 ▾`.
  - `best_cond`가 있으면 가격 아래 한 줄 `카드 조건 시 {formatWon(price)}` (apple-blue 계열 작은 글씨).
  - 제공자 줄의 링크 문구: `naver`면 `판매사 선택 ↗`, 그 외 `예약 ↗`. `cond_price`가 있으면 들여 쓴 줄 `└ {cond_label} {formatWon(cond_price)}` + `cond_booking_url` 링크 `판매사 선택 ↗`.
- [ ] **Step 3: `SelectionBar`**
  - 두 편 중 하나라도 `best_cond`가 있으면 `카드 조건 적용 시 최저 합계 {formatWon(Σ min(best_cond?.price ?? best_price, best_price))}` 한 줄 + 작은 글씨 `편마다 카드 조건이 다를 수 있어요`.
  - 왕복 참고 문구에 제공자: `이 항공사 왕복으로 사면 총 {rt_min}부터 ({providerLabel(rt_provider)})`; `cond_rt_min`이 있으면 `· 카드 조건 시 {cond_rt_min}`.
- [ ] **Step 4:** `npm run build` 통과. 로컬 API + 시드(GF·Naver 스냅샷, 조건부 있음/없음)로 헤드리스 브라우저 확인: 상세 기본 펼침, 조건부 줄과 링크, 선택 바 합계 줄, 390px 가로 스크롤 없음. 확인한 것과 코드로만 본 것을 log.md에 구분해 기록.
- [ ] **Step 5: Commit** `feat(m2-web): conditional prices, naver seller links, details open by default` (+ log.md)

---

### Task 9: 마무리 — spike 스크립트 삭제, 문서

**Files:**
- Delete: `scripts/naver_spike.py`
- Modify: `AGENTS.md` (§1 데이터 소스에 Naver: 내부 API `searchFlights` 직접 호출·SSE·쿠키 불필요·데스크톱 UA; §2 Providers 행에 `naver.py`; §9 운영 알림이 제공자별 `ops:{provider}`), `TODOS.md` (M2 항목 제거, "OCI Naver 차단 시 브라우저 재시도" 후보 추가), `log.md` (현재 상태 갱신)

- [ ] **Step 1:** 파일 삭제·문서 갱신.
- [ ] **Step 2:** `pytest tests/ -q`, `python -m ruff check .`, `npm run build` 모두 통과.
- [ ] **Step 3: Commit** `docs(m2): retire naver spike script, update AGENTS/TODOS/log`
