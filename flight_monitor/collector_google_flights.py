# flight_monitor/collector_google_flights.py
#
# crawl4ai 기반 Google Flights 크롤러.
# JS injection으로 항공편 카드를 개별 파싱해 노선별 정확한 데이터를 추출한다.
#
# 구조:
#   - 날짜를 URL hash fragment(#flt=)에 직접 포함해 결과 페이지로 직접 진입
#   - JS로 무한 스크롤 처리 후, DOM에서 카드 단위로 구조화된 데이터 추출
#   - 편도(outbound + return) 각각 수집 후 왕복 조합

from __future__ import annotations

import asyncio
import base64
import json
import re
import calendar
from collections import defaultdict
from datetime import datetime, timedelta
from html import unescape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crawl4ai import AsyncWebCrawler

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig  # noqa: F811
    _CRAWL4AI_AVAILABLE = True
except ImportError:
    _CRAWL4AI_AVAILABLE = False

from .config import ORIGIN, JAPAN_AIRPORTS, SEARCH_CONFIG, TFS_TEMPLATES

_TFS_BASE_DATE = "2026-05-01"


def _build_tfs_url(dep: str, arr: str, date_str: str) -> str | None:
    """노선+날짜 조합의 Google Flights 검색 URL 반환. 템플릿 없으면 None.
    tfs 값은 base64 문자열 또는 전체 URL 모두 허용."""
    template = TFS_TEMPLATES.get(f"{dep}_{arr}")
    if not template:
        return None
    # 전체 URL이 입력된 경우 tfs= 파라미터만 추출
    if template.startswith("http"):
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(template).query)
        tfs_list = qs.get("tfs")
        if not tfs_list:
            return None
        template = tfs_list[0]
    raw = base64.urlsafe_b64decode(template + "==")
    raw = raw.replace(_TFS_BASE_DATE.encode(), date_str.encode())
    tfs = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return f"https://www.google.com/travel/flights/search?tfs={tfs}&curr=KRW&hl=ko"


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
    """
    li.pIav2d 카드 셀렉터 기반으로 항공편 데이터를 추출해
    #__fl__ div에 JSON으로 주입한다.
    """
    return """(function() {
    function toHHMM(text) {
        if (!text) return null;
        var m = text.match(/(오전|오후)\\s*(\\d+):(\\d+)/);
        if (!m) return text.trim();
        var h = parseInt(m[2]);
        if (m[1] === '오후' && h !== 12) h += 12;
        if (m[1] === '오전' && h === 12) h = 0;
        return String(h).padStart(2, '0') + ':' + m[3];
    }

    var results = [];
    var cards = Array.from(document.querySelectorAll('li.pIav2d'));

    for (var i = 0; i < cards.length; i++) {
        var card = cards[i];

        // 가격: aria-label="250436 대한민국 원"
        var priceEl = card.querySelector('.YMlIz.FpEdX.jLMuyc > span[aria-label]')
                   || card.querySelector('.YMlIz.FpEdX span[aria-label]');
        if (!priceEl) continue;
        var priceLabel = priceEl.getAttribute('aria-label') || '';
        var priceM = priceLabel.match(/^([\d,]+)/);
        if (!priceM) continue;
        var price = parseInt(priceM[1].replace(/,/g, ''));
        if (price < 20000 || price > 3000000) continue;

        // 출발/도착 시간
        var depEl = card.querySelector('.wtdjmc.YMlIz');
        var arrEl = card.querySelector('.XWcVob.YMlIz');

        // 직항 여부 / 경유 횟수
        var stopsEl = card.querySelector('.VG3hNb');
        var stopsText = stopsEl ? stopsEl.textContent.trim() : '';
        var stops = stopsText === '직항' ? 0 : (parseInt(stopsText) || null);

        // 비행시간 (aria-label: "총 비행 시간은 2시간 20분입니다.")
        var durEl = card.querySelector('.gvkrdb');
        var durText = durEl ? (durEl.getAttribute('aria-label') || durEl.textContent || '') : '';
        var durM = durText.match(/(\\d+)시간(?:\\s*(\\d+)분)?/);
        var duration_min = durM ? parseInt(durM[1]) * 60 + parseInt(durM[2] || 0) : null;

        // 항공사
        var airlineEl = card.querySelector('.h1fkLb span');
        var airline = airlineEl ? airlineEl.textContent.trim() : '';

        // 공항 코드 — IATA 3자리 대문자. .iCvNQ 또는 fallback으로 전체 텍스트 노드 스캔
        var depAirport = null, arrAirport = null;
        var airportEls = card.querySelectorAll('.iCvNQ');
        if (airportEls.length >= 2) {
            depAirport = airportEls[0].textContent.trim();
            arrAirport = airportEls[airportEls.length - 1].textContent.trim();
        } else {
            // fallback: 카드 내 모든 텍스트 노드에서 IATA 패턴 검색
            var walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
            var codes = [];
            while (walker.nextNode()) {
                var t = walker.currentNode.textContent.trim();
                if (/^[A-Z]{3}$/.test(t) && codes.indexOf(t) === -1) codes.push(t);
            }
            if (codes.length >= 2) { depAirport = codes[0]; arrAirport = codes[1]; }
        }

        results.push({
            price: price,
            dep_time: toHHMM(depEl ? depEl.textContent : null),
            arr_time: toHHMM(arrEl ? arrEl.textContent : null),
            stops: stops,
            duration_min: duration_min,
            airline: airline,
            dep_airport: depAirport,
            arr_airport: arrAirport
        });
    }

    var el = document.getElementById('__fl__');
    if (!el) {
        el = document.createElement('div');
        el.id = '__fl__';
        el.style.display = 'none';
        document.body.appendChild(el);
    }
    el.textContent = JSON.stringify(results);
})();"""


