# flight_monitor/collector_naver.py
#
# crawl4ai 기반 네이버 항공권 크롤러.
# flight.naver.com 검색 결과 페이지에서 JS injection으로 항공편 카드를 파싱한다.
#
# 구조:
#   - 편도(OW) URL로 outbound/inbound 각각 수집
#   - DOM에서 카드 단위로 데이터 추출
#   - 편도 레그 저장 후 왕복 조합 생성

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from html import unescape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crawl4ai import AsyncWebCrawler

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig  # noqa: F811
    _CRAWL4AI_AVAILABLE = True
except ImportError:
    _CRAWL4AI_AVAILABLE = False

from .config import JAPAN_AIRPORTS, SEARCH_CONFIG, KST

ORIGIN = "ICN"
ORIGIN_NAVER = "SEL:city"
SOURCE = "naver"

_BATCH_SIZE = 5


def _build_naver_url(dep: str, arr: str, date_str: str) -> str:
    """편도 검색 URL 생성.

    dep/arr: IATA 공항 코드 (e.g. ICN, NRT).
    date_str: YYYY-MM-DD 형식.
    """
    date_compact = date_str.replace("-", "")
    # 출발지는 SEL:city, 도착지는 {code}:airport
    if dep == ORIGIN:
        dep_part = ORIGIN_NAVER
        arr_part = f"{arr}:airport"
    else:
        dep_part = f"{dep}:airport"
        arr_part = ORIGIN_NAVER
    return (
        f"https://flight.naver.com/flights/international/"
        f"{dep_part}-{arr_part}-{date_compact}"
        f"?adult=1&isDirect=false&fareType=Y"
    )


def _make_scroll_js() -> str:
    return """
(async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    let prev = 0;
    for (let i = 0; i < 5; i++) {
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(1500);
        const curr = document.body.scrollHeight;
        if (curr === prev) break;
        prev = curr;
    }
})();
"""


def _extract_js() -> str:
    """DOM에서 항공편 카드 데이터를 추출해 #__nv__ div에 JSON으로 주입."""
    return """(function() {
    var results = [];
    var cards = document.querySelectorAll('div[class*="combination_ConcurrentItemContainer"]');

    for (var i = 0; i < cards.length; i++) {
        var card = cards[i];

        // 가격
        var priceEl = card.querySelector('i[class*="item_num"]');
        if (!priceEl) continue;
        var priceText = priceEl.textContent.trim().replace(/,/g, '');
        var price = parseInt(priceText);
        if (isNaN(price) || price < 20000 || price > 3000000) continue;

        // 항공사
        var airlineEl = card.querySelector('b[class*="airline_name"]');
        var airline = airlineEl ? airlineEl.textContent.trim() : '';

        // 출발/도착 시간 & 공항
        var times = card.querySelectorAll('b[class*="route_time"]');
        var codes = card.querySelectorAll('i[class*="route_code"]');
        var depTime = times.length > 0 ? times[0].textContent.trim() : null;
        var arrTime = times.length > 1 ? times[1].textContent.trim() : null;
        var depAirport = codes.length > 0 ? codes[0].textContent.trim() : null;
        var arrAirport = codes.length > 1 ? codes[1].textContent.trim() : null;

        // 비행정보: "직항, 02시간 10분" or "경유 1, 26시간 25분"
        var detailEl = card.querySelector('button[class*="route_details"]');
        var detailText = detailEl ? detailEl.textContent.trim() : '';
        var stops = 0;
        var durationMin = null;

        if (detailText.indexOf('직항') !== -1) {
            stops = 0;
        } else {
            var sm = detailText.match(/경유\\s*(\\d+)/);
            if (sm) stops = parseInt(sm[1]);
        }

        var dm = detailText.match(/(\\d+)시간(?:\\s*(\\d+)분)?/);
        if (dm) {
            durationMin = parseInt(dm[1]) * 60 + parseInt(dm[2] || 0);
        }

        results.push({
            price: price,
            airline: airline,
            dep_time: depTime,
            arr_time: arrTime,
            dep_airport: depAirport,
            arr_airport: arrAirport,
            stops: stops,
            duration_min: durationMin
        });
    }

    var el = document.getElementById('__nv__');
    if (!el) {
        el = document.createElement('div');
        el.id = '__nv__';
        el.style.display = 'none';
        document.body.appendChild(el);
    }
    el.textContent = JSON.stringify(results);
})();"""


