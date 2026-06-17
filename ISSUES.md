# 작업 이슈 & TODO

_최종 업데이트: 2026-06-17_

> 구조적/보류 항목은 `TODOS.md`, 하네스 규칙은 `AGENTS.md` 참조.

---

## 완료된 작업

- Google Flights 크롤러 전면 재작성 (`collector_google_flights.py`)
  - `#flt=` hash URL → `search?tfs=` URL로 교체 (tfs 바이너리에서 날짜만 교체)
  - 전체 페이지 마크다운 가격 긁기 버그 수정 → `li.pIav2d` 카드 단위 DOM 파싱
  - 신규 필드 추출: 출발/도착 시간, 비행 시간(분), 경유 횟수, 항공사
- Naver 항공 크롤러 추가
- DB 3-레이어 파이프라인 (`raw_legs` → `flight_legs` → `price_events` 트리거)
- 알림 채널: Telegram(1순위) → Discord(2순위) fallback
- 결과 선별 로직(top-5 + `selectDiverseDeals`)을 FastAPI 서버로 이동 완료 (`search_service.py`)
- **deals 사전계산 테이블** — `/api/results`를 카테시안 조인에서 인덱스 조회로 전환, 3시간마다 나던 cold miss 제거 (2026-06)
- **수집 run 안정화** — `flock` 동시 실행 금지 + 좀비 run 자동 청소 (2026-06)
- **알림 집약** — `(목적지, 출발월)` 단위로 축소, 하루 1000건+ 폭주 해결 (2026-06)
- `/api/monitor/coverage`, `/api/price-history` timeline Redis 캐시
- raw_legs 90일 보존 정리 (`cleanup_old_data()`)
- **아키텍처 테스트** — `tests/test_architecture.py` 로 AGENTS §2/§8 레이어 경계를 ast 정적 분석으로 강제 (2026-06)

---

## 현재 알려진 이슈

### 1. Google Flights 간헐적 0건 수집
- GF가 간헐적으로 차단/타임아웃되어 특정 run에서 0건 반환 (Naver는 정상).
- ~~`page_timeout=30s`를 URL마다 꽉 채우고 실패 → run 시간 증가.~~ → GF 전용 `gf_page_timeout_ms=15s`로 분리(fast-fail). Naver는 30s 유지. (2026-06)
- 후속(남음): 차단 원인(DOM 셀렉터 드리프트 vs 안티봇) 진단 + 실패 재시도 정책.

### 2. 수집 run 시간 자체가 김
- 첫-run-of-day는 12개월 × 공항 × 양방향을 한 번에 수집 → 수 시간 소요.
- 지혈(flock + 좀비청소)로 중첩 누적은 막았으나, run 길이 단축은 미해결.
- 후속(구조): 12개월 크롤을 cron tick에 분산 / 근미래 우선 갱신.

---

## 다음 작업 (참고)

1. 크롤링 효율 — `page_timeout` 단축 + 재시도, 작업 분산 (위 이슈 1·2)
2. `price_history` 테이블 DROP + 관련 코드 정리 (`TODOS.md` 참조)
3. `flight_legs` 13개월 보존 정리 (`TODOS.md` 참조)
4. ~~`tests/test_architecture.py` 작성 — 레이어 경계 기계 검증~~ → 완료 (2026-06, ast 정적 분석 7 테스트)
