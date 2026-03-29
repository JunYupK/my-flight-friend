
## DB 정리 정책 구현
**What:** crontab에 raw_legs 90일 이상 삭제 cron + price_history DROP 조건 스크립트 추가
**Why:** raw_legs가 무한정 쌓이면 price_history와 동일한 데이터 폭증 재현
**Pros:** DB 용량 제어, 성능 유지
**Cons:** 90일 이전 원본 데이터 손실 (포트폴리오 원본 보존 강조와 트레이드오프)
**Context:** price_history는 /api/price-history가 price_events 기반으로 전환된 후 안전하게 DROP 가능.
  raw_legs는 `DELETE FROM raw_legs WHERE collected_at < NOW() - INTERVAL '90 days'` cron으로 처리.
  price_history DROP 전에 Trends 페이지 정상 동작 확인 필수.
**Depends on:** 3-레이어 파이프라인 PR 완료 + price_events 데이터 충분히 누적 (최소 2주)
