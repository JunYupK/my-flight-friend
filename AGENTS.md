# AGENTS.md — flight-friend

> Claude Code가 이 레포에서 작업할 때 항상 먼저 읽는 하네스(Harness) 명세서.
> 모든 규칙은 테스트와 린터로 기계적으로 강제하는 것을 목표로 한다 — 충돌 시 본 문서 우선.

---

## 1. 프로젝트 개요

**ICN 출발 일본 항공권 최저가 모니터링 서비스.**
복수 데이터 소스(Google Flights, Naver)에서 편도 레그를 수집해 왕복 조합을 만들고,
목표가 이하 딜을 알림으로 전송한다. FastAPI 백엔드 + React/Vite SPA로 웹 UI를 제공한다.

**배포 환경:** OCI 한국 리전, 단일 `docker-compose.yml` (profiles로 dev/full 분리), 호스트 crontab으로 3시간 주기 수집.

---

## 2. 아키텍처 레이어 (의존성 방향 엄수)

```
Types/Config  →  Repository  →  Service  →  Router  →  UI
     ↑               ↑              ↑           ↑
  config.py      storage.py    (service/)   api/main.py   web/src/
```

### 레이어별 책임

| 레이어 | 위치 | 책임 | 금지 |
|--------|------|------|------|
| **Config** | `flight_monitor/config.py`, `config_db.py` | 전역 설정, DB → 메모리 패치 | 비즈니스 로직, DB 직접 쿼리 |
| **Repository** | `flight_monitor/storage.py` | DB CRUD, 트랜잭션 | 비즈니스 로직, HTTP 의존 |
| **Collector** | `flight_monitor/collector_*.py` | 외부 데이터 수집, `save_legs()` 호출 | Router/Service 직접 import |
| **Service** | `flight_front/api/deals_cache.py`, `run_state.py`, `mcp_server.py` | 캐시 전략, 조합 로직, 상태/RPC | FastAPI 직접 의존, HTTP 응답 객체 생성 |
| **Notifier** | `flight_monitor/notifier.py` | 알림 dispatch (Telegram 1순위 → Discord 2순위 fallback) | 비즈니스 로직 |
| **Router** | `flight_front/api/main.py` | HTTP 엔드포인트, 요청/응답 직렬화 | DB 직접 쿼리, 비즈니스 로직 함수 정의 |
| **UI** | `flight_front/web/src/` | React 컴포넌트, API 호출 | 백엔드 모듈 직접 import |

### 의존성 규칙

```
✅ 허용
router  → service
router  → storage  (단순 CRUD 1줄 이하, 조건 없음)
service → storage
collector → storage
config_db → storage

❌ 금지
router  → collector   (크롤러를 라우터에서 직접 호출 금지)
service → router      (역방향 금지)
ui      → storage     (프론트엔드가 DB 모듈 import 금지)
```

> 본 규칙은 추후 `tests/test_architecture.py`에서 기계 검증 예정 (§11 참조).

---

## 3. 파일 위치 규칙

새 파일을 만들기 전에 아래 표를 확인할 것. 위치가 불명확하면 **파일 생성 전에 물어본다.**

| 무엇을 만드는가 | 위치 |
|----------------|------|
| DB 쿼리 함수 | `flight_monitor/storage.py` |
| 캐시 / 조합 로직 | `flight_front/api/deals_cache.py` (또는 새 service 파일) |
| 새 데이터 소스 collector | `flight_monitor/collector_{source}.py` |
| API 엔드포인트 | `flight_front/api/main.py` |
| MCP RPC 함수 | `mcp_server.py` (Service 레이어) |
| React 컴포넌트 | `flight_front/web/src/components/` |
| API 클라이언트 함수 | `flight_front/web/src/api.ts` |
| 공유 타입 | `flight_front/web/src/types.ts` |
| 테스트 | `tests/` |
| 알림 채널 추가 | `flight_monitor/notifier.py` |

---

## 4. 코딩 규칙

### Python

