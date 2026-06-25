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
    "median_alert_threshold_pct": 10,  # 출발일별 과거 중앙값 대비 이 % 이상 하락 시 알림
    "median_min_obs": 5,               # 중앙값 신뢰를 위한 최소 관측일 수

    # 조합 정책
    "allow_mixed_airline": True,
    "stay_durations": [3, 4, 5],

    # 수집 범위
    "search_range_months": 12,         # 오늘 기준 몇 개월 앞까지 수집
    # 한 cron tick이 수집할 개월 슬라이스 폭. range_months 전체를 이 단위로 나눠
    # 근미래부터 round-robin으로 tick마다 한 조각씩만 수집 → 첫-run-of-day의 12개월
    # full-sweep이 3h 주기를 넘겨 죽던 death spiral 차단. range_months 이상이면 비활성.
    "sweep_tick_months": 3,
    "topk_per_date": 5,                # 날짜별 Top-K 유지

    # 성능/안전
    "request_delay": 1.0,
    "parallel_airports": 3,      # 동시 실행 공항 수
    "page_timeout_ms": 30000,    # CrawlerRunConfig page_timeout (ms) — Naver(delay 8s)용 기본값
    # GF는 차단/타임아웃 시 wait_for가 page_timeout을 URL마다 꽉 채워 run 시간을 폭증시킨다.
    # GF 정상 로드는 scroll(~7.5s)+goto/wait이 각각 timeout 미만이라 15s로도 충분 → fast-fail.
    "gf_page_timeout_ms": 15000,

    # 렌더 비용 절감 (CPU 병목 완화). 가격/시간/항공사는 모두 DOM 텍스트라 이미지·웹폰트
    # 불필요 → Chromium에서 차단해 렌더·디코딩 CPU를 줄인다. CSS/JS는 SPA 렌더·셀렉터에
    # 필요하므로 끄지 않는다. 추출이 깨지면 False로 되돌려 즉시 롤백.
    "crawler_block_images": True,
    # 렌더 픽셀 수를 줄여 레이아웃 CPU 절감 (1920×1080 → 1280×800, ~50%). 데스크톱 폭 유지.
    "crawler_viewport": {"width": 1280, "height": 800},
}
