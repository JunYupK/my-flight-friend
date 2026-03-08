# flight_monitor/config.py

ORIGIN = "ICN"

JAPAN_AIRPORTS = {
    "TYO": "도쿄 (나리타/하네다)",
    # "OSA": "오사카 (간사이/이타미)",
    #"FUK": "후쿠오카",
    # "CTS": "삿포로 (신치토세)",
    # "OKA": "오키나와 (나하)",
    # "NGO": "나고야 (중부)",
    # "HIJ": "히로시마",
    # "SDJ": "센다이",
    # "KIJ": "니가타",
}

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
    "stay_durations": [3, 5, 7],

    # FSC (Amadeus)
    "departure_date_range_days": 90,
    "amadeus_max_requests_per_run": 60,  # Amadeus 월 한도 초과 방지

    # LCC (Naver GraphQL)
    "search_months": ["2026-05"],        # 2개 이상으로 늘리면 요청 수도 배증 주의
    "lcc_topk_per_date": 5,             # 날짜별 Top-K 유지
    "lcc_max_days": 5,                  # None이면 월 전체, 숫자면 해당 일수만 수집 (테스트용)

    # 성능/안전
    "request_delay": 1.0,
}