- **타입 힌트 필수**: 함수 파라미터와 반환값 모두. `Any` 사용 금지.
- **async/await 일관성**: `asyncio.run()`은 최상위 진입점(`main.py`, 동기 래퍼)에서만. 내부 함수는 `async def`로 일관.
- **크롤러 병렬화**: 신규 collector는 반드시 `arun_many()` 배치 패턴 사용. 순차 루프 금지.
- **에러 처리**: collector는 개별 실패를 `print(f"[{SOURCE} ERROR]")`로 로깅 후 계속 진행. 전체 크롤을 중단하는 `raise` 금지.
- **하드코딩 금지**: URL, 크리덴셜, DB 연결 정보는 환경변수 또는 `config.py` 경유.

### Offer Dict 인터페이스

모든 collector는 반드시 아래 필드를 포함하는 dict를 생산해야 한다.
누락 필드가 있으면 `save_prices()`에서 런타임 에러가 발생한다.

```python
{
    "source": str,           # "google_flights" | "naver"
    "trip_type": str,        # "round_trip" | "oneway_combo"
    "origin": str,           # "ICN"
    "destination": str,      # IATA 3자리
    "destination_name": str,
    "departure_date": str,   # "YYYY-MM-DD"
    "return_date": str,
    "stay_nights": int,
    "price": float,          # 왕복 합산 KRW
    "currency": str,         # "KRW"
    "out_airline": str,
    "in_airline": str,
    "is_mixed_airline": bool,
    "checked_at": str,       # isoformat with KST timezone
    "out_url": str | None,
    "in_url": str | None,
    "out_price": float,
    "in_price": float,
}
```

### Leg Dict 인터페이스

`save_legs()`에 전달하는 leg dict 필수 필드:

```python
{
    "source": str,
    "origin": str,
    "destination": str,
    "destination_name": str,
    "date": str,        # "YYYY-MM-DD"
    "direction": str,   # "out" | "in"
    "price": float,
    "checked_at": str,  # isoformat
    # optional: airline, dep_time, arr_time, duration_min, stops,
    #           dep_airport, arr_airport, booking_url, search_url
}
```

### TypeScript / React

- **타입 단언(`as`) 금지**: `types.ts`에 정의된 타입 사용. 타입이 없으면 추가.
- **`any` 금지**: `unknown` + type guard 패턴.
- **API 호출 위치**: 컴포넌트에서 직접 `fetch` 금지. 반드시 `api.ts` 함수 경유.
- **상태 관리**: 전역 상태 라이브러리 추가 금지. `useState` / `useEffect` 패턴 유지.

---

## 5. DB 규칙

### 테이블 역할 (절대 혼용 금지)

| 테이블 | 역할 | 쓰기 위치 |
|--------|------|-----------|
| `raw_legs` | 수집 원본 append-only 로그 | `save_legs()` 전용 |
| `flight_legs` | 소스별 현재 최저가 (UPSERT) | `save_legs()` 전용 |
| `price_events` | 가격 하락 이벤트 (DB 트리거 자동 기록) | **직접 INSERT 금지** |
| `price_history` | 레거시 왕복 조합 기록 | `save_prices()` 전용 |
| `alert_state` | 알림 dedup/cooldown 상태 | `record_alert()` 전용 |
| `airports` | 목적지 공항 설정 | 웹 UI API 또는 `config_db.py` |
| `app_config` | JSONB 설정 | `write_config()` 전용 |
| `collection_runs` | 수집 실행 이력 | `start/finish_collection_run()` 전용 |

### 마이그레이션 규칙

- 스키마 변경은 `init_db()`에 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 패턴으로 추가.
- `init_db()`는 멱등성 보장 필수 (두 번 호출해도 에러 없음 — `TestInitDb.test_init_idempotent` 검증).
- 컬럼 타입 변경 시 반드시 `SAVEPOINT` 패턴 사용 (기존 코드 참고).

---

## 6. 테스트 규칙

### 테스트 파일 위치

```
tests/
├── test_flight_monitor.py    # storage 레이어 통합 테스트 (PostgreSQL 필요)
├── test_notifier.py          # 알림 fallback 단위 테스트 (HTTP mock)
└── test_architecture.py      # 레이어 경계 위반 감지 (예정, §11 참조)
```

