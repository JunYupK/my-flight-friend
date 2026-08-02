# my-flight-friend — 포트폴리오 정리 문서 (사실 기반)

> 이 문서는 저장소를 직접 조사해 확인한 값만 담는다. 추정/추측은 배제했고,
> 저장소만으로 확인 불가능한 항목(프로덕션 DB·호스트 crontab·런타임 로그·텔레그램 히스토리)은
> `❓미확인`으로 명시했다. 각 항목에는 근거 파일 경로 또는 실행한 명령을 함께 적었다.
>
> 조사 환경: 원격 세션의 fresh clone. **프로덕션 PostgreSQL에 접속 불가**(`DATABASE_URL` 미설정,
> `pg_isready localhost:5432` → no response). 따라서 행 수·수집량·성공률 등 런타임 수치는
> 저장소에서 산출할 수 없다. `scripts/diagnose_db.py`가 이 값들을 뽑는 도구이며, OCI 호스트에서
> 실행해야 한다.
>
> 조사일: 2026-08-02 (시스템 날짜). 최신 커밋: 2026-06-22.

---

## ⚠️ 먼저 읽을 것 — 문서/코드와 실제의 불일치 (면접 리스크)

포트폴리오 원문(`CLAUDE.md`)·`readme.md`·프론트엔드 UI에 **실제 코드와 어긋나는 서술**이 있다.
과장 검증당하기 전에 정리한다. 근거는 각 항에 명시.

| 주장(문서/UI) | 실제(코드) | 근거 |
|---|---|---|
| 데이터 소스 4개: Amadeus, Google Flights, Naver, Skyscanner | **실가동 2개: Google Flights + Naver** | `main.py:16-17` 이 두 개만 import |
| Amadeus REST API collector 구현 | **collector_amadeus.py 없음.** `amadeus==9.0.0`이 `requirements.txt`에 있고 UI에 라벨/색만 존재 | `requirements.txt:1`, `flight_front/web/src/components/DealCard.tsx:88`, `Landing.tsx:120`. `grep collector_amadeus` → 파일 없음 |
| Skyscanner RapidAPI collector | **collector_skyscanner.py는 존재하나 죽은 코드** — `main.py`에서 import 안 됨, `SEARCH_CONFIG["search_months"]`(config에 없는 키)가 없어 early return, 사용 API(`browsequotes v1.0`)는 폐기된 무료 엔드포인트 | `flight_monitor/collector_skyscanner.py:66-70`, `config.py`에 `search_months` 없음 |
| Landing 페이지: "데이터는 Google Flights, Amadeus, Naver 등에서 수집됩니다" | Amadeus 미수집. 사용자에게 부정확 | `flight_front/web/src/components/Landing.tsx:120` |
| "48개 테스트" | **정적 카운트 89개 `def test_` (10개 파일)** | `grep -rEc "def test_" tests/` |
| MCP "3개 query tool 제공" | **현재 11개 `@mcp.tool()`** | `grep -c "@mcp.tool()" mcp_server.py` → 11 |
| "OCI 한국 리전 이전으로 레이턴시 개선" | **git 이력에 리전 이전 커밋 없음.** OCI Korea에서 운영한다는 서술은 있으나 "이전(migration)" 근거 없음 | `git log --grep=리전\|region\|migrat` → 해당 커밋 없음 |
| 개발 시작 "2026-03-03" | **git 최초 커밋 2026-03-23** | `git log --reverse --date=iso` |
| "커밋 80회+" | **총 142 커밋 (non-merge 99)** | `git rev-list --count HEAD` |

> Amadeus/Skyscanner는 "설계했다"가 아니라 "**과거 시도 후 실가동에서 빠졌고 UI/의존성에 잔재가 남았다**"가
> 정확한 서술이다. 면접에서는 "현재 2개 소스 실운영, 나머지는 잔재/미구현"으로 말하는 편이 안전하다.

---

## 1. 프로젝트 메타

