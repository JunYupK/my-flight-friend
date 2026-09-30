# TODOS

_최종 업데이트: 2026-09-30_

## OCI(한국 IP)에서 Naver API 동작 확인
**What:** 배포 후 `/admin`에서 Naver 스냅샷 상태가 `ok`인지 확인. `blocked`/`error`가 이어지면 ops 알림(`ops:naver`)이 오고, 브라우저 재시도 방식(설계 D7)을 재논의한다.
**Context:** M2 계획 Task 1(OCI 사전 확인)은 보류됐다. spike 스크립트는 삭제했고, 배포된 worker 자체가 확인 수단이다.

## OCI Naver 차단 시 브라우저 재시도
**What:** Naver 직접 API 호출이 OCI에서 차단되면 브라우저(crawl4ai) 경유 재시도 폴백을 추가한다 (설계 D7). 차단이 확인될 때만 진행하는 후보.

## 잠정 상수 확정
**What:** 갱신 주기 티어(6h/2h/1h)와 신선도 창(W = 주기 × 2) 확정.
**Context:** 실제 추적 데이터로 가격 변동 빈도와 GF 차단 여부를 보고 `domain/schedule.py` 상수만 바꾼다 (AGENTS §7).

## V1 테이블 정리
**What:** 서버에서 `scripts/v1_freeze.sql` 실행 (pg_dump 백업 후) → 분석이 끝나면 `v1` 스키마 DROP 여부 결정.

## 이후 후보 (스펙 §11)
- 왕복 2단계 확장, 관심 항공편 고정, 다중 목적지 Trip, V1 참고 이력, 하루 요약 알림
