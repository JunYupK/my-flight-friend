# AGENTS.md — flight-friend

> Claude Code가 이 레포에서 작업할 때 항상 먼저 읽는 하네스(Harness) 명세서.
> 규칙은 테스트와 린터로 기계적으로 강제하는 것을 목표로 한다 — 충돌 시 본 문서 우선.
> 설계 원문: `docs/superpowers/specs/2026-09-28-flight-friend-v2-design.md`

---

## 1. 프로젝트 개요 (V2)

**ICN 출발 일본 항공권 추적 서비스.** 사용자가 **Trip**(목적지·출발일·귀국일·선호)을 만들면 그 Trip을 중심으로
가격을 추적한다.

- **Trip 중심:** 모든 화면/알림/조회의 단위는 Trip. 전역 "딜 목록"은 없다.
- **스냅샷 관측:** 한 번의 재확인 = 한 `search_run`, 제공자별 결과 = `snapshot`. 관측값은 append-only로 쌓고 덮어쓰지 않는다.
- **사용자 트리거 재확인:** 웹에서 사용자가 "다시 확인"을 누르면 run이 큐잉되고, 상주 worker가 처리한다 (수동 쿨다운 있음).
  추적 중(`tracking`) Trip은 worker가 출발까지 남은 일수 티어에 따라 자동 갱신한다.
- 데이터 소스는 현재 Google Flights 하나(편도 leg + 왕복 rt). 제공자는 어댑터 인터페이스로 추가한다 (§5).

**배포:** OCI 한국 리전 단일 `docker-compose.yml`. `app`(FastAPI + SPA), `worker`(상주, Chromium), `db`, `caddy`.

> **V1은 제거됨 (Task 17).** 코드는 커밋 `d8e0422`(V2 직전 master)에 있다 (`git show d8e0422:<경로>`). V1 테이블은 `scripts/v1_freeze.sql`로 `v1` 스키마에 동결.

---

## 2. 아키텍처 레이어 (의존성 방향 엄수)

```
types/config → db/repo → providers → domain → worker / api views → api main → web
```

| 레이어 | 위치 | 책임 | 금지 |
|--------|------|------|------|
| **Types/Config** | `flight_friend/types.py`, `config.py` | 데이터클래스, 잠정 상수 | 로직, I/O |
| **DB/Repo** | `flight_friend/db.py`, `repo.py` | 스키마(`init_schema()`), CRUD, 트랜잭션 | 비즈니스 로직, HTTP 의존 |
| **Providers** | `flight_friend/providers/` | 외부 수집(크롤링), 결과를 `ProviderResult`로 정규화 | DB 접근, 웹 프레임워크 |
| **Domain** | `flight_friend/domain/` (`results`, `schedule`, `tracking`) | 순수 로직: 결과 조합·후보·near-miss, 갱신 주기, 알림 판정 | `fastapi`/`starlette`, `db`/`repo` import |
| **Worker** | `flight_friend/worker.py`, `notifier.py` | run 소비, provider 호출, snapshot 저장, 알림 판정·발송 | 웹 프레임워크 |
| **Views** | `flight_friend/api/views.py` | repo + domain → JSON 직렬화 dict | `fastapi`/`starlette` import |
| **API** | `flight_friend/api/main.py` | HTTP 엔드포인트(`/api/*`, `/healthz`), SPA 서빙 | `providers` import, SQL 직접 작성 |
| **Web** | `flight_front/web/src/` | React SPA, `api.ts` 경유 호출 | 백엔드 모듈 import |

`tests/test_architecture.py`가 위 금지 규칙(views/domain/providers/db/repo → 웹 프레임워크, api/main → providers, domain → db/repo)을
`ast` 정적 분석으로 검증한다 (DB 불필요, CI 항상 실행).

---

## 3. 파일 위치 규칙

위치가 불명확하면 **파일 생성 전에 물어본다.**

| 무엇을 만드는가 | 위치 |
|----------------|------|
| DB 쿼리 함수 / 스키마 변경 | `flight_friend/repo.py` / `db.py` |
| 순수 로직 (조합·주기·알림 판정) | `flight_friend/domain/` |
| 새 데이터 소스 | `flight_friend/providers/{source}.py` |
| JSON 응답 조립 | `flight_friend/api/views.py` |
| HTTP 엔드포인트 | `flight_friend/api/main.py` |
| 잠정 상수 | `flight_friend/config.py`, `domain/schedule.py` |
| React 컴포넌트 / 페이지 | `flight_front/web/src/components/`, `pages/` |
| API 클라이언트 / 공유 타입 | `flight_front/web/src/api.ts` / `types.ts` |
| 테스트 | `tests/test_<모듈>.py` (fixture 파일은 `tests/fixtures/`) |
| 아키텍처 규칙 | `tests/test_architecture.py` |

