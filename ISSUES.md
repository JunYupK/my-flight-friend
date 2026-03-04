# 작업 이슈 & TODO

_최종 업데이트: 2026-03-05_

---

## 완료된 작업

- Google Flights 크롤러 전면 재작성 (`collector_google_flights.py`)
  - `#flt=` hash URL → `search?tfs=` URL로 교체 (tfs 바이너리에서 날짜만 교체)
  - 전체 페이지 마크다운 가격 긁기 버그 수정 → `li.pIav2d` 카드 단위 DOM 파싱
  - 신규 필드 추출: 출발/도착 시간, 비행 시간(분), 경유 횟수, 항공사
- DB 스키마 확장: `out/in_dep_time`, `out/in_arr_time`, `out/in_duration_min`, `out/in_stops`
- 기존 DB 자동 마이그레이션 (ALTER TABLE)
- 환경변수 없어도 실행 가능 (Amadeus, WhatsApp, Email 각각 graceful skip)

---

## 현재 알려진 이슈

### 1. DB에 오염된 구 데이터 잔존
- **문제**: 이전 크롤러(전체 페이지 긁기)로 수집한 17,550건이 DB에 남아 있음
  - 동일 가격이 9개 목적지 전부에 등장하는 잘못된 데이터
- **해결**: `data/flights.db` 삭제 후 재수집 필요
  ```bash
  rm data/flights.db
  python main.py
  ```

### 2. 테스트용 `lcc_max_days: 5` 설정 중
- `config.py`의 `lcc_max_days`가 현재 `5`로 설정됨
- 전체 월 수집 시 `None`으로 변경 필요
  ```python
  "lcc_max_days": None,
  ```

### 3. 항공사 목록에 외국 LCC 미포함
- 피치항공(일본), 집에어 등 외국 항공사가 `AIRLINES` 리스트에 없음
- `collector_google_flights.py` `_extract_js()` 내 `AIRLINES` 배열에 추가 필요
  ```javascript
  var AIRLINES = ['대한항공','아시아나항공','진에어', ..., '피치항공', '집에어'];
  ```

### 4. 다른 공항 tfs 템플릿 미등록
- 현재 ICN↔TYO만 등록됨
- `collector_google_flights.py` `_TFS_TEMPLATES`에 추가 필요
- 추가 방법: 구글 플라이트에서 해당 노선 검색 → URL의 `tfs=` 값 복사
  ```python
  _TFS_TEMPLATES = {
      ("ICN", "TYO"): "...",
      ("TYO", "ICN"): "...",
      ("ICN", "OSA"): "",   # ← 추가 필요 (/m/0dqyw = 오사카)
      ("OSA", "ICN"): "",   # ← 추가 필요
      # FUK, CTS, OKA, NGO, HIJ, SDJ, KIJ ...
  }
  ```

### 5. 알림 채널 미설정
- WhatsApp (CALLMEBOT_PHONE, CALLMEBOT_API_KEY) 미설정
- Email (GMAIL_ADDRESS, GMAIL_APP_PASSWORD, ALERT_EMAIL) 미설정
- 현재 수집은 되지만 알림은 전송되지 않음

---

## 다음 작업 순서 (우선순위)

1. `data/flights.db` 삭제 후 `lcc_max_days: None`으로 전체 재수집
2. 외국 LCC 항공사 이름 추가 (피치항공 등)
3. OSA, FUK 등 공항별 tfs 템플릿 등록 및 `config.py`에서 해당 공항 주석 해제
4. 알림 채널 중 하나 설정 (텔레그램 or WhatsApp)