### 필수 원칙

- **새 `storage.py` 함수 → 반드시 테스트 동반.** 테스트 없는 DB 함수 PR 금지.
- **`clean_db` fixture 필수 사용**: 모든 DB 테스트는 `autouse=True` fixture로 격리.
- **외부 API mock 필수**: collector / notifier 테스트에서 실제 crawl4ai / HTTP 호출 금지. `monkeypatch.setattr` 또는 `unittest.mock.patch` 사용.
- **테스트 실행 명령**:

```bash
pytest tests/                                                 # 전체
pytest tests/test_flight_monitor.py::TestSaveLegs             # 클래스 단위
pytest tests/test_notifier.py::TestSendAlertFallback          # fallback 검증
```

### 아키텍처 테스트 (`tests/test_architecture.py`, 예정)

§2의 의존성 규칙을 기계적으로 검증할 테스트가 추가될 예정. 검증 대상:

1. `api/main.py`가 `storage.py`의 `get_conn()`을 직접 호출하지 않음
2. `collector_*.py`가 `fastapi`를 import하지 않음
3. `web/src/` TypeScript 파일이 Python 모듈을 import하지 않음 (당연하지만 명시)

---

## 7. 성능 & 운영 규칙

### 크롤러

- 배치 크기: `_BATCH_SIZE = 5` (변경 시 OCI 메모리 한도 주의)
- 병렬 공항 수: `SEARCH_CONFIG["parallel_airports"]` (기본 3)
- 오늘 이미 수집한 레그는 `get_collected_today()`로 스킵 (중복 요청 방지)
- crawl4ai `wait_for` 셀렉터 변경 시 반드시 해당 collector mock 테스트도 업데이트

### 캐시

- Redis 연결 실패 시 in-memory fallback 자동 전환 (현재 구현 유지)
- TTL: `DEALS_CACHE_TTL = 11400` (3시간 10분). 크롤 주기(3h)보다 길게 유지.
- 크롤 완료 후 반드시 `bump_deals_version()` + `warm_deals_cache()` 호출 순서 보장

### 알림

- **채널 우선순위 고정**: Telegram(1순위) → Discord(2순위) fallback. **첫 성공 채널만 발송**, 둘 다 보내지 않는다.
- 채널 추가는 `notifier.send_alert()` 의 fallback 체인 끝에 append. 우선순위 재배치 시 fallback 테스트(`test_notifier.py`) 동시 갱신.
- `notify(offer, target_price)` 는 사용자 알림 (왕복 딜), `send_alert(message)` 는 운영 알림 (수집 0건 / 크래시).

### 수집 트리거

- **호스트 crontab**이 3시간 주기로 collector 컨테이너를 실행한다 (`docker compose --profile collect run --rm collector python main.py`).
- collector 컨테이너 이미지는 `Dockerfile.collector` (crawl4ai + Playwright). 빌드 시간이 길어 배포 헬스체크와 분리되어 있음 (`.github/workflows/deploy.yml` 참고).
- 환경변수는 `.env` 로딩 후 진입.

### 배포

- 단일 `docker-compose.yml`. profiles로 분기:
  - `docker compose up -d` → db + redis만 (로컬 개발 기본)
  - `docker compose --profile full up -d` → app/collector/mcp/caddy 포함 풀 스택 (배포 서버)
  - `docker compose --profile collect run --rm collector ...` → 크론 1회성 수집
- 환경변수 추가 시 `docker-compose.yml` + `.env.example` + 본 문서 §10 동시 업데이트
- GitHub Actions CI: 즉시 배포 검증 흐름이므로 `pytest tests/` + React build 통과를 강하게 강제한다. CI 실패 시 SSH 배포 잡(`deploy.yml`)이 트리거되지 않는다.

---

## 8. 금지사항 (절대 위반 금지)