---

## 4. 코딩 규칙

- **Python:** 타입 힌트 필수(파라미터·반환), `Any` 지양. 하드코딩 금지 — URL/크리덴셜/DB 연결은 환경변수 경유.
  provider는 개별 실패를 예외로 던지지 말고 `ProviderResult(status="error", ...)`로 흡수한다.
- **TypeScript/React:** `as` 단언·`any` 금지(`unknown` + type guard), 컴포넌트에서 직접 `fetch` 금지(`api.ts` 경유),
  전역 상태 라이브러리 금지(`useState`/`useEffect`).

---

## 5. Provider 어댑터 인터페이스

provider 모듈은 크롤러(`Crawler` Protocol)를 주입받는 async 함수로 노출하고 항상 `ProviderResult`를 돌려준다.
(현재: `providers/google_flights.py` — `search_oneway(crawler, dep, arr, date)`, `search_roundtrip(...)`)

```python
@dataclass
class ProviderResult:
    status: Literal["ok", "empty", "blocked", "error"]
    legs: list[LegQuote]   # 편도 견적
    rts: list[RtQuote]     # 왕복 견적
    error: str | None
    seconds: float
```

- `blocked`(차단 의심)와 `empty`(결과 없음)를 구분한다. 예외는 `error`로 흡수.
- worker는 provider 함수를 주입 가능한 인자로 받는다 → 테스트에서 실제 크롤링 없이 fake로 대체.
- 신규 provider는 `providers/`에 추가하고 worker의 provider 목록에만 등록한다 (api/main은 모른다).

---

## 6. DB 규칙 (V2 테이블)

| 테이블 | 역할 | 성격 |
|--------|------|------|
| `trips` | 사용자 Trip(목적지·날짜·선호·tracking·archived_at) | 갱신(UPDATE) |
| `search_runs` | 재확인 요청/진행 상태(queued→running→done/error) | 갱신 |
| `snapshots` | run × provider × kind(oneway/roundtrip) 관측 1건 + status/error | **append-only** |
| `leg_quotes` | snapshot에 딸린 편도 견적 | **append-only** |
| `rt_quotes` | snapshot에 딸린 왕복 견적 | **append-only** |
| `alerts` | 알림 발송 이력(dedup/쿨다운 기준) | 갱신/기록 |

- `snapshots`/`leg_quotes`/`rt_quotes`는 UPDATE·DELETE 금지 (이력 = 가격 추이의 원천).
- 스키마 진입점은 `flight_friend/db.py`의 `init_schema()` (V1의 `init_db()` 아님). **API 기동(lifespan)과 worker 시작(`main_loop` 최상단)이 호출**하며, advisory lock으로 동시 실행에 안전하다. 변경은 `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`로 추가, 멱등 필수.
- `/healthz`는 `db.schema_ready()`로 스키마·DB 연결을 확인해 실패 시 503을 돌려준다.
- 모든 DB 접근은 `repo.py` 경유. 테스트는 `tests/conftest.py`의 `clean_db` fixture로 격리.
- **V1 테이블(`raw_legs`, `flight_legs`, `deals`, `price_events`, `price_history`, `alert_state`, `collection_runs` 등)은 동결.**
  `scripts/v1_freeze.sql`이 `v1` 스키마로 옮긴다 (분석용 읽기만). V2는 읽지도 쓰지도 않는다.

---

## 7. 잠정 상수

실측 전 잠정치이며 코드 상수 한 곳에서만 바꾼다.

- `flight_friend/config.py`: `ORIGIN`, `MANUAL_COOLDOWN`(5분), `STUCK_RUN_AFTER`(10분), `NEAR_MISS_MIN_PCT/KRW`,
  `ALERT_DROP_PCT/KRW`, `MIN_TRACKING_DAYS`
- `flight_friend/domain/schedule.py`: 갱신 주기 티어 `FAR/NEAR_TIER_DAYS`, `FAR/MID/NEAR_INTERVAL` (출발까지 남은 일수 기준)

