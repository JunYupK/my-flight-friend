# 수정 계획

## 버그 수정

### B1. `is_mixed_airline` 렌더링 시 "0" 출력 (Peach Aviation**0** 문제)
- **원인**: DB에서 `is_mixed_airline`이 INTEGER(0/1)로 저장됨. React에서 `{0 && <span>(혼합)</span>}`은 "0"을 렌더링함 (JS 단축평가 특성)
- **파일**: `Results.tsx:167`
- **수정**: `{deal.is_mixed_airline && ...}` → `{!!deal.is_mixed_airline && ...}` 또는 `{Boolean(deal.is_mixed_airline) && ...}`

### B2. Google Flights `trip_type`이 `"round_trip"`으로 설정됨
- **원인**: `collector_google_flights.py:246`에서 편도 2개를 조합하면서 `trip_type: "round_trip"`으로 설정. 실제로는 편도+편도 조합이므로 `"oneway_combo"`여야 함
- **파일**: `collector_google_flights.py:246`
- **수정**: `"trip_type": "round_trip"` → `"trip_type": "oneway_combo"`

### B3. `ICN → ICN : 복귀: HND` 표시 문제
- **원인 분석**: `out_arr_airport`이 null일 때 `deal.destination`(예: "NRT")으로 fallback하므로 정상이어야 함. 하지만 스크래퍼가 공항 코드를 잘못 추출하면 `out_arr_airport`에 출발지("ICN")가 들어갈 수 있음
- **파일**: `Results.tsx:122-133` (표시 로직), `collector_google_flights.py:126-138` (공항 추출 JS)
- **수정**:
  1. 표시 로직 개선 — `out_arr_airport`이 `origin`과 같으면 무시하고 `destination` 사용
  2. 복귀 공항도 마찬가지로 `in_dep_airport`이 `origin`과 같으면 표시 안 함

## UI 개선

### U1. 시간 필터 탭 삭제 (전체/24시간/48시간/7일)
- **파일**: `Results.tsx:64-69, 207, 228-231, 267-284`
- **수정**: `FRESHNESS_OPTIONS` 상수 및 관련 state/UI 코드 제거. API 호출도 항상 `hours` 없이 호출

### U2. 수집 일시 표시
- **파일**: `Results.tsx` DealCard 컴포넌트
- **수정**: `last_checked_at` 값을 "MM.DD HH:mm 수집" 형태로 카드에 표시. 기존 FreshnessBadge 대신 구체적 일시 표시

## 수정 순서

1. B1 — `is_mixed_airline` "0" 렌더링 수정
2. B2 — Google Flights `trip_type` 수정
3. B3 — ICN→ICN 표시 로직 수정
4. U1 — 시간 필터 탭 삭제
5. U2 — 수집 일시 표시
