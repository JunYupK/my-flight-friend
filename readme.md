# ✈️ My Flight Friend

ICN(인천) 출발 일본행 항공권 최저가 모니터링 도구.

복수 데이터 소스에서 편도 항공편을 수집하고 왕복 조합을 생성해서, 목표가 이하의 딜을 WhatsApp / 이메일로 알려줍니다.

## 주요 기능

- **다중 소스 수집** — Amadeus API(FSC), Google Flights 스크래핑, Naver GraphQL(LCC)
- **왕복 자동 조합** — 편도 운임을 조합하여 최적 왕복가 산출 (혼합 항공사 지원)
- **목표가 알림** — 설정 금액 이하 딜 발견 시 WhatsApp + 이메일 발송
- **알림 중복 방지** — 쿨다운 + 가격 하락 폭 기반 재알림 로직
- **웹 대시보드** — React + FastAPI 기반 수집 결과 조회 및 설정 관리
- **자동 수집** — GitHub Actions로 매일 자동 실행, DB 덤프 보존

## 아키텍처

```
main.py
  ├─ collector_amadeus.py        (Amadeus REST API — KE/OZ)
  ├─ collector_google_flights.py (crawl4ai 헤드리스 브라우저)
  └─ collector_lcc.py            (Naver GraphQL — 미연결)
        ↓
  storage.save_prices()  →  PostgreSQL (price_history)
        ↓
  should_notify()  →  notifier.notify()  →  WhatsApp / Email
```

**웹 UI** (`flight_front/`)
```
FastAPI (flight_front/api/main.py)
  ├─ GET/PUT /api/config       설정 조회/수정
  ├─ GET/POST/DELETE /api/airports  공항 관리
  ├─ POST /api/run             수집 실행
  ├─ GET /api/run/status       실행 상태
  ├─ WS /ws/run                실시간 로그
  └─ GET /api/results          노선별 Top-5 딜

React/Vite (flight_front/web/)
  ├─ 수집 결과 탭  →  딜 목록 + Google Flights 검색 링크
  └─ 설정 탭      →  검색 설정 + 공항/tfs 관리 + 수집 실행
```

## 빠른 시작

### 사전 요구사항

- Python 3.11+
- Node.js 20+ (프론트엔드 개발 시)
- Docker (PostgreSQL용)

### 설치

```bash
# 저장소 클론
git clone https://github.com/JunYupK/my-flight-friend.git
cd my-flight-friend

# 환경변수 설정
cp .env.example .env
# .env 파일을 편집하여 필요한 값 입력

# Python 의존성 설치
pip install -r requirements.txt

# crawl4ai 브라우저 설치 (Google Flights 수집에 필요)
crawl4ai-setup
```

### 실행

```bash
# 1. PostgreSQL 시작
docker compose up -d

# 2. 항공권 수집 실행
python main.py

# 3. 웹 대시보드 실행 (선택)
uvicorn flight_front.api.main:app --reload
# → http://localhost:8000

# 프론트엔드 개발 서버 (선택)
cd flight_front/web && npm install && npm run dev
```

### 프로덕션 배포

```bash
docker compose -f docker-compose.prod.yml up -d --build
# → http://localhost:8000
```

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `DATABASE_URL` | **필수** | PostgreSQL 연결 문자열 |
| `AMADEUS_CLIENT_ID` | 선택 | Amadeus API 클라이언트 ID |
| `AMADEUS_CLIENT_SECRET` | 선택 | Amadeus API 시크릿 |
| `CALLMEBOT_PHONE` | 선택 | WhatsApp 알림 전화번호 |
| `CALLMEBOT_API_KEY` | 선택 | CallMeBot API 키 |
| `GMAIL_ADDRESS` | 선택 | 이메일 알림 발신 Gmail |
| `GMAIL_APP_PASSWORD` | 선택 | Gmail 앱 비밀번호 |
| `ALERT_EMAIL` | 선택 | 알림 수신 이메일 |

선택 변수가 없으면 해당 수집기/알림은 건너뜁니다.

## 주요 설정 (`config.py`)

`SEARCH_CONFIG`에서 수집 동작을 제어합니다. 웹 UI 설정 탭에서도 변경 가능합니다.

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `target_price_krw` | 300,000 | 왕복 목표가 (원) |
| `stay_durations` | [3, 4, 5] | 체류 일수 조합 |
| `alert_cooldown_hours` | 12 | 동일 조건 재알림 간격 (시간) |
| `alert_realert_drop_krw` | 15,000 | 이전 알림 대비 이만큼 하락 시 재알림 |
| `search_months` | ["2026-05"] | LCC 수집 대상 월 |
| `allow_mixed_airline` | true | 가는편/오는편 다른 항공사 조합 허용 |

## 테스트

```bash
pytest tests/

# 특정 테스트
pytest tests/test_flight_monitor.py::TestShouldNotify
```

테스트는 PostgreSQL이 실행 중이어야 합니다 (`docker compose up -d`).

## GitHub Actions

`.github/workflows/daily_check.yml`로 매일 09:00 KST에 자동 수집합니다.

- PostgreSQL 서비스 컨테이너 사용
- 이전 실행의 DB 덤프를 복원하여 히스토리 유지
- 수집 후 DB를 덤프하여 artifact로 저장 (90일 보존)
- 수동 실행(workflow_dispatch)도 지원

GitHub Secrets에 환경변수를 등록해야 합니다.

## 기술 스택

- **Backend**: Python 3.11, FastAPI, psycopg2, crawl4ai, Amadeus SDK
- **Frontend**: React 18, TypeScript, Tailwind CSS, Vite
- **Database**: PostgreSQL 16
- **Infra**: Docker, GitHub Actions
