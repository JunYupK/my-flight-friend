# flight_monitor/collector_google_flights.py
#
# crawl4ai 기반 Google Flights 크롤러.
# collector_lcc.py와 동일한 출력 포맷(list[dict])을 반환한다.
#
# 구조:
#   - 날짜를 URL hash fragment(#flt=)에 직접 포함해 결과 페이지로 직접 진입
#   - JS로 무한 스크롤 처리 (높이 변화 없을 때까지 최대 5회)
#   - 편도(outbound + return) 각각 수집 후 왕복 조합
#   - 가격 파싱: 렌더링된 마크다운에서 ₩/원 포함 금액 추출

import asyncio
import re
import calendar
from collections import defaultdict
from datetime import datetime, timedelta

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from .config import ORIGIN, JAPAN_AIRPORTS, SEARCH_CONFIG

GOOGLE_FLIGHTS_BASE = "https://www.google.com/travel/flights?hl=ko&curr=KRW"


def _build_url(dep: str, arr: str, date_str: str) -> str:
    """날짜가 포함된 편도 검색 URL 반환. date_str 형식: YYYY-MM-DD
    Google Flights hash fragment로 날짜를 직접 전달해 calendar picker 조작을 우회한다."""
    return (
        f"https://www.google.com/travel/flights"
        f"#flt={dep}.{arr}.{date_str};c:KRW;e:1;sd:1;t:f"
    )



def _make_scroll_js() -> str:
    """
    검색 결과 페이지에서 추가 항공편을 로드하는 스크롤 스크립트.
    Google Flights는 무한 스크롤로 결과를 점진 로딩하므로,
    페이지 높이 변화가 없을 때까지 반복 스크롤한다 (최대 5회).
    """
    return """
(async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    let prev = 0;
    for (let i = 0; i < 5; i++) {
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(1500);
        const curr = document.body.scrollHeight;
        if (curr === prev) break;   // 새 결과 없으면 중단
        prev = curr;
    }
})();
"""


# 항공권 가격 범위 (원화 기준 최소/최대)
_PRICE_MIN = 20_000
_PRICE_MAX = 3_000_000


def _parse_prices(markdown: str) -> list[int]:
    """렌더링된 마크다운에서 원화 가격 목록 추출."""
    prices = []
    for m in re.findall(r'₩\s*([\d,]+)', markdown):
        try:
            p = int(m.replace(',', ''))
            if _PRICE_MIN < p < _PRICE_MAX:
                prices.append(p)
        except ValueError:
            continue
    # "1,234,000원" 형식도 시도 (자릿수 제한 없음)
    for m in re.findall(r'([\d,]+)원', markdown):
        try:
            p = int(m.replace(',', ''))
            if _PRICE_MIN < p < _PRICE_MAX:
                prices.append(p)
        except ValueError:
            continue
    return sorted(set(prices))


async def _fetch_one_way(
    crawler: AsyncWebCrawler,
    dep: str, arr: str, date_str: str,
) -> list[dict]:
    """편도 항공편 크롤링. date_str 형식: YYYYMMDD
    날짜는 URL hash fragment에 직접 포함해 calendar picker 조작 없이 결과 페이지로 진입.
    """
    date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    url = _build_url(dep, arr, date_formatted)

    try:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                magic=True,
                js_code=_make_scroll_js(),
                wait_for="js:() => document.body.innerText.includes('원')",
                delay_before_return_html=4.0,
                cache_mode="bypass",
            ),
        )
    except Exception as e:
        print(f"[GoogleFlights ERROR] {dep}-{arr} {date_formatted}: {e}")
        return []

    if not result.success:
        print(f"[GoogleFlights FAIL] {dep}-{arr} {date_formatted}: {result.error_message}")
        return []

    prices = _parse_prices(result.markdown or "")
    return [
        {"date": date_formatted, "airline": "", "price": p}
        for p in prices[:SEARCH_CONFIG["lcc_topk_per_date"]]
    ]


def _combine_roundtrips(
    out_flights: list[dict], in_flights: list[dict],
    dep_airport: str, arr_airport: str, arr_name: str,
) -> list[dict]:
    """편도 왕/복편 조합으로 왕복 오퍼 생성. collector_lcc.py와 동일 로직."""
    topk = SEARCH_CONFIG["lcc_topk_per_date"]

    out_idx: dict[str, list] = defaultdict(list)
    in_idx:  dict[str, list] = defaultdict(list)
    for f in out_flights:
        out_idx[f["date"]].append(f)
    for f in in_flights:
        in_idx[f["date"]].append(f)

    for d in out_idx:
        out_idx[d] = sorted(out_idx[d], key=lambda x: x["price"])[:topk]
    for d in in_idx:
        in_idx[d] = sorted(in_idx[d], key=lambda x: x["price"])[:topk]

    results = []
    for dep_date, outs in out_idx.items():
        dep_dt = datetime.strptime(dep_date, "%Y-%m-%d")
        for stay in SEARCH_CONFIG["stay_durations"]:
            ret_date = (dep_dt + timedelta(days=stay)).strftime("%Y-%m-%d")
            ins = in_idx.get(ret_date)
            if not ins:
                continue
            for out in outs:
                for ret in ins:
                    results.append({
                        "source": "google_flights",
                        "trip_type": "round_trip",
                        "origin": dep_airport,
                        "destination": arr_airport,
                        "destination_name": arr_name,
                        "departure_date": dep_date,
                        "return_date": ret_date,
                        "stay_nights": stay,
                        "price": out["price"] + ret["price"],
                        "currency": "KRW",
                        "out_airline": "",
                        "in_airline": "",
                        "is_mixed_airline": False,
                        "checked_at": datetime.now().isoformat(),
                    })

    results.sort(key=lambda x: x["price"])
    return results


async def _fetch_route(
    crawler: AsyncWebCrawler,
    airport_code: str, airport_name: str,
    year: int, month: int,
) -> list[dict]:
    days_in_month = calendar.monthrange(year, month)[1]
    out_flights, in_flights = [], []
    delay = SEARCH_CONFIG["request_delay"]

    for day in range(1, days_in_month + 1):
        date_str = f"{year}{month:02d}{day:02d}"

        outs = await _fetch_one_way(crawler, ORIGIN, airport_code, date_str)
        out_flights.extend(outs)
        await asyncio.sleep(delay)

        ins = await _fetch_one_way(crawler, airport_code, ORIGIN, date_str)
        in_flights.extend(ins)
        await asyncio.sleep(delay)

    return _combine_roundtrips(out_flights, in_flights, ORIGIN, airport_code, airport_name)


async def _fetch_all() -> list[dict]:
    browser_config = BrowserConfig(
        headless=True,
        viewport={"width": 1920, "height": 1080},
        extra_args=["--disable-blink-features=AutomationControlled"],
    )

    all_results = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for month_str in SEARCH_CONFIG["search_months"]:
            year, month = map(int, month_str.split("-"))
            for airport_code, airport_name in JAPAN_AIRPORTS.items():
                offers = await _fetch_route(crawler, airport_code, airport_name, year, month)
                all_results.extend(offers)
                print(f"[GoogleFlights] {airport_code} {month_str}: {len(offers)}건")

    return all_results


def fetch_google_flights_offers() -> list[dict]:
    """Google Flights 크롤링으로 항공권 최저가 수집 (동기 래퍼)."""
    return asyncio.run(_fetch_all())
