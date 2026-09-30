# Flight Friend M2 — Naver 제공자 설계

- 작성일: 2026-09-30
- 상위 설계: `docs/superpowers/specs/2026-09-28-flight-friend-v2-design.md` (§11 마일스톤 M2, §13.1 Naver spike)
- 상태: 합의 완료, 구현 계획 대기

## 1. 목표와 성공 기준

Naver를 두 번째 제공자로 붙여, 같은 Trip 검색에서 Google Flights(GF)와 Naver의 가격을 **항공편 단위로 비교**한다.

성공 기준:

1. 한 번의 run에서 GF 3건 + Naver 3건(편도 출국·귀국, 왕복) 스냅샷이 저장된다.
2. 같은 항공편의 GF·Naver 견적이 한 카드로 합쳐진다 (spike 기준 GF 편도 40/40 일치).
3. 카드에서 조건 없는 최저가와, 더 싼 조건부(카드 실적 등) 가격을 함께 보고, 각 가격의 판매사 선택 페이지로 이동할 수 있다.
4. Naver가 실패해도 GF 결과는 그대로 쓰이고, 연속 실패는 운영 알림으로 드러난다.
5. 추적·알림·대표 후보 계산은 조건 없는 가격 기준으로 유지된다 (M1 동작 불변).

범위 밖: 판매처별 요금 전체 저장, "내 카드만 인정" 설정, 브라우저 기반 Naver 수집(OCI에서 API가 막힐 때만 재논의), 프론트엔드 대개편(별도 예정 — 이번 화면 변경은 최소한으로).

## 2. 결정 사항 요약

| # | 결정 | 근거 |
|---|---|---|
| D1 | 가격은 두 가지를 보관·표시: 조건 없는 최저가(`A01`) + 더 싼 조건부 최저가(`A01/Bxx`, 조건 이름 포함) | 사용자 결정 |
| D2 | 추적 그래프·알림·파레토 후보·조건 밖 제안은 **조건 없는 가격 기준**. 조건부는 표시만 | 이력 정합성. 카드 프로모션에 흔들리지 않음 |
| D3 | 코드셰어는 버리고 실제 운항사 편만 남김 | 같은 항공편 중복 제거 |
| D4 | 편명 보조 매칭: `flight_key`가 달라도 날짜·공항·편명이 같으면 같은 항공편 | spike에서 도착 시각 1분 흔들림 관측. 정합성 우선 |
| D5 | 매칭 후 시각이 다르면 **조용히 합침** — 대표 시각은 GF 우선, GF가 없으면 Naver | 사용자 결정 |
| D6 | Naver 왕복도 수집해 왕복 참고가에 반영 | 사용자 결정 |
| D7 | Naver는 내부 API 직접 호출만. 막히면 실패로 드러내고 운영 알림 | 단순함. OCI 확인을 첫 단계로 |
| D8 | 조건부 요금은 기존 견적 행에 칸을 추가해 저장 (새 테이블 없음) | 변경 최소, M1 로직 불변 |
| D9 | Naver 예약 링크 = 판매사 선택 페이지 딥링크 (fareType별) | spike에서 동작 확인 |

## 3. 수집 — `flight_friend/providers/naver.py`

### 3.1 호출

- 엔드포인트: `POST https://flight-api.naver.com/flight/international/searchFlights`
- 헤더: `content-type: application/json`, `accept: text/event-stream`, `origin: https://flight.naver.com`, `referer: https://flight.naver.com/`, `accept-language: ko-KR`, 데스크톱 Chrome `user-agent`. 쿠키·토큰 없음.
- 본문: spike의 `scripts/naver_spike.py` `body()`와 같은 형태. `departureLocationType`/`arrivalLocationType`은 `"airport"` (GMP 제외). 편도는 `tripType: "OW"` + 여정 1개, 왕복은 `"RT"` + 여정 2개.
- 응답: SSE `data: {...}` 줄들. **마지막 줄**이 누적 스냅샷이므로 그것만 사용한다.
- 공개 함수 (M1과 같은 `ProviderResult` 반환):
  - `async search_oneway(client, dep, arr, date_) -> ProviderResult`
  - `async search_roundtrip(client, dep, arr, out_date, ret_date) -> ProviderResult`
  - `client`는 `httpx.AsyncClient` (worker가 하나 열어 재사용).
