# 포트폴리오 — my-flight-friend

> CLAUDE.md에서 옮김 (2026-10-01). 아래 서술은 V1 기준이며, V2 기준 재작성은 `docs/TODOS.md` 참고.

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
  7. 운영 중 성능 병목 진단·해결 — `/api/results`의 카테시안 조인(매 3시간 cold miss 5~10초)을 왕복 조합 사전계산(materialized `deals` 테이블)으로 전환, 무거운 read 엔드포인트 Redis 캐시 적용
  8. 수집 안정성 개선 — `flock` 동시 실행 금지 + 좀비 run 자동 청소로 run 중첩 누적 차단, 알림을 목적지×출발월 단위로 집약해 하루 1000건+ 폭주 해결

- **결과:**
  복수 소스 통합 수집 → 왕복 조합 → 목표가 알림까지 완전 자동화 파이프라인 운영 중
  48개 테스트 케이스 (PostgreSQL 기반 통합 테스트, 테스트 간 DB 격리)
  CI/CD 자동 배포 (CI 성공 시 무중단 배포 + 헬스체크)
  OCI 한국 리전 단일 서버에서 비용 최소화 운영
  커밋 80회+, 지속 개발 중 (2026-03-03 ~ 현재)

- **기술 스택:**
  Python, FastAPI, React 18, TypeScript, Tailwind CSS, PostgreSQL, Docker Compose,
  GitHub Actions, Caddy, OCI, crawl4ai, psycopg2, WebSocket
