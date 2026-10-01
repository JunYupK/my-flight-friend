# TODOS

_최종 업데이트: 2026-10-01_

## 진행 순서 (사용자 결정, 2026-09-30)
1. ~~FE 대개편~~ (완료 2026-09-30, Task 1–9) → 2. ~~Skyscanner 소스 추가~~ (보류 2026-10-01, 아래) → 3. V1 테이블 동결(`scripts/v1_freeze.sql`, 서버 실행 대기) → 4. README·포트폴리오 V2 기준 재작성

## 21st.dev·Mobbin 슬롯 교체
**What:** FE 대개편 spec §8 슬롯(`DashboardTripCard`, `Sparkline`, `PriceHistoryChart`, `DateRangePicker`, `DestinationCombobox`, `BestComboHero`, `LegCard`, `SelectionPanel`, `EmptyState`)을 사용자가 고른 21st.dev 컴포넌트/Mobbin 화면으로 하나씩 교체.
**Context:** 지금은 shadcn 기본 구현. 슬롯마다 한 파일·default export·props 고정이라 그 파일만 바꾸면 된다. 추가 라이브러리(framer-motion 등)가 필요하면 교체 시점에 판단 (spec §12 위험).

## Naver 차단 시 브라우저 재시도 (후보)
**What:** Naver 직접 API 호출이 차단되면 브라우저(crawl4ai) 경유 재시도 폴백 (M2 설계 D7). 2026-09-30 배포 후 OCI에서 Naver 스냅샷 ok 확인 — 차단이 생길 때만 진행.

## 잠정 상수 확정
**What:** 갱신 주기 티어(6h/2h/1h)와 신선도 창(W = 주기 × 2) 확정.
**Context:** 실제 추적 데이터로 가격 변동 빈도와 GF 차단 여부를 보고 `domain/schedule.py` 상수만 바꾼다 (AGENTS §7).

## V1 테이블 정리
**What:** 서버에서 `scripts/v1_freeze.sql` 실행 (pg_dump 백업 후) → 분석이 끝나면 `v1` 스키마 DROP 여부 결정.
**Context:** 2026-10-01 로컬 리허설 통과 — V1(`d8e0422` `init_db`) + V2 스키마를 한 DB에 만든 뒤 실행: public에 V2 6개만 남음, 2회 실행 멱등, 이동한 트리거(`v1.flight_legs` → `v1.record_price_change`)가 `v1.price_events`에 기록, `v1.v_best_observed` 조회 가능, V2 Trip 생성·run 등록·삭제 정상. 현재 코드에 V1 테이블 참조 없음.

## Skyscanner 소스 (보류)
**What:** Skyscanner를 세 번째 제공자로 추가.
**Context:** 2026-10-01 spike — skyscanner.co.kr/.net 모두 홈페이지부터 PerimeterX 캡차("Are you a person or a robot?")로 차단. curl, Playwright headless/headful(xvfb), crawl4ai(`magic` 유무) 전부 동일 → 접속 IP(데이터센터) 단계 차단으로 판단. 캡차 풀이·가정용 프록시 우회는 하지 않기로 함. 재개 조건: OCI에서 `curl -L https://www.skyscanner.co.kr/` 결과에 captcha가 없거나, RapidAPI 비공식 API(키·월 한도 확인)로 가기로 결정할 때.

## 이후 후보 (스펙 §11)
- 왕복 2단계 확장, 관심 항공편 고정, 다중 목적지 Trip, V1 참고 이력, 하루 요약 알림