def _parse_cards(raw_html: str) -> list[dict]:
    """JS가 주입한 #__nv__ div에서 항공편 데이터를 추출."""
    m = re.search(r'id="__nv__"[^>]*>(.*?)</div>', raw_html, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(unescape(m.group(1).strip()))
    except (json.JSONDecodeError, ValueError):
        return []


def _combine_roundtrips(
    out_flights: list[dict], in_flights: list[dict],
    dep_airport: str, arr_airport: str, arr_name: str,
) -> list[dict]:
    """편도 왕/복편 조합으로 왕복 오퍼 생성."""
    topk = SEARCH_CONFIG["topk_per_date"]

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
                    out_al = out.get("airline", "")
                    in_al  = ret.get("airline", "")
                    results.append({
                        "source":           SOURCE,
                        "trip_type":        "oneway_combo",
                        "origin":           dep_airport,
                        "destination":      arr_airport,
                        "destination_name": arr_name,
                        "departure_date":   dep_date,
                        "return_date":      ret_date,
                        "stay_nights":      stay,
                        "price":            out["price"] + ret["price"],
                        "currency":         "KRW",
                        "out_airline":      out_al,
                        "in_airline":       in_al,
                        "is_mixed_airline": bool(out_al and in_al and out_al != in_al),
                        "out_dep_time":     out.get("dep_time"),
                        "out_arr_time":     out.get("arr_time"),
                        "out_duration_min": out.get("duration_min"),
                        "out_stops":        out.get("stops"),
                        "in_dep_time":      ret.get("dep_time"),
                        "in_arr_time":      ret.get("arr_time"),
                        "in_duration_min":  ret.get("duration_min"),
                        "in_stops":         ret.get("stops"),
                        "out_arr_airport":  out.get("arr_airport"),
                        "in_dep_airport":   ret.get("dep_airport"),
                        "out_url":          out.get("search_url"),
                        "in_url":           ret.get("search_url"),
                        "out_price":        out["price"],
                        "in_price":         ret["price"],
                        "checked_at":       datetime.now(KST).isoformat(),
                    })

    results.sort(key=lambda x: x["price"])
    return results


async def _fetch_route(
    crawler: AsyncWebCrawler,
    airport_code: str, airport_name: str,
    start_date: date, end_date: date,
    skip_set: set[tuple[str, str, str]] | None = None,
) -> list[dict]:
    """start_date~end_date 범위의 편도 항공편을 수집하고 왕복 조합을 반환."""
    delay = SEARCH_CONFIG["request_delay"]
    topk = SEARCH_CONFIG["topk_per_date"]

    # 1) 전체 URL + meta 목록 생성
    urls: list[str] = []
    metas: list[dict] = []

    d = start_date
    while d <= end_date:
        date_formatted = d.strftime("%Y-%m-%d")
        for dep, arr, direction in [
            (ORIGIN, airport_code, "out"),
            (airport_code, ORIGIN, "in"),
        ]:
            if skip_set and (airport_code, date_formatted, direction) in skip_set:
                continue
            url = _build_naver_url(dep, arr, date_formatted)
            urls.append(url)
            metas.append({
                "dep": dep, "arr": arr,
                "date": date_formatted,
                "direction": direction,
                "url": url,
            })
        d += timedelta(days=1)

    # 2) BATCH_SIZE 단위로 arun_many() 호출
    config = CrawlerRunConfig(
        magic=True,
        js_code=[_make_scroll_js(), _extract_js()],
        wait_for="js:() => !!document.querySelector('div[class*=\"combination_ConcurrentItemContainer\"]')",
        delay_before_return_html=8.0,
        cache_mode="bypass",
        page_timeout=SEARCH_CONFIG.get("page_timeout_ms", 30000),
    )

    out_flights, in_flights = [], []

    for i in range(0, len(urls), _BATCH_SIZE):
        batch_urls = urls[i:i + _BATCH_SIZE]
        batch_metas = metas[i:i + _BATCH_SIZE]
        url_to_meta = {u: m for u, m in zip(batch_urls, batch_metas)}

        try:
            results = await crawler.arun_many(urls=batch_urls, config=config)
        except Exception as e:
            print(f"[Naver ERROR] batch {i // _BATCH_SIZE}: {e}")
            continue

        for result in results:
            meta = url_to_meta.get(result.url)
            if meta is None:
                print(f"[Naver WARN] 매칭 메타 없음: {result.url[:80]}")
                continue
            if not result.success:
                print(f"[Naver FAIL] {meta['dep']}-{meta['arr']} {meta['date']}: {result.error_message}")
                continue

            flights = _parse_cards(result.html or "")
            if not flights:
                print(f"[Naver WARN] 카드 추출 0건 {meta['dep']}-{meta['arr']} {meta['date']}")
                continue

            flights.sort(key=lambda x: x["price"])
            enriched = []
            for f in flights[:topk]:
                enriched.append({"date": meta["date"], "search_url": meta["url"], **f})

            if meta["direction"] == "out":
                out_flights.extend(enriched)
            else:
                in_flights.extend(enriched)

        if i + _BATCH_SIZE < len(urls):
            await asyncio.sleep(delay)

    # 편도 레그를 raw_legs / flight_legs 테이블에 저장
    from flight_monitor.storage import save_legs
    now_iso = datetime.now(KST).isoformat()
    leg_records = []
    for direction, flights in [("out", out_flights), ("in", in_flights)]:
        for f in flights:
            leg_records.append({
                "source": SOURCE,
                "origin": ORIGIN,
                "destination": airport_code,
                "destination_name": airport_name,
                "date": f["date"],
                "direction": direction,
                "airline": f.get("airline"),
                "dep_time": f.get("dep_time"),
                "arr_time": f.get("arr_time"),
                "duration_min": f.get("duration_min"),
                "stops": f.get("stops"),
                "dep_airport": f.get("dep_airport"),
                "arr_airport": f.get("arr_airport"),
                "price": f["price"],
                "booking_url": None,
                "search_url": f.get("search_url"),
                "checked_at": now_iso,
            })
    save_legs(leg_records)

    return _combine_roundtrips(out_flights, in_flights, ORIGIN, airport_code, airport_name)


async def _fetch_airport(
    airport_code: str,
    airport_name: str,
    today: date,
    end_date: date,
    skip_set: set[tuple[str, str, str]],
    on_route_done,
    semaphore: asyncio.Semaphore,
    browser_config,
) -> list[dict]:
    async with semaphore:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            offers = await _fetch_route(
                crawler, airport_code, airport_name, today, end_date, skip_set
            )
        if on_route_done and offers:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, on_route_done, offers)
        print(f"[Naver] {airport_code}: {len(offers)}건")
        return offers


