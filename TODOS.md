
## ✅ raw_legs 90일 정리 — 완료 (2026-06)
**What:** raw_legs 90일 이상 삭제
**상태:** `storage.cleanup_old_data()` 구현 → `main.py` 수집 완료 후 매 run마다 호출.
  별도 crontab 불필요 (수집 파이프라인에 내장). `DELETE FROM raw_legs WHERE collected_at < NOW() - INTERVAL '90 days'`.
**남은 것:** price_history DROP은 아래 항목 참조 (별개).

## price_history DROP 시 코드 정리 (price_events 2주 누적 후 ~2026-04-21)
**What:** price_history 테이블 DROP 후 아래 코드 제거
  1. `storage.py`: `save_prices()` 함수 전체
  2. `storage.py`: `init_db()` 내 `price_history` CREATE TABLE DDL
  3. `storage.py`: `init_db()` 내 `v_best_observed` DROP + CREATE VIEW (price_history 의존)
**Context:**
  - 2026-04-07 기준: save_prices 콜백 main.py에서 이미 제거됨 (price_history 신규 쓰기 없음)
  - price_history 마지막 업데이트: 2026-04-03 (사실상 dead)
  - 모든 API는 flight_legs / raw_legs / price_events 기반으로 전환 완료
  - 2026-06-16: `/api/timing/advance`(`deals_cache.py::_query_timing_advance`)가 price_history를 읽던
    마지막 누락 소비자였음. raw_legs 기반 self-join으로 이전 완료 — DROP 차단 요소 해소됨.
  - 2026-06-17: `should_notify_median_drop()`(price_history 기반 중앙값 알림) 제거됨 — 알림이
    `(목적지, 출발월)` 집약 + 목표가/쿨다운/하락 dedup으로 단순화. price_history 읽는 코드 더 줄어듦.
**Depends on:** DB에서 price_history 테이블 DROP 완료 확인 후

## flight_legs 보존 정책
**What:** `flight_legs`에서 `date < NOW() - 13개월`인 행 삭제 cron 추가 검토.
**Why:** `flight_legs`는 UPSERT라 노선당 1행만 유지되지만, 출발일이 지난 과거 날짜 row는 갱신되지 않고
  영구 보존되어 무제한 증가한다. `/api/timing/seasonal`이 12개월 lookback만 사용하므로 13개월(버퍼 1개월)
  이전 데이터는 조회되지 않음에도 삭제되지 않고 계속 쌓인다.
**Pros:** 테이블/인덱스 크기 제어, vacuum/조회 성능 유지.
**Cons:** 13개월 이전 과거 가격 데이터 손실 (포트폴리오 원본 보존 강조와 트레이드오프).
**Context:** 위 "DB 정리 정책 구현" 항목(raw_legs 90일 삭제)과 같은 마이그레이션 스크립트에서 함께 처리하는
  것을 권장. `idx_flight_legs_out`/`idx_flight_legs_in`(destination, date) 부분 인덱스가 있어
  `date < ...` 조건의 삭제 자체는 인덱스 레인지 스캔으로 가능.
**Depends on:** 없음 (독립적으로 실행 가능).