---

## 8. 테스트 규칙

- 테스트는 `tests/` 한 곳. `conftest.py`의 autouse `clean_db`가 매 테스트 스키마 보장 + TRUNCATE 하므로 PostgreSQL 필요(`DATABASE_URL`).
  DB가 필요 없는 정적 분석 모듈은 `pytestmark = pytest.mark.no_db`로 빠진다 (`tests/test_architecture.py`).
- 새 `repo.py` 함수 → 테스트 동반. 외부 호출(크롤링/알림)은 fake·mock 필수.
- 실행:

```bash
DATABASE_URL=postgresql://flight_user:flight_pass@localhost:5432/flights pytest tests/ -q
ruff check .            # CI는 ruff==0.16.9 고정
```

---

## 9. 운영 · 배포

- `docker compose up -d` → db (로컬 개발)
- `docker compose --profile full up -d` → app / worker / caddy 포함 풀 스택
- `worker`는 `Dockerfile.collector`(crawl4ai + Chromium)로 빌드, `restart: unless-stopped` 상주. 크롤러가 무거워 배포 시
  app 헬스체크 이후 별도 빌드·기동한다 (`.github/workflows/deploy.yml`).
- `app` 헬스체크와 배포 readiness probe는 `/healthz` (`{"ok": true}`).
- CI(`ci.yml`): `pytest tests/` + `ruff check .` + React build. 실패 시 배포(`deploy.yml`) 미트리거. master push + CI 성공 → SSH 자동 배포.
- 알림 채널은 Telegram 1순위 → Discord 2순위 fallback, 첫 성공 채널만 발송 (`flight_friend/notifier.py`).
- 호스트 crontab의 **V1 수집 cron과 spike cron은 제거**해야 한다 (worker가 대체).

### 환경 변수

```bash
DATABASE_URL=postgresql://flight_user:flight_pass@localhost:5432/flights   # 필수
TELEGRAM_BOT_TOKEN= / TELEGRAM_CHAT_ID=     # 선택 — 알림 1순위
DISCORD_WEBHOOK_URL=                        # 선택 — 알림 2순위
DB_PASSWORD=flight_pass / DOMAIN=localhost  # docker-compose
PUBLIC_BASE_URL=                            # 선택 — 알림의 Trip 링크 기준 URL
```

신규 환경변수는 `docker-compose.yml` + `.env.example` + 본 섹션을 같이 갱신한다.

---

## 10. 금지사항 (절대 위반 금지)

```
❌ V1 테이블(v1 스키마) 쓰기 — 동결된 분석용 데이터
❌ api/main.py 에 SQL 직접 작성, providers import
❌ views.py / domain/* / providers/* / db·repo 에서 fastapi·starlette import, domain/* 에서 db·repo import
❌ snapshots / leg_quotes / rt_quotes 의 UPDATE·DELETE (append-only)
❌ 하드코딩된 DATABASE_URL 문자열
❌ 테스트에서 실제 외부 API 호출 (크롤러/알림 mock 필수)
❌ React 컴포넌트에서 직접 fetch() 호출 (api.ts 경유 필수)
❌ 크롤러 코드에서 asyncio.run() 중첩
❌ notifier 에 비즈니스 로직(메시지 포맷 외) 추가
```

---

## 11. 작업 시작 전 체크리스트

1. 어느 레이어 변경인가? → 해당 레이어 파일에만 손댄다.
2. 스키마 변경? → `init_schema()` 멱등성 유지, 관련 테스트 통과.
3. 새 repo 함수/provider? → 테스트 먼저(TDD), 어댑터 인터페이스 충족.
4. API 응답 변경? → `types.ts` 동시 갱신.
5. 잠정 상수 변경? → 코드 상수 한 곳 + §7 갱신.

---

## 12. 명령어 레퍼런스

```bash
docker compose up -d                                   # DB
docker compose --profile full up -d                    # 풀 스택 (배포 서버)

python -u -m flight_friend.worker                      # worker (crawl4ai + Chromium 필요)
uvicorn flight_friend.api.main:app --reload            # API (/api/*, /healthz, SPA)

DATABASE_URL=postgresql://flight_user:flight_pass@localhost:5432/flights pytest tests/ -q
cd flight_front/web && npm run dev                     # 프론트 개발 서버
cd flight_front/web && npm run build                   # 프론트 빌드 (API가 dist 서빙)
```