def _parse_flight_cards(raw_html: str) -> list[dict]:
    """JS가 주입한 #__fl__ div에서 구조화된 항공편 데이터를 추출."""
    m = re.search(r'id="__fl__"[^>]*>(.*?)</div>', raw_html, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(unescape(m.group(1).strip()))
    except (json.JSONDecodeError, ValueError):
        return []


async def _fetch_one_way(
    crawler: AsyncWebCrawler,
    dep: str, arr: str, date_str: str,
) -> list[dict]:
    """편도 항공편 크롤링. date_str 형식: YYYYMMDD"""
    date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    url = _build_tfs_url(dep, arr, date_formatted)
    if url is None:
        return []

    try:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                magic=True,
                js_code=[_make_scroll_js(), _extract_js()],
                wait_for="js:() => !!document.querySelector('li.pIav2d')",
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

    flights = _parse_flight_cards(result.html or "")
    if not flights:
        print(f"[GoogleFlights WARN] 카드 추출 0건 {dep}-{arr} {date_formatted}")
        return []

    flights.sort(key=lambda x: x["price"])
    return [{"date": date_formatted, "search_url": url, **f} for f in flights[:SEARCH_CONFIG["lcc_topk_per_date"]]]


def _combine_roundtrips(
    out_flights: list[dict], in_flights: list[dict],
    dep_airport: str, arr_airport: str, arr_name: str,
) -> list[dict]:
    """편도 왕/복편 조합으로 왕복 오퍼 생성."""
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
                    out_al = out.get("airline", "")
                    in_al  = ret.get("airline", "")
                    results.append({
                        "source":           "google_flights",
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
                        "checked_at":       datetime.now().isoformat(),
                    })

    results.sort(key=lambda x: x["price"])
    return results


_BATCH_SIZE = 5


async def _fetch_route(
    crawler: AsyncWebCrawler,
    airport_code: str, airport_name: str,
    year: int, month: int,
) -> list[dict]:
    days_in_month = calendar.monthrange(year, month)[1]
    max_days = SEARCH_CONFIG.get("lcc_max_days") or days_in_month
    delay = SEARCH_CONFIG["request_delay"]

    # 1) 전체 URL + meta 목록 생성
    urls: list[str] = []
    metas: list[dict] = []
    topk = SEARCH_CONFIG["lcc_topk_per_date"]

    for day in range(1, min(max_days, days_in_month) + 1):
        date_str = f"{year}{month:02d}{day:02d}"
        date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

        for dep, arr, direction in [
            (ORIGIN, airport_code, "out"),
            (airport_code, ORIGIN, "in"),
        ]:
            url = _build_tfs_url(dep, arr, date_formatted)
            if url is None:
                continue
            urls.append(url)
            metas.append({"dep": dep, "arr": arr, "date": date_formatted, "direction": direction, "url": url})

    # 2) BATCH_SIZE 단위로 arun_many() 호출
    config = CrawlerRunConfig(
        magic=True,
        js_code=[_make_scroll_js(), _extract_js()],
        wait_for="js:() => !!document.querySelector('li.pIav2d')",
        delay_before_return_html=4.0,
        cache_mode="bypass",
    )

    out_flights, in_flights = [], []

    for i in range(0, len(urls), _BATCH_SIZE):
        batch_urls = urls[i:i + _BATCH_SIZE]
        batch_metas = metas[i:i + _BATCH_SIZE]

        try:
            results = await crawler.arun_many(urls=batch_urls, config=config)
        except Exception as e:
            print(f"[GoogleFlights ERROR] batch {i // _BATCH_SIZE}: {e}")
            continue

        for result, meta in zip(results, batch_metas):
            if not result.success:
                print(f"[GoogleFlights FAIL] {meta['dep']}-{meta['arr']} {meta['date']}: {result.error_message}")
                continue

            flights = _parse_flight_cards(result.html or "")
            if not flights:
                print(f"[GoogleFlights WARN] 카드 추출 0건 {meta['dep']}-{meta['arr']} {meta['date']}")
                continue

            flights.sort(key=lambda x: x["price"])
            enriched = [{"date": meta["date"], "search_url": meta["url"], **f} for f in flights[:topk]]

            if meta["direction"] == "out":
                out_flights.extend(enriched)
            else:
                in_flights.extend(enriched)

        if i + _BATCH_SIZE < len(urls):
            await asyncio.sleep(delay)

    return _combine_roundtrips(out_flights, in_flights, ORIGIN, airport_code, airport_name)


async def _fetch_all(on_route_done=None) -> list[dict]:
    if not _CRAWL4AI_AVAILABLE:
        print("[GoogleFlights] crawl4ai 미설치, 수집 스킵")
        return []

    browser_config = BrowserConfig(
        headless=True,
        viewport={"width": 1920, "height": 1080},
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",           # Docker/CI에서 root 실행 시 필수
            "--disable-dev-shm-usage",  # Docker /dev/shm 64MB 제한 우회
            "--disable-gpu",           # 서버 환경 GPU 없음
        ],
    )

    all_results = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for month_str in SEARCH_CONFIG["search_months"]:
            year, month = map(int, month_str.split("-"))
            for airport_code, airport_name in JAPAN_AIRPORTS.items():
                offers = await _fetch_route(crawler, airport_code, airport_name, year, month)
                all_results.extend(offers)
                if on_route_done and offers:
                    on_route_done(offers)
                print(f"[GoogleFlights] {airport_code} {month_str}: {len(offers)}건")

    return all_results


def fetch_google_flights_offers(on_route_done=None) -> list[dict]:
    """Google Flights 크롤링으로 항공권 최저가 수집 (동기 래퍼).
    on_route_done: 노선별 수집 완료 시 호출되는 콜백 (offers 리스트 전달)."""
    return asyncio.run(_fetch_all(on_route_done=on_route_done))