async def _fetch_all(on_route_done=None) -> list[dict]:
    if not _CRAWL4AI_AVAILABLE:
        print("[Naver] crawl4ai 미설치, 수집 스킵")
        return []

    browser_config = BrowserConfig(
        headless=True,
        viewport={"width": 1920, "height": 1080},
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )

    if not JAPAN_AIRPORTS:
        print("[Naver] JAPAN_AIRPORTS 비어 있음 — airports 테이블 확인 필요")
        return []

    today = date.today()
    range_months = SEARCH_CONFIG.get("search_range_months", 12)
    end_date = date(today.year, today.month, 1) + timedelta(days=32 * range_months)
    end_date = date(end_date.year, end_date.month, 1) - timedelta(days=1)
    max_stay = max(SEARCH_CONFIG["stay_durations"])
    end_date = end_date + timedelta(days=max_stay)

    from flight_monitor.storage import get_collected_today
    skip_set = get_collected_today(SOURCE)
    if skip_set:
        print(f"[Naver] {len(skip_set)}건 오늘 이미 수집됨, 스킵")

    parallel = SEARCH_CONFIG.get("parallel_airports", 3)
    semaphore = asyncio.Semaphore(parallel)

    tasks = [
        _fetch_airport(code, name, today, end_date, skip_set, on_route_done, semaphore, browser_config)
        for code, name in JAPAN_AIRPORTS.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    empty_routes = 0
    for airport_code, result in zip(JAPAN_AIRPORTS.keys(), results):
        if isinstance(result, BaseException):
            print(f"[Naver ERROR] {airport_code}: {result}")
            empty_routes += 1
        else:
            all_results.extend(result)
            if not result:
                empty_routes += 1

    if len(tasks) > 0 and empty_routes == len(tasks):
        print(f"[Naver WARN] 전체 {len(tasks)}개 노선 모두 0건 — DOM 셀렉터 변경 또는 크롤링 차단 가능성")

    return all_results


def fetch_naver_offers(on_route_done=None) -> list[dict]:
    """네이버 항공권 크롤링으로 항공편 수집 (동기 래퍼).
    on_route_done: 노선별 수집 완료 시 호출되는 콜백 (offers 리스트 전달)."""
    return asyncio.run(_fetch_all(on_route_done=on_route_done))
