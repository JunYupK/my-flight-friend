# CLAUDE.md

> **프로젝트 명세 / 아키텍처 / 인터페이스 / 금지사항은 [`AGENTS.md`](./AGENTS.md) 로 이전됨.**
> 본 파일은 LLM 행동 규범과 포트폴리오만 담는다. 충돌 시 AGENTS.md 우선.

---

## Behavioral guidelines

Behavioral guidelines to reduce common LLM coding mistakes. **Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

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

상세 명세(레이어, 인터페이스, DB 규칙, 환경변수, 명령어 등)는 `AGENTS.md` 참고.

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

---

## gstack

Use `/browse` from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/cso`, `/autoplan`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`.

If gstack skills aren't working, run `cd .claude/skills/gstack && ./setup` to build the binary and register skills.
