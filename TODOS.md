
## DB 정리 정책 구현
**What:** crontab에 raw_legs 90일 이상 삭제 cron + price_history DROP 조건 스크립트 추가
**Why:** raw_legs가 무한정 쌓이면 price_history와 동일한 데이터 폭증 재현
**Pros:** DB 용량 제어, 성능 유지
**Cons:** 90일 이전 원본 데이터 손실 (포트폴리오 원본 보존 강조와 트레이드오프)
**Context:** price_history는 /api/price-history가 price_events 기반으로 전환된 후 안전하게 DROP 가능.
  raw_legs는 `DELETE FROM raw_legs WHERE collected_at < NOW() - INTERVAL '90 days'` cron으로 처리.
  price_history DROP 전에 Trends 페이지 정상 동작 확인 필수.
**Depends on:** 3-레이어 파이프라인 PR 완료 + price_events 데이터 충분히 누적 (최소 2주, ~2026-04-21 이후)

## price_history DROP 시 코드 정리 (price_events 2주 누적 후 ~2026-04-21)
**What:** price_history 테이블 DROP 후 아래 코드 제거
  1. `storage.py`: `save_prices()` 함수 전체
  2. `storage.py`: `init_db()` 내 `price_history` CREATE TABLE DDL
  3. `storage.py`: `init_db()` 내 `v_best_observed` DROP + CREATE VIEW (price_history 의존)
**Context:**
  - 2026-04-07 기준: save_prices 콜백 main.py에서 이미 제거됨 (price_history 신규 쓰기 없음)
  - price_history 마지막 업데이트: 2026-04-03 (사실상 dead)
  - 모든 API는 flight_legs / raw_legs / price_events 기반으로 전환 완료
**Depends on:** DB에서 price_history 테이블 DROP 완료 확인 후