- 타임아웃: 편도 45초, 왕복 60초 (`config.py`의 `NAVER_ONEWAY_TIMEOUT`, `NAVER_ROUNDTRIP_TIMEOUT`).

### 3.2 응답 → `LegQuote` (편도)

마지막 스냅샷의 `itineraries`를 `itineraryId`로 색인하고, `fareMappings`와 각 매핑의 `sameFareMappings`를 모두 항공편 후보로 본다. 각 후보(`itineraryIds` → 구간 목록 `segments`)에 대해:

1. **코드셰어 제외:** 어느 구간이든 `operatingCarrier.airlineCode`가 비어 있지 않고 `marketingCarrier.airlineCode`와 다르면 버린다.
2. **공항·시각 검증:** 첫 구간 출발 공항 ≠ 검색 출발지, 또는 마지막 구간 도착 공항 ≠ 검색 도착지면 버린다. 시각(`HHMM`)을 `HH:MM`으로 바꾸고 형식이 틀리면 버린다 (GF `_valid_times`와 같은 규칙).
3. **요금:**
   - `price` = `fareType == "A01"`인 요금의 `adult.totalFare` 최저값. `A01`이 없으면 후보를 버린다.
   - 조건부 최저 = `fareType`이 `"A01/"`로 시작하는 요금의 최저값. 이것이 `price`보다 작을 때만 `cond_price`로 채운다.
   - `cond_label` = 응답 `status.fareTypesCodeMap[fareType].name`에서 앞의 `"성인/"`을 뗀 문자열 (예: `"삼성 iD GLOBAL 카드"`). 맵에 없으면 fareType 문자열 그대로.
4. **필드:**
   - `flight_numbers` = 각 구간 `f"{airlineCode} {int(flightNumber)}"` (GF와 같은 `"RS 433"` 형식)
   - `airline_iata` = 첫 구간 marketing 항공사, `airline_name` = `status.airlinesCodeMap`의 이름 (없으면 코드)
   - `stops` = 구간 수 − 1 + 모든 구간 `hiddenStops` 개수
   - `duration_min` = 여정 `duration`(초) // 60
   - `flight_key` = 기존 `airlines.flight_key(date, dep, arr, dep_time, arr_time, stops, airline_iata)`
5. **링크:**
   - `booking_url` = 판매사 선택 딥링크(fareType `A01`), `cond_booking_url` = 같은 형식에 조건부 fareType
   - 딥링크 형식: `https://flight.naver.com/flights/international/detail/{DEP}:airport-{ARR}:airport-{YYYYMMDD}?adult=1&isDirect=false&fareType=Y&selectType=concurrent&selectedFlight=` + URL 인코딩된 `1:{itineraryId}:{fareType}:HK:{airline_iata}:`
   - `search_url` = `https://flight.naver.com/flights/international/{DEP}:airport-{ARR}:airport-{YYYYMMDD}?adult=1&isDirect=false&fareType=Y&tripType=OW`
6. 같은 `flight_key`가 여러 번 나오면 `price`가 가장 낮은 것 1건만 남기고, 가격 오름차순으로 정렬한다 (GF `cards_to_legs`와 같은 규칙).

### 3.3 응답 → `RtQuote` (왕복)

- `fareMappings[].itineraryIds`는 `"{가는편 itineraryId}-{오는편 itineraryId}"` 형식이다.
- 가는 편·오는 편 모두 3.2의 코드셰어·공항·시각 규칙을 통과한 조합만 쓴다.
- `out_flight_key` = 가는 편 `flight_key`, `airline_iata` = 가는 편 첫 구간 marketing 항공사
- `total_price` = `A01` 최저, `cond_total_price`/`cond_label` = 3.2와 같은 규칙
- 요청은 가격순 200개(`limit: 200`)만 받는다. 참고가에는 최저 쪽만 필요하다.

### 3.4 상태 판정

| 상황 | status | error |
|---|---|---|
| HTTP 403·429, 또는 본문이 SSE/JSON이 아님(HTML) | `blocked` | HTTP 코드 또는 `"non-json response"` |
| 네트워크 예외, 5xx, 타임아웃 | `error` | 예외 메시지 |
| 스냅샷을 받았으나 항공편 0개 | `empty` | — |
| 항공편 1개 이상 | `ok` | 판매처 응답이 덜 끝났으면 `"partners 18/20"` 형식 기록 |

