# flight_monitor/config.py

ORIGIN = "ICN"

JAPAN_AIRPORTS: dict[str, str] = {}

# Google Flights tfs= 파라미터 템플릿. 웹 UI에서 입력.
# key: "ICN_TYO" 형식 (출발_도착), value: base64 tfs= 값
# 구글 플라이트에서 해당 노선 검색 후 URL의 tfs= 값을 붙여넣기.
TFS_TEMPLATES: dict[str, str] = {}

SEARCH_CONFIG = {
    # 공통
    "adults": 1,
    "currency": "KRW",
    "nonStop": False,

    # 목표가/알림
    "target_price_krw": 300000,        # 왕복 기준 목표가
    "alert_cooldown_hours": 12,        # 같은 조건 알림 최소 간격
    "alert_realert_drop_krw": 15000,   # 이전 알림 대비 이만큼 내려가면 재알림

    # 조합 정책
    "allow_mixed_airline": True,
    "stay_durations": [3, 4, 5],

    # FSC (Amadeus)
    "departure_date_range_days": 90,
    "amadeus_max_requests_per_run": 60,  # Amadeus 월 한도 초과 방지

    # LCC (Naver GraphQL)
    "search_months": ["2026-05"],        # 2개 이상으로 늘리면 요청 수도 배증 주의
    "lcc_topk_per_date": 5,             # 날짜별 Top-K 유지
    "lcc_max_days": None,                  # None이면 월 전체, 숫자면 해당 일수만 수집 (테스트용)

    # 성능/안전
    "request_delay": 1.0,
}
