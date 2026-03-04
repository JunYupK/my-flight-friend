# flight_monitor/collector_google_flights.py
#
# crawl4ai 기반 Google Flights 크롤러.
# collector_lcc.py와 동일한 출력 포맷(list[dict])을 반환한다.
#
# 구조:
#   - 편도(outbound + return) 각각 크롤링 후 왕복 조합
#   - 폼 조작: JS로 편도 선택 → 출발지/목적지/날짜 입력 → 검색 버튼 클릭
#   - 가격 파싱: 렌더링된 마크다운에서 ₩ 또는 원 포함 금액 추출
#
# NOTE:
#   Google Flights는 비공식 스크래핑 대상이므로 셀렉터가 변경될 수 있다.
#   FORM_SELECTORS 딕셔너리에서 셀렉터를 모아 관리하므로, 변경 시 이 부분만 수정.

import asyncio
import re
import calendar
from collections import defaultdict
from datetime import datetime, timedelta

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from .config import ORIGIN, JAPAN_AIRPORTS, SEARCH_CONFIG

GOOGLE_FLIGHTS_URL = "https://www.google.com/travel/flights?hl=ko&curr=KRW"

# 셀렉터가 바뀌면 여기만 수정
FORM_SELECTORS = {
    "one_way_option": '[role="option"]:has-text("편도"), [data-value="2"]',
    "origin_input":   'input[aria-label*="출발지"], input[placeholder*="출발지"]',
    "dest_input":     'input[aria-label*="목적지"], input[placeholder*="목적지"]',
    "date_input":     'input[aria-label*="출발일"], input[placeholder*="출발일"]',
    "first_option":   '[role="listbox"] [role="option"]:first-child',
    "search_btn":     'button[aria-label*="검색"], button[type="submit"]',
    "price_loaded":   'text:원',
}


def _make_fill_form_js(dep: str, arr: str, date_str: str) -> str:
    """
    Google Flights 검색 폼을 JS로 조작하는 스크립트 반환.
    date_str 형식: YYYY-MM-DD
    """
    return f"""
(async () => {{
    const sleep = ms => new Promise(r => setTimeout(r, ms));

    async function waitFor(selector, timeout=8000) {{
        const start = Date.now();
        while (Date.now() - start < timeout) {{
            const el = document.querySelector(selector);
            if (el) return el;
            await sleep(150);
        }}
        return null;
    }}

    // React 컨트롤 input에 값 세팅 (native setter + input 이벤트)
    function setReactValue(el, value) {{
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        )?.set;
        if (setter) setter.call(el, value);
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
    }}

    await sleep(2000);

    // 1. 왕복 → 편도 전환
    const tripBtn = document.querySelector('[data-value="1"]');  // 왕복 드롭다운
    if (tripBtn) {{
        tripBtn.click();
        await sleep(600);
        const oneWay = await waitFor('[role="option"][data-value="2"], [role="listbox"] li:nth-child(2)');
        if (oneWay) {{ oneWay.click(); await sleep(400); }}
    }}

    // 2. 출발지
    const origin = await waitFor('{FORM_SELECTORS["origin_input"]}');
    if (origin) {{
        origin.click();
        await sleep(300);
        setReactValue(origin, '');
        await sleep(100);
        setReactValue(origin, '{dep}');
        await sleep(1200);
        const opt = await waitFor('{FORM_SELECTORS["first_option"]}');
        if (opt) {{ opt.click(); await sleep(400); }}
    }}

    // 3. 목적지
    const dest = await waitFor('{FORM_SELECTORS["dest_input"]}');
    if (dest) {{
        dest.click();
        await sleep(300);
        setReactValue(dest, '');
        await sleep(100);
        setReactValue(dest, '{arr}');
        await sleep(1200);
        const opt = await waitFor('{FORM_SELECTORS["first_option"]}');
        if (opt) {{ opt.click(); await sleep(400); }}
    }}

    // 4. 날짜
    const dateEl = await waitFor('{FORM_SELECTORS["date_input"]}');
    if (dateEl) {{
        dateEl.click();
        await sleep(300);
        setReactValue(dateEl, '{date_str}');
        dateEl.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
        await sleep(400);
    }}

    // 5. 검색
    const searchBtn = await waitFor('{FORM_SELECTORS["search_btn"]}');
    if (searchBtn) {{ searchBtn.click(); await sleep(3000); }}

    // 6. 스크롤로 추가 결과 로드
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(1000);
    window.scrollTo(0, document.body.scrollHeight);
}})();
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
    # "123,456원" 형식도 시도
    for m in re.findall(r'([\d]{2,3},[\d]{3})원', markdown):
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
    """편도 항공편 크롤링. date_str 형식: YYYYMMDD"""
    date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    js = _make_fill_form_js(dep, arr, date_formatted)

    try:
        result = await crawler.arun(
            url=GOOGLE_FLIGHTS_URL,
            config=CrawlerRunConfig(
                magic=True,
                js_code=js,
                wait_for=FORM_SELECTORS["price_loaded"],
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