## 4. 저장

- `init_schema()`에 `ADD COLUMN IF NOT EXISTS` 추가 (기존 행은 NULL):
  - `leg_quotes`: `cond_price INT`, `cond_label TEXT`, `cond_booking_url TEXT`
  - `rt_quotes`: `cond_total_price INT`, `cond_label TEXT`
- `types.py`: `LegQuote`에 `cond_price: int | None = None`, `cond_label: str | None = None`, `cond_booking_url: str | None = None`; `RtQuote`에 `cond_total_price: int | None = None`, `cond_label: str | None = None`. 기본값이 있어 GF 코드는 그대로 동작한다.
- `repo.save_snapshot` / `load_snapshots`가 새 칸을 저장·복원한다. 스냅샷·견적은 append-only 그대로.
- `alerts.kind`의 운영 알림은 제공자별로 `"ops:google_flights"`, `"ops:naver"`를 쓴다. 기존 `"ops"` 행은 더 이상 조회하지 않는다 (배포 직후 쿨다운이 한 번 초기화되는 것뿐).

## 5. 병합 — `flight_friend/domain/results.py`

`_merge(direction, entries, cutoff)`를 다음 순서로 바꾼다.

1. **1차 매칭:** `flight_key`가 같은 견적끼리 묶는다 (현행).
2. **2차 매칭:** 묶음들 가운데 `(date, dep_airport, arr_airport, tuple(flight_numbers))`가 같은 것끼리 합친다. `flight_numbers`가 비어 있는 견적은 2차 매칭에 참여하지 않는다. 묶음 합치기는 union-find 또는 동등한 방식으로, 1차·2차 어느 쪽으로든 연결되면 하나가 된다.
3. **대표 견적 `leg`:** 묶음 안에 GF 견적이 있으면 그중 가장 싼 것, 없으면 전체에서 가장 싼 것. `MergedLeg.flight_key`는 대표 견적의 키.
4. **제공자별 가격 `prices`:** 제공자마다 1건 — 같은 제공자 견적이 여럿이면 `price`가 가장 낮은 것. `ProviderPrice`에 `cond_price`, `cond_label`, `cond_booking_url` 추가.
5. **`best_price`/`best_provider`:** 신선한 `prices`의 `price` 최저 (현행 규칙 그대로).
6. **`best_cond`** (신규, `CondPrice | None`): 신선한 `prices`의 `cond_price` 최저가 `best_price`보다 작을 때만 `CondPrice(price, label, provider, booking_url)`.

추적(`domain/tracking.py`), 알림 판정, 파레토 후보, near-miss, 선호 조건 판정은 `best_price`와 대표 견적만 쓰므로 바꾸지 않는다.

`rt_reference`는 이미 제공자별 최신 ok 왕복 스냅샷을 모은다. Naver 왕복이 들어오면 두 제공자 중 싼 쪽이 반영된다. 조건부 왕복가(`cond_total_price` 최저, `total_price`보다 쌀 때만)를 `RtReference`에 참고 칸으로 추가한다.

## 6. API와 화면

### 6.1 API (`api/views.py`) · `types.ts`

- 편도 항목: `best_cond: {price, label, provider, booking_url} | null` 추가. `prices[]` 각 항목에 `cond_price`, `cond_label`, `cond_booking_url` 추가.
- 왕복 참고가: 조건부 왕복가 칸 추가.
- 기존 칸의 이름·의미는 바꾸지 않는다.

### 6.2 화면 (최소 변경 — FE 대개편 예정)

- **편도 카드 (`LegCard`):**
  - 가격 칸은 현행(조건 없는 최저가 + `제공자 외 N곳`). `best_cond`가 있으면 아래 한 줄 `카드 조건 시 161,700원`.
  - 상세 영역은 **기본 펼침**. 토글 버튼은 누르기 쉽게 더 크게.
  - 제공자별 줄: `Naver 171,000원 · 3분 전 · 판매사 선택 ↗`, 조건부가 있으면 들여 쓴 줄 `삼성 iD GLOBAL 카드 실적 충족 시 161,700원 · 판매사 선택 ↗`. GF 줄은 현행 `예약 ↗`.
