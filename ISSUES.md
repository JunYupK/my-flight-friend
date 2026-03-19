# 작업 이슈 & TODO

_최종 업데이트: 2026-03-19_

---

## 완료된 작업

- Google Flights 크롤러 전면 재작성 (`collector_google_flights.py`)
  - `#flt=` hash URL → `search?tfs=` URL로 교체 (tfs 바이너리에서 날짜만 교체)
  - 전체 페이지 마크다운 가격 긁기 버그 수정 → `li.pIav2d` 카드 단위 DOM 파싱
  - 신규 필드 추출: 출발/도착 시간, 비행 시간(분), 경유 횟수, 항공사
- DB 스키마 확장: `out/in_dep_time`, `out/in_arr_time`, `out/in_duration_min`, `out/in_stops`
- 기존 DB 자동 마이그레이션 (ALTER TABLE)
- 환경변수 없어도 실행 가능 (Amadeus, WhatsApp, Email 각각 graceful skip)
- DB 오염 데이터 정리 (이전 크롤러 수집분)
- `lcc_max_days` 설정 정리
- 외국 LCC 항공사 목록 이슈 해결/파기
- 공항 tfs 템플릿 이슈 해결/파기 (웹 UI에서 airports 테이블로 관리)

---

## 현재 알려진 이슈

### 1. 알림 채널 미설정
- WhatsApp (CALLMEBOT_PHONE, CALLMEBOT_API_KEY) 미설정
- Email (GMAIL_ADDRESS, GMAIL_APP_PASSWORD, ALERT_EMAIL) 미설정
- 현재 수집은 되지만 알림은 전송되지 않음

---

## 다음 작업 순서 (우선순위)

1. 알림 채널 중 하나 설정 (텔레그램 or WhatsApp)
2. 결과 선별 로직을 FastAPI 서버로 이동
   - 현재: `/api/results`가 전체 deals 반환 → 프론트(`Results.tsx`)에서 최저가 5개 + 시간대별 추천 선별
   - 문제: 데이터 많아질수록 프론트 로딩 느려짐
   - 할 일: top-5 선별 + `selectDiverseDeals` 로직을 API 서버에서 처리, 프론트는 렌더링만
