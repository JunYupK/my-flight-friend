# My Flight Friend

**인천(ICN) 출발 일본 항공권을 "내 여행" 단위로 추적하는 개인용 가격 모니터링 서비스**

[![CI](https://github.com/JunYupK/my-flight-friend/actions/workflows/ci.yml/badge.svg)](https://github.com/JunYupK/my-flight-friend/actions/workflows/ci.yml)
[![Deploy](https://github.com/JunYupK/my-flight-friend/actions/workflows/deploy.yml/badge.svg)](https://github.com/JunYupK/my-flight-friend/actions/workflows/deploy.yml)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

목적지와 날짜를 정해 **Trip**을 만들면, 상주 worker가 Google Flights와 Naver 항공권에서 가는 편·오는 편·왕복 가격을 주기적으로 확인합니다. 결과는 스냅샷으로 쌓입니다. 웹에서는 지금 가장 싼 조합, 제공자별 가격 비교, 시작 이후 가격 추이를 한눈에 보여줍니다. 새 최저가가 나오거나 목표가에 닿으면 Telegram(실패 시 Discord)으로 알립니다.

![대시보드](docs/images/dashboard.png)

| Trip 상세 (데스크톱) | 모바일 · 다크 모드 |
|---|---|
| ![Trip 상세](docs/images/trip-detail.png) | ![모바일 다크](docs/images/trip-mobile-dark.png) |

> 스크린샷은 `scripts/dev_seed.py`로 만든 시드 데이터입니다.

---

## 주요 기능

- **Trip 중심 추적**: 목적지·출발일·귀국일과 선호 조건(출발 시간대, 직항만, 항공사)을 담은 Trip이 화면·알림·조회의 단위입니다.
- **복수 제공자 비교**: Google Flights와 Naver 가격을 같은 항공편끼리 묶어 나란히 보여주고, 어느 쪽이 얼마나 싼지 표시합니다. Naver의 카드사 조건부 요금은 별도로 표시하며, 최저가 계산에는 무조건 요금만 씁니다.
- **지금 최선 + 후보**: 조건 안 최저 조합, 차액·현지 체류 시간이 다른 대안 후보, 조건을 조금 풀면 크게 싸지는 경우("near-miss")를 제안합니다.
- **자동 갱신 주기**: 출발까지 남은 일수에 따라 확인 주기를 바꿉니다. 60일 넘게 남으면 6시간, 15–60일이면 2시간, 14일 이내면 1시간입니다. 수동 "지금 확인"과 대시보드의 "전체 다시 확인"도 있습니다(5분 쿨다운).
- **가격 추이와 알림**: 일별 최저가 차트, 시작 대비 변동, 기간 최저를 보여줍니다. 새 최저가와 목표가 도달을 알리며, dedup·쿨다운으로 같은 알림을 반복하지 않습니다.
- **예약 바로가기**: Google Flights 예약 페이지, Naver 판매사 선택 페이지로 바로 이동합니다.
- **운영 화면**(`/admin`): 최근 확인 기록과 제공자별 일자 성공률을 보여주고, 차단·오류가 반복되면 운영 알림을 보냅니다.

## 아키텍처

```mermaid
graph LR
    subgraph OCI["OCI 한국 리전 · Docker Compose"]
        Caddy["Caddy<br/>자동 HTTPS"] --> App["app<br/>FastAPI + React SPA"]
        App --> DB[("PostgreSQL 16")]
        Worker["worker (상주)<br/>스케줄러 · 수집 · 알림"] --> DB
    end
    User(["브라우저"]) --> Caddy
    Worker -- "crawl4ai (Chromium)" --> GF["Google Flights"]
    Worker -- "httpx · SSE" --> NV["Naver 항공권 API"]
    Worker --> Noti["Telegram / Discord"]
```

**확인 한 번의 흐름**
1. 웹에서 "지금 확인"을 누르거나 스케줄러가 주기를 판단하면 `search_runs`에 run이 큐잉됩니다.
2. worker가 run을 가져가 제공자 × {가는 편, 오는 편, 왕복} 호출을 동시에 실행합니다. 호출 하나가 끝날 때마다 즉시 `snapshots`에 저장하므로, 화면의 진행 칩이 하나씩 채워집니다. run 전체는 3분 상한이고, 끝나지 않은 호출만 `timeout`으로 기록합니다.
3. API가 스냅샷을 읽어 항공편을 병합합니다. 같은 편은 `flight_key`로 먼저 묶고, 편명 기준 보조 매칭으로 한 번 더 묶습니다. 그 결과로 최저 조합·후보·추이를 계산해 JSON으로 돌려줍니다.
4. run이 끝나면 worker가 알림 조건을 판정해 발송하고, 발송 이력을 `alerts`에 남깁니다.

**설계 원칙**
- **Append-only 관측**: `snapshots`·`leg_quotes`·`rt_quotes`는 수정·삭제하지 않습니다. 가격 추이는 이 이력에서 바로 계산합니다. 오래된 관측은 신선도 창(갱신 주기 × 2) 밖이면 "최신 가격 없음"으로 구분합니다.
- **레이어 규칙을 테스트로 강제**: `types → db/repo → providers → domain → worker / api`. domain은 DB를, views는 웹 프레임워크를, API는 providers를 import하지 못하도록 `tests/test_architecture.py`가 AST로 검사합니다.
- **제공자 어댑터**: 모든 제공자는 같은 `ProviderResult`(`ok` / `empty` / `blocked` / `error`)를 돌려줍니다. 실패는 예외 대신 결과로 흡수하므로, 한 제공자가 막혀도 다른 제공자 결과는 그대로 저장됩니다.

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| Backend | Python 3.11, FastAPI, psycopg2, PostgreSQL 16 |
| 수집 | crawl4ai(Playwright Chromium, Google Flights), httpx(Naver 내부 API, SSE) |
| Frontend | React 18, TypeScript, Vite 6, Tailwind CSS v4, shadcn/ui, Recharts |
| 인프라 | Docker Compose(app · worker · db · caddy), Caddy, OCI |
| CI/CD | GitHub Actions: pytest · ruff · React build → 성공 시 SSH 배포 + `/healthz` 확인 |

## 프로젝트 구조

```
flight_friend/
  types.py, config.py      데이터클래스, 잠정 상수
  db.py, repo.py           스키마(init_schema, 멱등), 모든 SQL
  providers/               google_flights.py, naver.py, airlines.py
  domain/                  results(병합·조합·후보), schedule(갱신 주기), tracking(추이·알림 판정)
  worker.py, notifier.py   상주 루프, 알림 발송
  api/                     main.py(엔드포인트), views.py(JSON 조립)
flight_front/web/src/      React SPA — pages/, components/{ui,common,layout,dashboard,inputs,trip}/, api.ts
tests/                     pytest (PostgreSQL 통합 테스트, fixture HTML/SSE)
scripts/                   dev_seed.py(시드), ui_snap.py(스크린샷·가로 넘침 검사), v1_freeze.sql
docs/                      설계·계획(superpowers/), 작업 로그, TODOS, ISSUES, 포트폴리오
```

## 로컬 실행

```bash
cp .env.example .env                       # DATABASE_URL 등
docker compose up -d                       # PostgreSQL
pip install -r requirements.txt

uvicorn flight_friend.api.main:app --reload    # API + 빌드된 SPA (http://localhost:8000)
python -u -m flight_friend.worker              # worker (crawl4ai + Chromium 필요)

cd flight_front/web && npm install && npm run dev   # 프론트 개발 서버 (또는 npm run build)
```

화면만 확인하려면 worker 없이 시드 데이터를 넣으면 됩니다: `python scripts/dev_seed.py --reset` (localhost DB에서만 동작).

## 테스트

```bash
DATABASE_URL=postgresql://flight_user:flight_pass@localhost:5432/flights python -m pytest tests/ -q
python -m ruff check .
cd flight_front/web && npm run build
```

테스트는 204개입니다. 실제 PostgreSQL에 붙는 통합 테스트이고, 테스트마다 DB를 초기화합니다. 외부 사이트 호출은 fixture와 fake 제공자로 대체합니다.

## 배포

`master`에 push하면 CI가 실행되고, 성공하면 GitHub Actions가 서버에 SSH로 접속합니다. 먼저 `app`·`caddy`를 다시 빌드·기동하고 `/healthz`로 내부·외부(HTTPS) 응답을 확인합니다. 그다음 크롤러가 무거운 `worker`를 따로 빌드·기동합니다. 헬스체크가 실패하면 워크플로가 실패로 끝납니다. 직전 app 이미지는 `flight-friend-app:prev` 태그로 남겨 두어 수동 롤백에 씁니다. 환경 변수는 [`.env.example`](.env.example)과 [`AGENTS.md` §9](AGENTS.md)를 참고하세요.

## 문서

- [`AGENTS.md`](AGENTS.md): 레이어·파일 위치·DB·금지 규칙 (코딩 에이전트와 사람 공용 명세)
- [`docs/superpowers/specs/`](docs/superpowers/specs): 설계 문서 (V2, Naver 제공자, FE 대개편)
- [`docs/log.md`](docs/log.md): 작업 로그 · [`docs/TODOS.md`](docs/TODOS.md): 보류·후속 · [`docs/ISSUES.md`](docs/ISSUES.md): 알려진 이슈

## 히스토리

- **V1 (2026-03 ~)**: 여러 소스에서 공항·월 단위로 일괄 수집하고, 왕복 "딜 목록"을 사전계산해 보여주던 구조입니다. 코드는 커밋 `d8e0422`에 남아 있고, 테이블은 `v1` 스키마로 동결합니다.
- **V2 (2026-09 ~)**: 사용자 Trip 중심의 스냅샷 추적으로 재설계했습니다. M1에서 Google Flights 기반 추적을, M2에서 Naver 제공자(조건부 요금, 판매사 선택 링크)를 붙였고, 이어 FE를 대개편했습니다(대시보드, Trip 상세, 모바일·다크 모드).
- Skyscanner는 사이트 봇 차단(PerimeterX)으로 보류했습니다. 근거는 [`docs/TODOS.md`](docs/TODOS.md)에 있습니다.
