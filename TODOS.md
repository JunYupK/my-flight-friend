# TODOS

_최종 업데이트: 2026-09-30_

## M2 — Naver 제공자
**What:** Naver spike (현 수집 경로 동작 여부, 요청 형식, 필드 커버리지) → 결과로 별도 계획 → `providers/naver.py` 어댑터.
**Context:** 스펙 §11. 2026-09 spike에서 V1 Naver 수집기가 0건 (2026-08-31부터 불능). 시간 일치 쌍의 69%에서 Naver가 GF보다 저렴.
V1 구현은 커밋 `d8e0422`의 `flight_monitor/collector_naver.py` 참고.

## 잠정 상수 확정
**What:** 갱신 주기 티어(6h/2h/1h)와 신선도 창(W = 주기 × 2) 확정.
**Context:** 실제 추적 데이터로 가격 변동 빈도와 GF 차단 여부를 보고 `domain/schedule.py` 상수만 바꾼다 (AGENTS §7).

## V1 테이블 정리
**What:** 서버에서 `scripts/v1_freeze.sql` 실행 (pg_dump 백업 후) → 분석이 끝나면 `v1` 스키마 DROP 여부 결정.

## 이후 후보 (스펙 §11)
- 왕복 2단계 확장, 관심 항공편 고정, 다중 목적지 Trip, V1 참고 이력, 하루 요약 알림