### 커밋/기간
| 항목 | 값 | 근거 |
|---|---|---|
| 최초 커밋 | 2026-03-23 (PR #14 merge) | `git log --reverse --date=iso` |
| 최신 커밋 | 2026-06-22 | `git log -1 --date=iso` |
| 개발 기간 | 약 3개월 (2026-03-23 ~ 06-22) | 위 두 값 |
| 총 커밋 | 142 | `git rev-list --count HEAD` |
| non-merge 커밋 | 99 | `git rev-list --no-merges --count HEAD` |
| 최신 커밋 이후 | 2026-07·08 커밋 없음 (조사일 기준 ~6주 정지) | `git log --date=format:%Y-%m` |

**작성자별 커밋 수** (`git shortlog -sne --all`):
| 작성자 | 커밋 |
|---|---|
| Claude `<noreply@anthropic.com>` | 85 |
| 김준엽 (JunYupK) | 46 |
| yongbul | 11 |

**월별 커밋 분포** (`git log --date=format:%Y-%m`):
| 월 | 커밋 |
|---|---|
| 2026-03 | 39 |
| 2026-04 | 33 |
| 2026-05 | 0 |
| 2026-06 | 70 |

> Claude 커밋이 60%(85/142). AI 협업이 커밋 단위로 실체가 있음(§8 참고). 5월 공백 존재.

### 코드 라인 수 (`wc -l`, node_modules/.git 제외)
| 영역 | 파일 수 | 라인 |
|---|---|---|
| Python 전체 | 32 | 6,482 |
| ├ `flight_monitor/` (수집·저장 코어) | 9 | 2,227 |
| ├ `flight_front/api/` (FastAPI + service) | 5 | 1,117 |
| ├ 루트 (`main.py`/`mcp_server.py`/`diagnosis_agent.py`) | 3 | 995 |
| ├ `tests/` | 10 | 1,385 |
| └ `scripts/` (.py) | 3 | 758 |
| TypeScript/TSX 전체 | 19 | 2,978 |
| └ `flight_front/web/src/components/*.tsx` | 15 | 2,443 |
| SQL / CSS / sh / yml | 각 1·1·2·3 | — |

> `readme.md:16`은 "Python 3,000줄 + TypeScript 2,200줄"이라 적혀 있으나, 측정값은 Python 6,482
> (테스트·스크립트 포함) / TS 2,978. 코어만 세도 Python은 3,000줄을 넘는다. README 수치는 초기값(2026-03).

### 디렉토리 트리 (depth 3, 노이즈 제외)
```
my-flight-friend/
├── main.py                    # 수집 파이프라인 진입점
├── mcp_server.py              # FastMCP SSE 서버 (11 tools)
├── diagnosis_agent.py         # 자동 진단 에이전트 (Anthropic native MCP client)
├── docker-compose.yml         # 단일 compose, profiles: full/collect
├── Dockerfile / .collector / .mcp
├── Caddyfile
├── AGENTS.md / CLAUDE.md / readme.md / ISSUES.md / TODOS.md
├── requirements.txt / ruff.toml / .env.example
├── flight_monitor/            # 수집·저장 코어
│   ├── collector_google_flights.py / collector_naver.py / collector_skyscanner.py(죽은 코드)
│   ├── crawler_utils.py / offer_utils.py
│   ├── storage.py / config.py / config_db.py / notifier.py
├── flight_front/
│   ├── api/  (main.py, deals_cache.py, run_state.py, search_service.py)
│   └── web/  (src/components/*.tsx, api.ts, types.ts, ...)
├── tests/                     # 10개 파일
├── scripts/                   # collect_and_diagnose.sh, diagnose_db.py, repopulate_deals.py, bench_gf_resource_block.py, diagnose_deals.sql
└── .github/workflows/         # ci.yml, deploy.yml
```

### 공개/URL
- **GitHub**: `https://github.com/JunYupK/my-flight-friend` (`readme.md:5` 배지 URL). 공개/비공개 여부는 저장소만으로 단정 불가 → `❓미확인`.
- **서비스 도메인**: `flight-friend.com` (`.claude/hooks/session-start.sh:23`, `deploy.yml:80` 기본값). 실제 라이브 접속 가능 여부 `❓미확인`.

---

## 2. 시스템 아키텍처

### 컨테이너 구성 (`docker-compose.yml`)
profiles로 분기: `up -d`(기본)=db+redis만 / `--profile full`=배포 풀스택 / `--profile collect`=크론 1회성 수집.

| 서비스 | 이미지/빌드 | 프로파일 | 포트 | 볼륨 | 역할 |
|---|---|---|---|---|---|
| `db` | postgres:16-alpine | (기본) | 5432:5432 | `pgdata` | PostgreSQL |
| `redis` | redis:7-alpine | (기본) | 6379:6379 | — | 캐시 (미설정 시 in-memory fallback) |
| `app` | `Dockerfile` (multi-stage) | full | expose 8000 | `/:/hostfs:ro` | FastAPI + React SPA |
| `collector` | `Dockerfile.collector` | **collect 전용** | — | — | crawl4ai + Playwright 수집 (1회성) |
| `mcp` | `Dockerfile.mcp` | full | expose 8001 | — | FastMCP SSE 서버 |
| `caddy` | caddy:2-alpine | full | 80/443/443-udp | `Caddyfile`(ro), `caddy_data`, `caddy_config` | 리버스 프록시 + 자동 HTTPS |

- collector가 `collect` 전용인 이유는 코드 주석에 명시: full에 넣으면 배포 시 `main.py`가 flock 우회로 자동 실행돼 cron run과 중첩됨 (`docker-compose.yml:69-71`).
- `app` 헬스체크는 curl/wget 없이 stdlib `urllib`로 `/api/config` 확인 (`docker-compose.yml:57-63`).
- `app`이 호스트 루트를 `:ro` 마운트하는 건 `/api/monitor/system` 디스크 지표용 (`docker-compose.yml:46-48`).

### Caddy 라우팅 (`Caddyfile`)
```caddyfile
{$DOMAIN} {
	handle_path /mcp/* {
		@no_auth not header Authorization "Bearer {env.MCP_API_KEY}"
		respond @no_auth 401
		reverse_proxy mcp:8001
	}
	reverse_proxy app:8000
}
```
→ `/mcp/*`는 Bearer 토큰 없으면 401, 나머지는 app으로. 자동 HTTPS.

### 레이어 구조 ↔ 실제 파일 (`AGENTS.md §2`)
```
Types/Config  →  Repository  →  Service  →  Router  →  UI
  config.py       storage.py    (service/)  api/main.py  web/src/
```
| 레이어 | 파일 |
|---|---|
| Config | `flight_monitor/config.py`, `config_db.py` |
| Repository | `flight_monitor/storage.py` |
| Collector | `flight_monitor/collector_*.py` |
| Service | `flight_front/api/deals_cache.py`, `run_state.py`, `search_service.py`, `mcp_server.py` |
| Notifier | `flight_monitor/notifier.py` |
| Router | `flight_front/api/main.py` |
| UI | `flight_front/web/src/` |

### 의존성 방향 규칙이 정의된 곳
- **문서**: `AGENTS.md §2`(허용/금지 표), `§8`(금지사항).
- **기계 강제**: `tests/test_architecture.py` — `ast` 정적 분석으로 CI에서 항상 검증(§7 인용).

### 배포 환경 스펙
- `readme.md`/`AGENTS.md`: **OCI 한국 리전, 단일 docker-compose**.
- `deploy.yml:117`은 **ARM64** 빌드 언급("playwright install … ARM64에서 캐시 미스 시 10분+") → OCI Ampere(ARM) 인스턴스로 추정되나 **인스턴스 타입/OS/vCPU/RAM은 저장소에 없음** → `❓미확인`.

### 아키텍처 다이어그램 (실제 구성 기준)
```mermaid
graph TB
    User["사용자 브라우저"]
    Cron["호스트 cron (3h)<br/>collect_and_diagnose.sh"]
    GF["Google Flights"]
    NV["flight.naver.com"]
    TG["Telegram / Discord"]
    ANTH["Anthropic API<br/>(claude-sonnet-4-6)<br/>native MCP client"]

    subgraph OCI["OCI Korea (docker-compose)"]
        Caddy["caddy<br/>:80/:443 자동HTTPS"]
        App["app<br/>FastAPI+React :8000"]
        MCP["mcp<br/>FastMCP SSE :8001"]
        Coll["collector (1회성)<br/>crawl4ai+Playwright"]
        Diag["diagnosis_agent.py<br/>(collector 이미지)"]
        DB[("PostgreSQL 16")]
        Redis[("Redis 7")]
    end

    User -->|HTTPS| Caddy
    Caddy -->|/*| App
    Caddy -->|/mcp/* +Bearer| MCP
    App --> DB
    App --> Redis
    Cron -->|1) run --rm collector main.py| Coll
    Cron -->|2) run --rm collector diagnosis_agent.py| Diag
    Coll -->|crawl4ai + JS injection| GF
    Coll -->|crawl4ai + JS injection| NV
    Coll -->|save_legs / materialize_deals| DB
    Coll -->|목표가 이하 offer| TG
    Diag -->|Anthropic API 호출| ANTH
    ANTH -->|SSE /mcp/sse over Caddy| MCP
    MCP -->|SQL 조회 / 소스읽기| DB
    ANTH -->|send_telegram_report tool| TG

    style OCI fill:#eef4ff,stroke:#4169E1
```

> 주의: `readme.md`의 다이어그램은 MCP를 "Claude Desktop → stdio"로 그렸으나, 실제 배포 경로는
> **diagnosis_agent.py가 Anthropic API의 native MCP client로 Caddy 경유 SSE(`/mcp/sse`)에 붙는다**
> (`diagnosis_agent.py:137,155-161`). Claude Desktop(stdio)은 별도 로컬 사용 시나리오.

---

## 3. 데이터 모델과 규모

### 테이블 스키마 (`flight_monitor/storage.py::init_db`)
9개 테이블 + 1개 뷰. 역할 표는 `AGENTS.md §5`.

| 테이블 | 역할 | 쓰기 경로 | 주요 인덱스 |
|---|---|---|---|
| `raw_legs` | 수집 원본 append-only 로그 (90일 보존) | `save_legs()` | `(destination,date,direction)`, `(collected_at)`, `(source,dest,date,dir)` |
| `flight_legs` | 소스별 현재 최저가 (UPSERT, 트리거 소스) | `save_legs()` | unique `uq_flight_legs_identity`(9컬럼), 부분인덱스 out/in ×2 (+checked_at 변형 ×2) |
| `deals` | 왕복 조합 사전계산(materialized) | `save_deals()` | `(destination,departure_date,min_price)`, `(source,destination)` |
| `price_events` | 가격 변동 이벤트 (DB 트리거 자동 기록) | **트리거 전용, 직접 INSERT 금지** | `(destination,date,direction)` |
| `price_history` | 레거시 왕복 기록 (deprecated, 신규 쓰기 없음, DROP 예정) | `save_prices()` | dest/dep/ret, checked_at, advance 부분인덱스 |
| `alert_state` | 알림 dedup/cooldown (PK=`destination\|YYYY-MM`) | `record_alert()` | PK |
| `airports` | 목적지 공항 설정 (code, name, tfs_out, tfs_in) | 웹 UI API / `config_db.py` | PK=code |
| `app_config` | JSONB 설정 (key=`search_config`) | `write_config()` | PK=key |
| `collection_runs` | 수집 실행 이력 (좀비 run 청소) | `start/finish_collection_run()` | PK |
| `v_best_observed` (뷰) | price_history 집계 뷰 (레거시) | — | — |

**핵심 컬럼** (발췌):
- `flight_legs`: `source, origin, destination, date, direction('out'/'in'), airline, dep_time, arr_time, duration_min, stops, dep_airport, arr_airport, price, best_source, checked_at`
- `deals`: `origin, destination, departure_date, return_date, stay_nights, trip_type, source, out/in_airline, is_mixed_airline, out/in_dep/arr_time, out/in_stops, out/in_url, out/in_price, min_price, last_checked_at`

**이벤트 소싱 트리거** (`storage.py:319-343`):
```sql
CREATE OR REPLACE FUNCTION record_price_change() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.price <> OLD.price THEN
        INSERT INTO price_events (destination, date, direction, airline, dep_time,
            source, old_price, new_price, changed_at)
        VALUES (NEW.destination, NEW.date, NEW.direction, NEW.airline, NEW.dep_time,
            COALESCE(NEW.best_source, NEW.source), OLD.price, NEW.price, NEW.checked_at);
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
-- AFTER UPDATE ON flight_legs FOR EACH ROW
```

**UPSERT 로직** (`storage.py:498-509`): `ON CONFLICT DO UPDATE SET price = LEAST(EXCLUDED.price, flight_legs.price)`, `best_source`는 더 싼 쪽 소스로 갱신.

### 규모 (행 수·수집량·노선 수 등)
| 항목 | 값 | 상태 |
|---|---|---|
| 각 테이블 현재 행 수 | — | `❓미확인` — 프로덕션 DB 접속 불가 |
| 수집 대상 노선 수 | — | `❓미확인` — `config.py:8` `JAPAN_AIRPORTS={}` (빈 dict), **런타임에 `airports` 테이블에서 로드**(`config_db.py:26-36`). 저장소에 목적지 목록 없음 |
| 날짜 조합 수 | 파라미터: `search_range_months=12`, `stay_durations=[3,4,5]`, `topk_per_date=5`, `sweep_tick_months=3` (`config.py:15-47`). 실제 조합 수는 노선 수×날짜에 의존 → `❓미확인` |
| 수집 시작일~현재, 누적 수집 건수, 일평균 | — | `❓미확인` — 런타임 데이터 |

> **확인 방법**: OCI 호스트에서 `python scripts/diagnose_db.py` 실행. 이 스크립트가
> collection_runs 이력, raw_legs 원본량, flight_legs 상태, 날짜별 커버리지, airports 설정을 출력한다
> (`scripts/diagnose_db.py` section 1·2·4·8·9). 또는:
> ```sql
> SELECT 'raw_legs', count(*) FROM raw_legs
> UNION ALL SELECT 'flight_legs', count(*) FROM flight_legs
> UNION ALL SELECT 'deals', count(*) FROM deals
> UNION ALL SELECT 'price_events', count(*) FROM price_events;
> SELECT count(*) FROM airports;                          -- 노선 수
> SELECT min(collected_at), max(collected_at) FROM raw_legs;  -- 수집 기간
> ```

---

## 4. 수집 파이프라인

### crawl4ai 설정값 (실제 값)
공통 유틸은 `crawler_utils.py`, 소스별 `CrawlerRunConfig`는 각 collector에 있음.

**BrowserConfig** (GF·Naver 동일, `collector_google_flights.py:513-522`, `collector_naver.py:270-279`):
```python
BrowserConfig(
    headless=True,
    viewport={"width": 1920, "height": 1080},
    extra_args=[
        "--disable-blink-features=AutomationControlled",  # 자동화 탐지 회피
        "--no-sandbox",           # Docker/CI root 실행 필수
        "--disable-dev-shm-usage",  # /dev/shm 64MB 제한 우회
        "--disable-gpu",
    ],
)
```

**CrawlerRunConfig**:
| 파라미터 | Google Flights | Naver | 근거 |
|---|---|---|---|
| `magic` | True | True | collector `_fetch_route` |
| `js_code` | `[make_scroll_js(), _extract_js()]` | 동일 | scroll 5회 + DOM 추출 |
| `wait_for` | `js:() => !!document.querySelector('li.pIav2d')` | `div[class*="combination_ConcurrentItemContainer"]` | 셀렉터 |
| `delay_before_return_html` | 4.0s | 8.0s | Naver가 더 느림 |
| `cache_mode` | `bypass` | `bypass` | 항상 신규 |
| `page_timeout` | `gf_page_timeout_ms=15000` (fast-fail) | `page_timeout_ms=30000` | `config.py:43-46` |

**스크롤 JS** (`crawler_utils.py:62-75`): 무한스크롤 최대 5회, 각 1.5s 대기, 높이 불변 시 중단.

**동시성/배치** (`config.py`, `crawler_utils.py`):
- `_BATCH_SIZE=5` (arun_many 배치, OCI 메모리 한도 고려 — `AGENTS.md §7`)
- `parallel_airports=3` (공항 asyncio.Semaphore)
- `request_delay=1.0s` (배치 간)
- 가격 유효범위 필터: `20,000 ≤ price ≤ 3,000,000` (JS injection 단계, `collector_google_flights.py:237`, `collector_naver.py:75`)
- `get_collected_today()`로 오늘 이미 수집한 (dest,date,direction) 스킵 (중복 요청 방지)

**sweep 분산** (`crawler_utils.py:25-59` `compute_sweep_window`): 12개월을 `sweep_tick_months=3` 단위 슬라이스로 나눠 cron tick마다(시각에서 stateless 유도) 근미래부터 round-robin으로 한 조각씩 수집. 첫-run-of-day의 12개월 full-sweep이 3h 주기를 넘겨 죽던 death spiral 차단.

### 스케줄러 구성
- **crontab 파일은 저장소에 없음** (호스트에 존재). 권장 entry는 `AGENTS.md §7`·`scripts/collect_and_diagnose.sh:5`에 명시:
  ```
  0 */3 * * * cd /path/to/my-flight-friend && bash scripts/collect_and_diagnose.sh >> /var/log/collector.log 2>&1
  ```
- 실행 주기: **3시간** (`0 */3 * * *`). 백업 cron(매일 03:00 KST `pg_dump`)은 `readme.md:273`에만 언급, 스크립트는 저장소에 없음 → `❓미확인`.
- 실행 방식: `collect_and_diagnose.sh`가 ① flock 직렬화 → ② 좀비 컨테이너 청소 → ③ `timeout 150m docker compose --profile collect run --rm collector python main.py` → ④ `... diagnosis_agent.py` 순서.
- **실제 호스트 crontab 등록 여부는 저장소에서 확인 불가** → `❓미확인`.

### 1회 수집 사이클 소요 시간
- `❓미확인` — 런타임 로그(`/var/log/collector.log`) 또는 `collection_runs.duration_sec` 필요. `ISSUES.md #2`는 "첫-run-of-day는 12개월×공항×양방향 → 수 시간 소요"라고만 정성 기술. 정량 실측은 `SELECT status, duration_sec FROM collection_runs ORDER BY started_at DESC` 로 확인.

### 수집 성공률 / 실패 유형
- `❓미확인 (로그 미보존)` — 저장소에 수집 로그가 커밋돼 있지 않다. `collection_runs.status`(`success`/`partial`/`error`/`running`)와 `error_log`로 산출 가능.
- **산출 방법**: `SELECT status, count(*) FROM collection_runs GROUP BY status;` (성공률), `error_log` 텍스트 분류(실패 유형). `ISSUES.md #1`이 알려진 실패 유형을 정성 기술: "GF 간헐적 차단/타임아웃 → 특정 run 0건 (Naver는 정상)".

### 크롤링 대상 사이트와 파싱 전략
| 소스 | 진입 방식 | 파싱 전략 | 카드 셀렉터 |
|---|---|---|---|
| Google Flights | `search?tfs=` protobuf URL (템플릿에서 날짜만 치환, `_build_tfs_url`) | headless + JS injection → `#__fl__` div에 JSON 주입 후 정규식 추출 (`_parse_flight_cards`) | `li.pIav2d`, 가격 `.YMlIz.FpEdX span[aria-label]` |
| Naver | 편도 검색 URL(`tripType=OW`, `_build_naver_url`) | 동일 패턴 → `#__nv__` div | `div[class*="combination_ConcurrentItemContainer"]`, 가격 `i[class*="item_num"]` |

**Protobuf 예약 URL 생성** (`collector_google_flights.py:53-146`): `tfs=` 파라미터를 varint/length-delimited로 직접 인코딩(`_pb_varint`/`_pb_field`/`_build_booking_tfs`)해 편명 단위 예약 페이지 직링크 생성.

---

## 5. Diagnosis Agent ★가장 중요

### 운영 여부
- **코드/문서상 크론에 연결됨**: `scripts/collect_and_diagnose.sh:42`가 수집 직후 `diagnosis_agent.py`를 실행하며, `AGENTS.md §7`이 이 래퍼를 크론 entry로 규정. `main.py` 실패(exit≠0)해도 진단은 항상 실행(`|| true`, `collect_and_diagnose.sh:7`).
- **구축 커밋**: 2026-06-09 `feat: 크롤링 데이터 품질 자동 진단 시스템 구축`.
- **OCI 호스트의 실제 crontab 등록·현재 가동 여부는 저장소에서 확인 불가** → `❓미확인`. (확인: 호스트에서 `crontab -l`, `/var/log/collector.log`의 "=== 진단 시작 ===" 라인.)

### 사용 모델 / 호출 방식 / 트리거
- **모델**: `claude-sonnet-4-6` (`diagnosis_agent.py:145`).
- **호출**: Anthropic Python SDK `client.beta.messages.create(...)` + **native MCP client** (`betas=["mcp-client-2025-04-04"]`, `mcp_servers=[{type:"url", url:"https://{DOMAIN}/mcp/sse", authorization_token: MCP_API_KEY}]`) (`diagnosis_agent.py:144-162`). `max_tokens=4096`.
- **트리거**: 크론 래퍼가 수집 완료 후 실행. 진단 시작 전 `_wait_for_collection()`으로 최근 run이 `running`이면 최대 15분 대기(30분 초과 시 크래시 의심으로 강제 진행) (`diagnosis_agent.py:73-121`).

### MCP 서버 구성
- **transport**: **SSE** (`mcp_server.py:19,653` `FastMCP("flight-friend", host="0.0.0.0", port=8001)`, `mcp.run(transport="sse")`). Caddy가 `/mcp/*`를 `mcp:8001`로 프록시하며 Bearer 토큰 검증(`Caddyfile`).
- **정의된 툴 전체 (11개, `@mcp.tool()`)**:

| # | 툴 | 시그니처 | 역할 |
|---|---|---|---|
| 1 | `get_best_deals` | `(destination?, month?, max_stay_nights?, limit=10)` | flight_legs out/in 조합 왕복 최저가 |
| 2 | `get_price_history` | `(destination, departure_date, direction="both")` | price_events 가격 변동 이력 |
| 3 | `explain_deal` | `(destination, departure_date, return_date)` | 특정 왕복 상세(현재가/이력/소스비교/all-time-low) |
| 4 | `compare_sources` | `(destination, departure_date)` | Naver vs GF 소스별 가격 비교 |
| 5 | `get_calendar_prices` | `(destination, month, direction="out")` | 월별 날짜별 최저가 |
| 6 | `get_recent_deals` | `(hours=24, destination?, max_price_krw?, limit=20)` | 최근 N시간 수집 딜 |
| 7 | `find_cheapest_month` | `(destination?)` | 목적지별 월별 최저/평균가 |
| 8 | `get_collection_status` | `(limit=10)` | **수집 이력 + 이상 자동 감지** |
| 9 | `get_collection_stats` | `(hours=6, stale_threshold_hours=6)` | **노선별 수집량 급감 + stale 감지** |
| 10 | `read_source_file` | `(path, start_line?, end_line?)` | **화이트리스트 소스 읽기** (11개 파일 한정, path traversal 방어) |
| 11 | `send_telegram_report` | `(message)` | 텔레그램 리포트 발송 |

> 툴셋에 **쓰기/수정/배포 능력이 없다** — DB는 read-only, 소스는 화이트리스트 read-only(`_ALLOWED_SOURCE_FILES`, `mcp_server.py:557-569`), 유일한 부수효과는 텔레그램 발송. 이것이 human-in-the-loop의 코드적 근거(아래).

### 시스템 프롬프트 원문 (`diagnosis_agent.py:21-70`, 그대로 인용)
```text
당신은 ICN↔일본 항공권 모니터링 시스템의 자동 진단 에이전트입니다.
크롤링 완료 후 데이터 품질을 점검하고 텔레그램으로 리포트를 보냅니다.

[시스템 구조]
- 수집 소스: GoogleFlights (crawl4ai headless), Naver (crawl4ai GraphQL)
- 실행: 3시간마다 cron → docker compose --profile collect run --rm collector python main.py
- DB 흐름: raw_legs(수집 원본, append-only) → flight_legs(현재 상태, UPSERT) → price_events(가격 변동, trigger 자동 기록)
- 수집 이력: collection_runs 테이블 (status: "success" | "partial" | "error" | "running")
- 파싱 함수:
  - _parse_flight_cards() — collector_google_flights.py:323, DOM regex + JSON.loads, 실패 시 [] 반환
  - _parse_cards()        — collector_naver.py:131, 동일 패턴
  - crawl_one_way_batches() — crawler_utils.py:32, 공통 배치 크롤 루프 (arun_many)
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
```
> 프롬프트 오기 1건: 시스템 구조에 "Naver (crawl4ai GraphQL)"이라 적혀 있으나, 실제 Naver collector는
> GraphQL이 아니라 검색결과 페이지 DOM 파싱이다(`collector_naver.py`). (포트폴리오 CLAUDE.md의
> "Naver GraphQL" 서술과 같은 계열의 부정확.)

### 진단 항목 전체 (실제 구현된 체크)
**(A) 자동 에이전트가 쓰는 프로그래밍 체크** — `mcp_server.py`:
- `get_collection_status` 이상 감지 (`mcp_server.py:454-480`):
  - `running` 30분 초과 → "크래시 의심"
  - `status='error'` → error_log 앞 200자 첨부
  - `total_saved==0` (running 아님) → "수집 0건"
  - 최근 2회 연속 error → "연속 error"
- `get_collection_stats` (`mcp_server.py:483-554`):
  - **수집량 급감**: 현재 윈도우 vs 직전 동일 윈도우 raw_legs count 비교 → `drop_rate_pct`
  - **stale 노선**: flight_legs.checked_at 기준 `stale_threshold_hours`(기본 6h) 초과 노선

**(B) 수동 진단 스크립트** — `scripts/diagnose_db.py` (사람이 OCI에서 실행, 10개 섹션):
1 수집 실행 이력 / 2 raw_legs 원본 / **3 raw_legs NULL 및 이상치** / 4 flight_legs 상태 / 5 price_events / 6 price_history / **7 raw_legs↔flight_legs 정합성** / 8 날짜별 커버리지 / 9 airports 설정 / **10 Naver vs Google 가격 편차**.

> "중복" 체크는 (A)/(B) 어디에도 명시적 항목으로 없음 — 중복은 `flight_legs`의 unique index(`uq_flight_legs_identity`)와 `get_collected_today()` 스킵으로 **사전 방지**하는 구조.

### 에이전트가 실제로 탐지한 이상 사례
- **`❓미확인 — 로그 미보존`**. 판단 근거: ① 수집/진단 로그는 호스트 `/var/log/collector.log`로 나가며 **저장소에 커밋돼 있지 않다**(리포지토리 내 `*.log` 0건). ② 텔레그램 리포트 히스토리는 외부(텔레그램 채널)에 있어 저장소에서 접근 불가. → "탐지 이력 없음"이라 단정할 수 없고, "**히스토리가 저장소에 보존되지 않아 확인 불가**"가 정확.
- **확인 방법**: 호스트 `/var/log/collector.log`에서 "데이터 이상 감지" grep, 또는 텔레그램 채널의 🚨 리포트. `collection_runs`에서 `status IN ('error','partial')` 또는 `total_saved=0` 행이 실제 이상 이벤트 근거.
- 참고: `ISSUES.md #1`이 "GF 간헐적 0건 수집" 실제 현상을 기록하고 있어, 진단 대상 이벤트 자체는 운영 중 발생했음을 정성적으로는 알 수 있다(단 에이전트 리포트 원문은 미보존).

### 왜 완전 자동 수정이 아니라 human-in-the-loop인가 (근거)
- **코드 근거**: MCP 툴셋에 파일 쓰기·배포·코드수정 툴이 전혀 없다. `read_source_file`은 화이트리스트 read-only + path traversal 방어(`mcp_server.py:572-620`). 유일한 부수효과는 텔레그램 발송.
- **프롬프트 근거**: 리포트 마지막이 `[Claude Code 지시문] > (한 줄...)` — 에이전트는 **사람/Claude Code가 실행할 한 줄 지시를 생성**할 뿐 직접 고치지 않는다(`diagnosis_agent.py:68-69`).
- 즉 설계상 **감지·진단·리포트까지 자동, 수정은 사람이 트리거**하는 구조가 코드로 강제돼 있다.

---

## 6. 운영 트러블슈팅 사례 (시간순, git/코드/문서 근거)

### 사례 1 — 수집 run 중첩 누적 (death spiral 지혈) · 2026-06-17
- **증상**: 첫-run-of-day가 12개월×공항×양방향을 한 번에 수집해 3h cron 주기를 초과 → 다음 tick이 이전 run 위에 겹쳐 실행되며 run이 무한 누적, `save_deals` 도달 전 죽어 데이터 0건.
- **원인 분석**: cron이 `docker compose run`을 직접 호출 → 직렬화 부재. 강제 종료로 `finish_collection_run`이 안 불려 `running` 좀비 run 박제.
- **해결**: `scripts/collect_and_diagnose.sh`에 `flock -n`(`/tmp/my-flight-friend-collector.lock`) 직렬화 + `timeout 150m` hard timeout + 진입 시 좀비 컨테이너 `docker rm -f` 청소. `start_collection_run()`이 1h 넘게 `running`인 row를 `error`로 마감(`storage.py:711-729`). GF는 `gf_page_timeout_ms=15000` fast-fail 분리.
- **결과**: 중첩 누적 차단(정성). 정량 전후 수치 `❓미확인`. 근거: 커밋 `fix(collector): 수집 run 중첩 누적 방지 (hard timeout + GF fast-fail)`, `ISSUES.md`, `AGENTS.md §7`.

### 사례 2 — 12개월 full-sweep을 cron tick에 분산 · 2026-06-19
- **증상**: 사례 1의 근본 원인(1 run이 너무 큼)이 지혈 후에도 남아 run 길이 과다.
- **해결**: `compute_sweep_window()`로 12개월을 3개월 슬라이스로 나눠 tick마다 하나씩(stateless, 시각 유도) round-robin 수집. `save_deals`를 `(source,destination,departure_date)` 단위 DELETE→INSERT 원자 교체로 바꿔 슬라이싱해도 다른 달 deal 보존.
- **결과**: 첫-run 크기 1/num_slices로 축소(정성). 근거: 커밋 `perf(collector): 12개월 full-sweep을 cron tick에 분산 (death spiral 차단)`, `crawler_utils.py:25-59`.

### 사례 3 — 알림 폭주 (하루 1000건+) · 2026-06-17
- **증상**: 날짜×항공사 조합마다 알림이 나가 하루 1000건+ 폭주.
- **해결**: `make_alert_key()`를 `destination|YYYY-MM` 단위로 집약, `main.py`가 목표가 이하 offer를 (목적지,출발월)별 최저가 1건으로 축소 후 알림. `should_notify()` 쿨다운(12h)/가격하락(15,000원↓) dedup.
- **결과**: 알림 단위 대폭 축소(정성). 근거: `ISSUES.md`(하루 1000건+ 폭주 해결), `storage.py:663-694`, `main.py:96-110`.

### 사례 4 — `/api/results` 카테시안 조인 cold miss → deals 사전계산 · 2026-06(및 04~06 캐시 작업)
- **증상**: `/api/results`가 flight_legs를 매 요청 카테시안 조인 → 3시간마다(수집 후 캐시 무효화) cold miss 5~10초.
- **해결**: 수집 시 `combine_roundtrips` 결과를 `deals` 테이블에 materialize(`save_deals`/`materialize_deals_for_route`), 읽기는 인덱스 조회로 전환. 추가로 무거운 read 엔드포인트 Redis 캐시(`/api/monitor/coverage` TTL 5분, `/api/price-history` timeline TTL 1h).
- **결과**: 카테시안 조인 제거(정성). "5~10초"는 `CLAUDE.md` 포트폴리오 서술값 → 저장소 정량 근거 `❓미확인`. 근거: 커밋 `deals 사전계산 테이블`(2026-06), `AGENTS.md §5/§7`, `storage.py:565-622`.

### 사례 5 — 배포 거짓 실패 / 502 (Caddy upstream 재해석) · 2026-04~06
- **증상**: app 재생성으로 컨테이너 IP가 바뀌면 Caddy가 죽은 옛 IP를 물어 502 지속. 헬스체크가 Caddy 경유라 app이 멀쩡해도 "거짓 실패". busybox wget이 `localhost`→IPv6(::1)로 붙어 caddy 영구 unhealthy.
- **해결**: 헬스체크를 app 컨테이너 내부 `:8000` 직격(Caddy 우회)으로 분리 → 배포 후 `caddy restart`로 upstream 재해석 → 도메인 경유 `--resolve` 스모크. caddy 헬스체크를 `127.0.0.1:2019`로 명시(IPv4).
- **결과**: 배포 거짓 실패/502 제거(정성). 근거: 커밋 `fix(deploy): 배포 거짓 실패 제거 + caddy 헬스체크/재해석 수정`, `fix(deploy): caddy healthcheck를 127.0.0.1로`, `deploy.yml:51-95`, `docker-compose.yml:132-141`.

### ⚠️ "OCI IP 차단" 이슈에 대한 정확한 상태
- 과제는 "OCI IP 차단 이슈를 반드시 상세히"라 했으나, **git/코드/문서에 "IP 차단을 탐지→우회 전략→전후 성공률"로 해결한 근거가 없다.**
- 저장소가 말하는 실제 상태(`ISSUES.md #1`): "GF가 **간헐적으로 차단/타임아웃**되어 특정 run에서 0건 반환(Naver는 정상)." 그리고 **후속(남음)**으로 "차단 원인(DOM 셀렉터 드리프트 vs 안티봇) 진단 + 실패 재시도 정책" — 즉 **원인 규명·우회 전략은 미완(open issue)**.
- 관련 대응은 두 갈래: (a) `gf_page_timeout_ms=15s` fast-fail로 차단 시 run 시간 폭증만 완화(전략적 우회는 아님), (b) `bench_gf_resource_block.py`로 `text_mode`(이미지/미디어 차단)의 속도·정확도 A/B를 "실제 OCI IP"에서 측정하는 **벤치 스크립트만 존재**(채택/전후 성공률은 미기록).
- **정직한 서술**: "GF 간헐 차단은 인지·완화(fast-fail)했고 진단 도구(text_mode 벤치, drop/stale 감지)를 갖췄으나, IP 차단 자체의 근본 우회는 미해결 open issue다." 전후 성공률 수치는 `❓미확인(로그 미보존)`.

---

## 7. 코드 품질 / 아키텍처 규율

### 레이어 위반 감지 테스트 (`tests/test_architecture.py`, 7개)
`ast` 정적 분석만 사용 → DB·크롤러 없이 CI에서 항상 실행. 검증:
1. `test_storage_does_not_import_fastapi` — Repository가 fastapi/starlette import 금지
2. `test_collectors_do_not_import_fastapi`
3. `test_storage_is_lowest_layer` — storage가 상위(collector/service/router) import 금지
4. `test_router_does_not_import_collectors`
5. `test_services_do_not_import_router` — 역방향 금지
6. `test_no_new_direct_sql_in_router` — `_GET_CONN_ALLOWLIST` 밖 새 엔드포인트의 `get_conn()` 직접 호출 차단
7. `test_no_stale_allowlist` — 마이그레이션 끝난 함수는 allowlist에서 반드시 제거(래칫 — 한 방향으로만 풀림)

동작 예 (allowlist 래칫, `test_architecture.py:132-140,185-191`):
```python
_GET_CONN_ALLOWLIST = frozenset({
    "upsert_airport", "delete_airport", "get_monitor_coverage",
    "get_calendar_prices", "get_price_history",  # AGENTS §11 잔여 직접-SQL
})
def test_no_stale_allowlist():
    stale = _GET_CONN_ALLOWLIST - _functions_calling_get_conn(ROUTER)
    assert not stale, f"...마이그레이션 끝났으니 삭제하라: {sorted(stale)}"
```

### 테스트 수 / 커버리지
| 항목 | 값 | 근거 |
|---|---|---|
| 테스트 파일 | 10 | `tests/` |
| `def test_*` 함수 (정적) | **89** | `grep -rEc "def test_" tests/` (파일별: flight_monitor 33, offer_utils 13, search_service 11, sweep_window 8, architecture 7, run_state 5, notifier 4, save_deals 3, deals_cache 3, materialize_deals 2) |
| 문서상 표기 | 48 (`readme.md:16`, `CLAUDE.md`) | 초기값(2026-03), 이후 증가로 실제와 불일치 |
| 커버리지 % | `❓미확인` | coverage 설정/리포트 없음. 다수 테스트가 PostgreSQL 필요(`clean_db` autouse fixture, `AGENTS.md §6`)라 이 환경(DB 없음)에서 실행 불가 |

> 이 조사 환경에서는 `DATABASE_URL` 미설정 + 의존성 미설치라 `pytest`를 실제로 돌려 수를 확정하지 못했다.
> 위 89는 **정적 함수 카운트**다. 실제 pytest 수집 수(파라미터라이즈 포함)는 OCI/CI에서 `pytest --collect-only -q | tail -1`로 확인.

### 린트/포맷
- **ruff** (`ruff.toml`): `target-version=py311`, `flight_front/web` 제외, `E402` 무시(load_dotenv 선실행 패턴). CI에서 `ruff check .` 강제(`ci.yml:48-51`).
- TS: `tsc && vite build`가 빌드 게이트(`package.json:8`), CI에서 `npm run build` 강제.
- Python 코딩 규칙(`AGENTS.md §4`): 타입힌트 필수·`Any` 금지, 신규 collector `arun_many` 배치 강제, collector 개별 실패 로깅 후 계속(raise 금지), 하드코딩 금지.

---

## 8. AI 협업 방식 ★

### 사람이 결정한 영역 vs AI에 위임한 영역
- **커밋 실체**: Claude 85 / 김준엽 46 / yongbul 11 (총 142). AI가 커밋의 60%를 실제로 생성.
- **경계의 코드적 근거**: `AGENTS.md`가 "Claude Code가 이 레포에서 작업할 때 항상 먼저 읽는 하네스 명세서"로, **아키텍처·레이어·DB 규칙·금지사항을 사람이 규정하고 AI는 그 안에서 구현**하는 구조. 규칙은 "테스트와 린터로 기계적으로 강제"(→ `test_architecture.py`, ruff).
- 사람 결정: 레이어 경계·DB 테이블 역할·알림 정책·파일 위치 규칙(`AGENTS.md §2·3·5·8`). AI 위임: 규칙 준수하는 구현·리팩터·버그픽스.

### AGENTS.md/CLAUDE.md에 정의된 AI 작업 규칙 (인용)
`CLAUDE.md`(행동 규범):
```text
## 1. Think Before Coding — Don't assume. Surface tradeoffs. 불명확하면 멈추고 질문.
## 2. Simplicity First — 요청 이상 기능/추상화 금지. 200줄이 50줄이면 다시 써라.
## 3. Surgical Changes — 건드릴 것만. 인접 코드 '개선' 금지. 기존 스타일 준수.
## 4. Goal-Driven Execution — 작업을 검증 가능한 목표로. 테스트로 루프.
```
`AGENTS.md §9`(작업 시작 전 체크리스트): 어느 레이어인가 / DB 스키마 변경 시 `init_db` 멱등성·`TestInitDb` / 새 storage 함수는 TDD / 새 collector는 offer·leg dict 인터페이스 충족 / API 응답 변경 시 `types.ts` 동시 갱신 / 알림 변경 시 `test_notifier` fallback 통과.

### 위임 → 검토 → 수정 패턴이 드러나는 커밋
- **자기 리뷰 반영**: `2026-03-24 fix: 코드 리뷰 이슈 3건 수정`, 최초 커밋이 `PR #14 ... claude/review-project-status`. 브랜치명 다수가 `claude/...` → AI가 브랜치 작업 후 PR 머지.
- **회귀 → 후속 수정 체인** (AI 작업의 반복 교정): `가격 편차 문제 수정 — 캐시 무효화 + 교차 소스 조합 방지`(2026-06-09) ← `out_source/in_source 필드 추가 및 교차 소스 뱃지`(같은 날) 후속. 배포 헬스체크도 `04-14 false-negative 수정 → 04-15 vhost 매칭 실패 수정 → 06-19 거짓 실패 제거`로 여러 라운드 교정.
- **테스트 우회 구멍까지 방어**: `2026-06-18 test: 아키텍처 검사의 import/get_conn 탐지 우회 구멍 차단` — AI가 만든 검사 자체의 허점을 다시 메움.

### 멀티 에이전트 개발 체계
- **현재 서브에이전트 정의 없음**. `.claude/`에는 `hooks/session-start.sh`(MCP 자동 연결)와 `settings.json`(hook 등록)만 존재. `.claude/agents/` 디렉토리 **없음** → **"도입 예정"**.
  - 근거: `find .claude -maxdepth 3` → `hooks/session-start.sh`, `settings.json` 뿐.
  - 참고: 저장소 루트의 `diagnosis_agent.py`는 "운영 데이터 진단" 에이전트지 "개발 서브에이전트"가 아님.

#### 제안 — 이 저장소에 맞는 4개 서브에이전트 구성 (`.claude/agents/*.md`)
이 레포는 이미 규칙이 기계로 강제(`test_architecture.py`, ruff)돼 있어, 서브에이전트는 그 규칙을 "리뷰 관점"으로 확장하는 형태가 자연스럽다.

| 에이전트 | 역할 | 이 레포에서의 구체 임무 (프롬프트 골자) |
|---|---|---|
| **비판적 검증 agent** | 구현의 정합성·회귀 검증 | "변경이 `AGENTS.md §2/§8` 레이어 경계를 어기지 않는가. `save_legs`/`save_deals`/트리거 불변식(직접 INSERT 금지)·`init_db` 멱등성을 깨지 않는가. 새 storage 함수에 `clean_db` 테스트가 동반됐는가. offer/leg dict 인터페이스 필수필드 누락 없는가"를 diff 기준으로 지적. |
| **오버엔지니어링 판단 agent** | 단순성 게이트 (`CLAUDE.md §2`) | "요청 범위를 넘는 추상화/설정가능성/불가능 시나리오 방어가 있는가. 200줄이 50줄로 되는가. 단일 사용처에 추상화가 있는가"를 판단. 이 레포의 `search_service.py` 분리 같은 '정당한 분리' vs 과설계를 구분. |
| **기획자 agent** | 요구 → 검증가능 목표 변환 (`CLAUDE.md §4`) | 새 기능을 "테스트 먼저 → 통과" 형태의 성공기준으로 분해. `ISSUES.md`/`TODOS.md`의 open item(가격_history DROP, flight_legs 13개월 보존, GF 재시도 정책)을 우선순위화. |
| **UI/UX agent** | 프론트 일관성 (`AGENTS.md §4 TS/React`) | "컴포넌트가 직접 `fetch` 안 하고 `api.ts` 경유하는가, `as`/`any` 금지·`types.ts` 사용, `useState/useEffect` 유지(전역상태 라이브러리 금지)"를 검사. deals/캘린더/트렌드 화면의 신선도 배지·상대시간 표기 일관성 리뷰. |

구성 방식: 각 에이전트는 read-only 코드 리뷰 관점(수정은 사람/메인 에이전트가 트리거)으로 두면, diagnosis_agent와 동일한 human-in-the-loop 철학과 일치한다.

---

## 9. 자료 (문서에 넣을 이미지)

### 현재 저장소에 있는 이미지
- **없음**. `find -iname '*.png'/'*.jpg'/'*.svg'/...` → 0건. `readme.md:18-20`에 스크린샷 자리(`docs/screenshot-deals.png`)가 주석으로 비어 있음. `docs/` 디렉토리도 이 문서 생성 전엔 없었음.

### 캡처해두면 좋은 화면 (제안 — 라우트는 `readme.md:99-106` 기준)
| 우선 | 캡처 대상 | 이유 |
|---|---|---|
| ★★★ | `/deals` 딜 목록 (목적지×월 필터, 소스/트립타입 뱃지) | 핵심 결과물. 교차소스·편도조합 뱃지 보이게 |
| ★★★ | 텔레그램 진단 리포트 🚨 실제 캡처 (이상 감지 1건) | §5 최중요 근거. 탐지→가설→지시문 형식이 그대로 보임 |
| ★★★ | `/monitor` 수집 실행 이력 (status/소요시간/error_log) | 안정성·운영 스토리 증거 (duration_sec 실측값 노출) |
| ★★ | `/search` 캘린더 가격 히트맵 | 날짜별 최저가 시각화 |
| ★★ | `/trends` 가격 추이 차트 (Recharts) | 이벤트 소싱(price_events) 결과 시각화 |
| ★★ | GitHub Actions CI/deploy 성공 로그 (헬스체크 통과) | CI/CD 파이프라인 실체 |
| ★ | `scripts/diagnose_db.py` 실행 출력 | 데이터 규모·정합성 수치를 표로 |
| ★ | `/settings` 공항 CRUD + WebSocket 실시간 수집 로그 | 실시간 로그 스트리밍 기능 |

---

## 10. 한계와 다음 단계

### 알려진 버그 / 기술 부채 (`ISSUES.md`, `TODOS.md`, `AGENTS.md §11`)
1. **GF 간헐 0건 수집** — 차단/타임아웃 원인(안티봇 vs DOM 드리프트) 미규명, 실패 재시도 정책 없음 (`ISSUES.md #1`).
2. **수집 run 시간 과다** — sweep 분산으로 지혈했으나 근본 단축 미완 (`ISSUES.md #2`).
3. **`price_history` 테이블 DROP 대기** — 신규 쓰기 없음(dead, 마지막 쓰기 2026-04-03), 관련 `save_prices()`/DDL/`v_best_observed` 뷰 정리 필요 (`TODOS.md`).
4. **`flight_legs` 무한 증가** — 출발 지난 과거 날짜 row가 UPSERT 갱신 안 돼 영구 잔류, 13개월 보존 cron 미도입 (`TODOS.md`).
5. **직접-SQL 잔여 엔드포인트** — `upsert_airport`, `delete_airport`, `get_monitor_coverage`, `get_calendar_prices`, `get_price_history`가 아직 `api/main.py`에서 `get_conn()` 직접 호출(allowlist 동결, `AGENTS.md §11`, `test_architecture.py:132-140`).
6. **`mcp_server.py` 위치** — Service 레이어로 분류했으나 물리적으로 레포 루트. 이동 예정(`AGENTS.md §11`).
7. **LCC IATA 매핑 누락** — 일부 LCC가 `_AIRLINE_IATA`에 없음(`AGENTS.md §11`).
8. **죽은/미구현 소스** — `collector_skyscanner.py`(죽은 코드), Amadeus(미구현, requirements/UI 잔재). ⚠️ 섹션 참조.
9. **문서-실제 불일치** — README 테스트 수(48)·라인수·MCP 툴 수(3), Landing 페이지 Amadeus 문구, 프롬프트의 "Naver GraphQL". ⚠️ 섹션 참조.

### 진행 중/계획된 작업
- `ISSUES.md`/`TODOS.md`에 명시된 것: GF 재시도 정책, run 분산 고도화, price_history DROP, flight_legs 보존 cron.
- **Sentinel Agent / Flight Picker**: 과제에 언급됐으나 **저장소에 관련 코드·문서·이슈 항목 없음** → `❓미확인(계획 근거 없음)`. (현재 존재하는 에이전트성 코드는 `diagnosis_agent.py` 하나.)

---

## ❓미확인 항목 목록 (사용자가 직접 확인)

프로덕션/외부에 있어 저장소만으로 확인 불가한 것들. 대부분 **OCI 호스트 접속 또는 텔레그램 채널**로 해결된다.

- [ ] **각 테이블 현재 행 수** — 호스트: `python scripts/diagnose_db.py` 또는 `SELECT count(*)` (§3 SQL).
- [ ] **수집 대상 노선 수** — `SELECT code,name FROM airports;` (config는 빈 dict, DB 로드).
- [ ] **날짜 조합 수 / 누적 수집 건수 / 수집 기간 / 일평균** — `raw_legs` 집계 (§3).
- [ ] **1회 수집 사이클 소요 시간** — `SELECT status,duration_sec FROM collection_runs ORDER BY started_at DESC LIMIT 20;`
- [ ] **수집 성공률·실패 유형 분포** — `SELECT status,count(*) FROM collection_runs GROUP BY status;` + `error_log` 분류.
- [ ] **Diagnosis Agent 실제 탐지 사례 3건** — `/var/log/collector.log`의 "데이터 이상 감지" 또는 텔레그램 🚨 리포트 원문 (로그 미보존, 외부 확인 필요).
- [ ] **호스트 crontab에 collect_and_diagnose.sh가 실제 등록됐는지 / 진단 에이전트 현재 가동 여부** — 호스트 `crontab -l`.
- [ ] **매일 03:00 DB 백업 cron 존재 여부** — README에만 언급, 스크립트 미포함. 호스트 crontab 확인.
- [ ] **OCI 인스턴스 스펙** (타입/OS/vCPU/RAM; ARM64 추정만) — OCI 콘솔.
- [ ] **서비스 라이브 접속 가능 여부 / 저장소 공개 여부** — `https://flight-friend.com`, GitHub 저장소 설정.
- [ ] **테스트 커버리지 % / 실제 pytest 수집 수** — CI에서 `pytest --collect-only -q`, coverage 미설정.
- [ ] **"OCI IP 차단" 전후 성공률** — 해당 근거가 저장소에 없음. 있다면 로그/텔레그램에서, 없으면 "미해결 open issue"로 서술.
- [ ] **개발 시작일** — git 최초 2026-03-23. 포트폴리오의 "2026-03-03"은 git과 불일치(이전 히스토리 존재 여부 확인).
- [ ] **Sentinel Agent / Flight Picker 계획 실체** — 저장소에 근거 없음.
- [ ] **text_mode 벤치(`bench_gf_resource_block.py`) 실측 결과** — collector 컨테이너에서 실행 후 채택 여부·수치.
```
