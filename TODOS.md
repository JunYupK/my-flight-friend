# TODOS

_최종 업데이트: 2026-09-30_

## 진행 순서 (사용자 결정, 2026-09-30)
1. FE 대개편 → 2. Skyscanner 소스 추가 → 3. V1 테이블 동결(`scripts/v1_freeze.sql`) → 4. README·포트폴리오 V2 기준 재작성

## Naver 차단 시 브라우저 재시도 (후보)
**What:** Naver 직접 API 호출이 차단되면 브라우저(crawl4ai) 경유 재시도 폴백 (M2 설계 D7). 2026-09-30 배포 후 OCI에서 Naver 스냅샷 ok 확인 — 차단이 생길 때만 진행.

## 잠정 상수 확정
**What:** 갱신 주기 티어(6h/2h/1h)와 신선도 창(W = 주기 × 2) 확정.
**Context:** 실제 추적 데이터로 가격 변동 빈도와 GF 차단 여부를 보고 `domain/schedule.py` 상수만 바꾼다 (AGENTS §7).

## V1 테이블 정리
**What:** 서버에서 `scripts/v1_freeze.sql` 실행 (pg_dump 백업 후) → 분석이 끝나면 `v1` 스키마 DROP 여부 결정.

## 이후 후보 (스펙 §11)
- 왕복 2단계 확장, 관심 항공편 고정, 다중 목적지 Trip, V1 참고 이력, 하루 요약 알림
