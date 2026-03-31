# flight_monitor/config.py
from datetime import timedelta, timezone

KST = timezone(timedelta(hours=9))

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

    # 수집 범위
    "search_range_months": 12,         # 오늘 기준 몇 개월 앞까지 수집
    "topk_per_date": 5,                # 날짜별 Top-K 유지

    # 성능/안전
    "request_delay": 1.0,
    "parallel_airports": 3,      # 동시 실행 공항 수
    "page_timeout_ms": 30000,    # CrawlerRunConfig page_timeout (ms)
}