```
❌ api/main.py 에 SQL 쿼리 직접 작성
❌ collector에서 asyncio.run() 내부에서 또 asyncio.run() 중첩
❌ storage.py 에서 FastAPI, HTTPException import
❌ 하드코딩된 DATABASE_URL 문자열
❌ price_events 테이블 직접 INSERT (트리거가 담당)
❌ flight_legs 테이블 직접 UPDATE (save_legs() 경유 필수)
❌ JAPAN_AIRPORTS / TFS_TEMPLATES 를 config.py 에서 직접 수정
    (반드시 config_db.apply_db_config() 경유)
❌ 테스트에서 실제 외부 API 호출 (크롤러/알림 mock 필수)
❌ React 컴포넌트에서 직접 fetch() 호출 (api.ts 경유 필수)
❌ notifier.py 에 비즈니스 로직 (메시지 포맷팅 외) 추가
```

---

## 9. 작업 시작 전 체크리스트

에이전트는 새 작업을 시작하기 전에 다음을 확인한다:

1. **어느 레이어에 속하는 변경인가?** → 해당 레이어 파일에만 손댄다.
2. **DB 스키마 변경이 포함되는가?** → `init_db()` 멱등성 유지, `TestInitDb` 통과 확인.
3. **새 storage 함수인가?** → 테스트 먼저 작성 후 구현 (TDD).
4. **새 collector인가?** → offer dict / leg dict 인터페이스 완전히 충족하는가 확인.
5. **API 응답 형식 변경인가?** → `types.ts`의 해당 타입도 동시 업데이트.
6. **알림 변경인가?** → `tests/test_notifier.py` 의 fallback 시나리오를 그대로 통과시키는가 확인.

---

## 10. 환경 변수

```bash
# 필수
DATABASE_URL=postgresql://flight_user:flight_pass@localhost:5432/flights

# 선택 — 캐시
REDIS_URL=redis://localhost:6379

# 선택 — 알림 채널 (Telegram 1순위 → Discord 2순위 fallback)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DISCORD_WEBHOOK_URL=

# docker-compose 사용 시
DB_PASSWORD=flight_pass
DOMAIN=localhost

# Windows 전용 (subprocess 인코딩)
PYTHONIOENCODING=utf-8
```

> 신규 환경변수 추가 시 `.env.example` 와 본 섹션을 같은 PR에서 갱신할 것.

---

## 11. Known Issues (작업 전 참고)

1. `api/main.py` 의 다음 함수가 Router에 있지만 Service 로직이다 — 추후 `flight_front/api/services/` 로 이동 예정. 해당 함수를 만지는 PR은 가능하면 이전도 함께 수행:
   - `_combine_legs`, `_select_diverse_deals`
   - `_query_outbound_legs`, `_query_inbound_legs`
   - `/api/calendar-prices` 본체의 `get_conn()` 직접 호출
   - `/api/price-history` 본체의 `get_conn()` 직접 호출

2. LCC 항공사(Peach, Zipair 등) 일부가 `_AIRLINE_IATA` 매핑에 누락 →
   `collector_google_flights.py` 의 `_AIRLINE_IATA` dict 에 추가 가능.

3. `tests/test_architecture.py` 미작성 상태.
   §2의 의존성 규칙은 현재 컨벤션이며, 본 테스트가 추가되면 CI에서 자동 강제된다.

4. `mcp_server.py` 는 Service 레이어로 분류했으나 물리적으로는 레포 루트에 있음.
   추후 `flight_front/api/services/` 로 이동 예정 — 위치 이동만으로 import 경로 깨짐 주의.

---

## 12. 명령어 레퍼런스

```bash
# DB + Redis 만 (로컬 개발 기본)
docker compose up -d

# 풀 스택 (배포 서버)
docker compose --profile full up -d

# 1회성 수집 (cron 트리거가 사용)
docker compose --profile collect run --rm collector python main.py

# 로컬 수집 실행
python main.py

# FastAPI 백엔드
uvicorn flight_front.api.main:app --reload

# React 프론트엔드
cd flight_front/web && npm run dev

# 테스트
pytest tests/
pytest tests/test_flight_monitor.py::TestSaveLegs
pytest tests/test_notifier.py

# React 빌드
cd flight_front/web && npm run build
```