- **선택 바 (`SelectionBar`):** 합계는 조건 없는 가격 기준. 한쪽이라도 조건부가 있으면 `카드 조건 적용 시 최저 합계 N원` 한 줄과 "편마다 조건이 다를 수 있음" 안내.
- **왕복 참고가:** 싼 제공자 이름 표시, 조건부 왕복가가 있으면 한 줄 추가.
- **상단 상태·`/admin`:** 제공자 표시는 스냅샷 기준이라 Naver가 자동으로 나타난다. 추가 작업 없음.

## 7. 운영

### 7.1 worker

- `main_loop`가 시작할 때 `httpx.AsyncClient`를 하나 열고 종료 시 닫는다.
- `execute_run`은 제공자 목록을 받는다. 각 제공자는 `(provider 이름, search_oneway, search_roundtrip)`이고, 실행 한 번에 6건을 `asyncio.gather`로 동시에 돌려 스냅샷 6개를 저장한다. 제공자 하나의 예외는 그 제공자의 `error` 스냅샷이 되고 나머지는 계속 저장된다.
- `RUN_TIMEOUT`(3분)은 그대로. 크롤러 재생성 로직도 그대로 (httpx 클라이언트는 재생성하지 않음).

### 7.2 운영 알림

- `evaluate_ops`를 제공자별로 판정한다: 끝난 run 최근 3건에서 그 제공자의 편도 스냅샷이 모두 비-ok이면 알림.
- 메시지: `[Flight Friend] {제공자 표시명} 최근 3회 검색 연속 실패 — /admin 확인`
- 쿨다운 6시간을 제공자별(`alerts.kind = "ops:{provider}"`)로 따로 적용한다.

### 7.3 요청량

run 1회당 Naver 요청 3건. 자동 갱신 주기(1–6시간)와 수동 쿨다운(5분) 아래에서 사람 검색 수준을 넘지 않는다.

## 8. 테스트

- `tests/fixtures/`에 실제 응답을 잘라 넣은 SSE 샘플(편도 1개, 왕복 1개). 테스트는 실제 Naver를 호출하지 않는다 (`httpx.MockTransport`).
- provider: 마지막 줄만 사용, 코드셰어 제외, 공항·시각 검증, `A01` 없는 후보 제외, 조건부 채움 규칙(더 쌀 때만)과 라벨, 딥링크 인코딩, 왕복 조합 파싱, 상태 판정 표(403/429/HTML/5xx/타임아웃/0개/부분 완료).
- 병합: 편명만 같고 도착 1분 다른 GF·Naver 견적이 합쳐지고 GF 시각이 대표; 편명이 비면 합쳐지지 않음; 같은 제공자 중복은 최저 1건; `best_cond`는 `best_price`보다 쌀 때만.
- worker: 제공자 2개 × 3건 스냅샷 저장, 한 제공자 예외 시 다른 제공자 스냅샷 유지, 제공자별 ops 알림과 쿨다운.
- M1 기존 테스트는 전부 그대로 통과해야 한다.

## 9. 진행 순서와 게이트

1. **OCI 확인 (게이트):** 서버에서 `scripts/naver_spike.py`로 `http 201 … completed True` 확인. 막히면 구현을 멈추고 브라우저 재시도 방식을 다시 논의한다.
2. 스키마·타입 → Naver provider → 병합 → worker·운영 알림 → API·화면.
3. 마무리: `scripts/naver_spike.py` 삭제, AGENTS.md(제공자 목록·Naver 메모)·log.md 갱신.

## 10. 리스크

| 리스크 | 대응 |
|---|---|
| OCI(한국 IP)에서 API 차단 | 9-1 게이트. 운영 중 차단은 ops 알림으로 감지 |
| Naver API 형식 변경 (비공개 API) | 파서 실패 → `error` 스냅샷 + ops 알림. GF는 계속 동작 |
| 조건부 가격 오해 | 계산에서 제외(D2), 조건 이름을 항상 함께 표시 |
| 편명 보조 매칭이 다른 항공편을 합침 | 날짜·양쪽 공항·편명 전체가 같아야 합침. 편명 없으면 불참 |
| 제3 발권사 가격 ≠ 결제 가격 (상위 설계 P2) | 미해결 유지. 판매사 선택 페이지로 보내 사용자가 확인 |
