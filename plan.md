# 구현 계획: 최저가 페이지 개선 + 불필요 파일 정리

## 작업 1: 불필요 파일 삭제
- `plan.md` 삭제 (이 파일 자체 — 구현 완료 후 삭제)
- verify: `git status`에서 삭제 확인

## 작업 2: `/api/results`에 월별 필터 추가 (백엔드)
**파일**: `flight_front/api/main.py` (L164-223)

현재 API는 `hours` 파라미터만 지원. `month` (YYYY-MM) 파라미터 추가 필요.
또한 현재는 `rn <= 5`로 목적지당 5개만 반환 → 전체 항공권도 반환해야 함.

변경:
- `GET /api/results?month=2026-05` — `departure_date LIKE '2026-05%'` WHERE 조건 추가
- top-5 제한(`rn <= 5`) 제거 → 전체 결과 반환 (프론트에서 top-5 / 나머지 분리)
- `month` 없으면 기존처럼 전체 반환
- 기존 `hours` 파라미터는 삭제 (더 이상 사용 안 함)

verify: `curl /api/results?month=2026-05` 로 월별 필터링 동작 확인

## 작업 3: `fetchResults`에 month 파라미터 추가 (프론트 API)
**파일**: `flight_front/web/src/api.ts` (L52-60)

변경:
- `fetchResults(month?: string)` 시그니처 변경
- 쿼리스트링에 `month` 추가

verify: 타입 에러 없음

## 작업 4: Results.tsx 월별 필터 + 2섹션 구조 개편 (프론트 UI)
**파일**: `flight_front/web/src/components/Results.tsx`

현재: 목적지 탭 → 딜 카드 그리드 (최대 5개)
변경후: 목적지 탭 + **월 필터** → **오늘의 최저가**(상단 5개) + **모든 항공권 조합**(하단 전체)

상세:
1. 월 선택 UI 추가 — 현재 월(2026-03) ~ +12개월(2027-03), 총 13개 버튼/탭
2. 월 변경 시 `fetchResults(month)` 호출
3. 상단 섹션: "오늘의 최저가" 헤더 + 가격 오름차순 상위 5개 DealCard
4. 하단 섹션: "모든 항공권 조합" 헤더 + 나머지 전체 DealCard (기존 trip_type 필터 유지)
5. 기존 DealCard 컴포넌트는 그대로 재사용

verify: 월 변경 시 데이터 갱신, 2섹션 정상 렌더링

## 작업 5: Settings에서 search_months 옵션 삭제
**파일**: `flight_front/web/src/components/SearchConfig.tsx` (L127-162)

변경:
- "검색 월 (YYYY-MM)" 섹션 전체 삭제 (L128-162)
- `monthInput` state, `addMonth`, `removeMonth` 함수 삭제

**파일**: `flight_front/web/src/types.ts`
- `SearchConfig.search_months` 필드는 백엔드/수집기에서 여전히 사용하므로 **유지**

verify: Settings 페이지 정상 렌더링, search_months UI 없음
