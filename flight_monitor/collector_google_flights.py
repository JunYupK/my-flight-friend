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
import calendar
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from flight_monitor.config import KST
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

_TFS_DATE_RE = re.compile(rb"\d{4}-\d{2}-\d{2}")

# 항공사 한글명 → IATA 코드 매핑 (ICN↔일본 노선 등장 항공사)
_AIRLINE_IATA: dict[str, str] = {
    "대한항공": "KE", "아시아나항공": "OZ",
    "진에어": "LJ", "제주항공": "7C", "티웨이항공": "TW",
    "에어서울": "RS", "에어부산": "BX", "이스타항공": "ZE",
    "일본항공": "JL", "전일본공수": "NH", "ANA": "NH",
    "피치항공": "MM", "Peach": "MM", "피치": "MM",
    "집에어": "ZG", "ZIPAIR": "ZG", "Zipair": "ZG",
    "스프링재팬": "IJ", "Spring Japan": "IJ",
    "중국동방항공": "MU", "중국남방항공": "CZ",
    "에어재팬": "NQ", "Air Japan": "NQ",
    "스타플라이어": "7G", "스카이마크": "BC",
    "배틀스타": "AD",
}


def _pb_varint(value: int) -> bytes:
    """Protobuf varint 인코딩."""
    result = b""
    while value > 0x7F:
        result += bytes([0x80 | (value & 0x7F)])
        value >>= 7
    result += bytes([value])
    return result


def _pb_field(field_num: int, wire_type: int, data: int | bytes) -> bytes:
    """Protobuf 필드 인코딩. wire_type 0=varint, 2=length-delimited."""
    tag = _pb_varint((field_num << 3) | wire_type)
    if wire_type == 0:
        return tag + _pb_varint(data)
    return tag + _pb_varint(len(data)) + data


def _pb_string(field_num: int, s: str) -> bytes:
    return _pb_field(field_num, 2, s.encode())


def _build_booking_tfs(
    date_str: str,
    segments: list[dict],
    origin: str,
    destination: str,
) -> str:
    """편명 정보로 Google Flights booking tfs 파라미터 생성.

    segments: [{"dep": "ICN", "arr": "NKG", "date": "2026-04-01",
                "airline": "MU", "flight_num": "580"}, ...]
    """
    itin = _pb_string(2, date_str)
    for seg in segments:
        seg_bytes = (
            _pb_string(1, seg["dep"])
            + _pb_string(2, seg["date"])
            + _pb_string(3, seg["arr"])
            + _pb_string(5, seg["airline"])
            + _pb_string(6, seg["flight_num"])
        )
        itin += _pb_field(4, 2, seg_bytes)
    # origin / destination wrappers (field 13, 14)
    itin += _pb_field(13, 2, _pb_field(1, 0, 1) + _pb_string(2, origin))
    itin += _pb_field(14, 2, _pb_field(1, 0, 1) + _pb_string(2, destination))

    outer = (
        _pb_field(1, 0, 28)
        + _pb_field(2, 0, 2)
        + _pb_field(3, 2, itin)
        + _pb_field(8, 0, 1)
        + _pb_field(9, 0, 1)
        + _pb_field(14, 0, 1)
        + _pb_field(16, 2, b"\x08" + b"\xff" * 9 + b"\x01")
        + _pb_field(19, 0, 2)
    )
    tfs = base64.urlsafe_b64encode(outer).rstrip(b"=").decode()
    return f"https://www.google.com/travel/flights/booking?tfs={tfs}&curr=KRW&hl=ko"


def _build_booking_url(
    flight: dict, dep: str, arr: str, date_str: str,
) -> str | None:
    """편명이 있으면 booking URL 생성, 없으면 None."""
    flight_numbers = flight.get("flight_numbers")
    if not flight_numbers:
        return None

    seg_dates = flight.get("segment_dates") or []
    airports = flight.get("segment_airports") or []

    segments = []
    for i, fn_str in enumerate(flight_numbers):
        m = re.match(r"([A-Z0-9]{2})\s*(\d+)", fn_str)
        if not m:
            return None
        seg_date = seg_dates[i] if i < len(seg_dates) and seg_dates[i] else date_str
        segments.append({
            "dep": "", "arr": "", "date": seg_date,
            "airline": m.group(1), "flight_num": m.group(2),
        })

    if len(segments) == 1:
        segments[0]["dep"] = dep
        segments[0]["arr"] = arr
    elif airports and len(airports) == len(segments) + 1:
        for i, seg in enumerate(segments):
            seg["dep"] = airports[i]
            seg["arr"] = airports[i + 1]
    else:
        return None

    return _build_booking_tfs(date_str, segments, dep, arr)


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
    # 템플릿 내 첫 번째 YYYY-MM-DD 패턴을 찾아 target 날짜로 교체
    m = _TFS_DATE_RE.search(raw)
    if m:
        raw = raw[:m.start()] + date_str.encode() + raw[m.end():]
    else:
        print(f"[GoogleFlights WARN] tfs 템플릿에 날짜 패턴 없음: {dep}_{arr}")
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
    편명은 data-travelimpactmodelwebsiteurl의 itinerary 파라미터에서 추출.
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

    // data-travelimpactmodelwebsiteurl에서 itinerary 파싱
    // 직항: itinerary=ICN-NRT-YP-735-20260501
    // 경유: itinerary=ICN-TNA-SC-8004-20260501,TNA-CKG-SC-8803-20260502
    function extractItinerary(card) {
        var el = card.querySelector('[data-travelimpactmodelwebsiteurl]');
        if (!el) return { flight_numbers: [], segment_airports: [], segment_dates: [] };
        var url = el.getAttribute('data-travelimpactmodelwebsiteurl') || '';
        var m = url.match(/itinerary=([^&]+)/);
        if (!m) return { flight_numbers: [], segment_airports: [], segment_dates: [] };

        var segments = m[1].split(',');
        var fns = [];
        var airports = [];
        var dates = [];
        for (var i = 0; i < segments.length; i++) {
            var parts = segments[i].split('-');
            // parts: [DEP, ARR, AIRLINE, FNUM, YYYYMMDD]
            if (parts.length < 5) continue;
            if (i === 0) airports.push(parts[0]);
            airports.push(parts[1]);
            fns.push(parts[2] + ' ' + parts[3]);
            // YYYYMMDD → YYYY-MM-DD
            var d = parts[4];
            if (d.length === 8) {
                dates.push(d.substring(0, 4) + '-' + d.substring(4, 6) + '-' + d.substring(6, 8));
            } else {
                dates.push('');
            }
        }
        return { flight_numbers: fns, segment_airports: airports, segment_dates: dates };
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
        var priceM = priceLabel.match(/^([\\d,]+)/);
        if (!priceM) continue;
        var price = parseInt(priceM[1].replace(/,/g, ''));
        if (price < 20000 || price > 3000000) continue;

        // 출발/도착 시간
        var depEl = card.querySelector('.wtdjmc.YMlIz');
        var arrEl = card.querySelector('.XWcVob.YMlIz');

        // 직항 여부 / 경유 횟수
        var stopsEl = card.querySelector('.VG3hNb');
        var stopsText = stopsEl ? stopsEl.textContent.trim() : '';
        if (!stopsText) {
            // fallback: 카드 내 텍스트에서 "직항" / "경유 N회" 패턴 검색
            var tw = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
            while (tw.nextNode()) {
                var txt = tw.currentNode.textContent.trim();
                if (txt === '직항') { stopsText = '직항'; break; }
                var sm = txt.match(/경유\\s*(\\d+)회/);
                if (sm) { stopsText = sm[1]; break; }
            }
        }
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

        // itinerary에서 편명 + 공항 + 날짜 추출
        var itin = extractItinerary(card);

        // dep/arr 공항: DOM 셀렉터 실패 시 itinerary에서 보완
        if (!depAirport && itin.segment_airports.length >= 2) {
            depAirport = itin.segment_airports[0];
        }
        if (!arrAirport && itin.segment_airports.length >= 2) {
            arrAirport = itin.segment_airports[itin.segment_airports.length - 1];
        }

        results.push({
            price: price,
            dep_time: toHHMM(depEl ? depEl.textContent : null),
            arr_time: toHHMM(arrEl ? arrEl.textContent : null),
            stops: stops,
            duration_min: duration_min,
            airline: airline,
            dep_airport: depAirport,
            arr_airport: arrAirport,
            flight_numbers: itin.flight_numbers,
            segment_airports: itin.segment_airports,
            segment_dates: itin.segment_dates
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
    enriched = []
    for f in flights[:SEARCH_CONFIG["topk_per_date"]]:
        booking_url = _build_booking_url(f, dep, arr, date_formatted)
        enriched.append({"date": date_formatted, "search_url": url, "booking_url": booking_url, **f})
    return enriched


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
                        "out_url":          out.get("booking_url") or out.get("search_url"),
                        "in_url":           ret.get("booking_url") or ret.get("search_url"),
                        "out_price":        out["price"],
                        "in_price":         ret["price"],
                        "checked_at":       datetime.now(KST).isoformat(),
                    })

    results.sort(key=lambda x: x["price"])
    return results


_BATCH_SIZE = 5


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
            url = _build_tfs_url(dep, arr, date_formatted)
            if url is None:
                continue
            urls.append(url)
            metas.append({"dep": dep, "arr": arr, "date": date_formatted, "direction": direction, "url": url})
        d += timedelta(days=1)

    # 2) BATCH_SIZE 단위로 arun_many() 호출
    config = CrawlerRunConfig(
        magic=True,
        js_code=[_make_scroll_js(), _extract_js()],
        wait_for="js:() => !!document.querySelector('li.pIav2d')",
        delay_before_return_html=4.0,
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
            print(f"[GoogleFlights ERROR] batch {i // _BATCH_SIZE}: {e}")
            continue

        for result in results:
            meta = url_to_meta.get(result.url)
            if meta is None:
                print(f"[GoogleFlights WARN] 매칭 메타 없음: {result.url[:80]}")
                continue
            if not result.success:
                print(f"[GoogleFlights FAIL] {meta['dep']}-{meta['arr']} {meta['date']}: {result.error_message}")
                continue

            flights = _parse_flight_cards(result.html or "")
            if not flights:
                print(f"[GoogleFlights WARN] 카드 추출 0건 {meta['dep']}-{meta['arr']} {meta['date']}")
                continue

            flights.sort(key=lambda x: x["price"])

            # 첫 번째 항공편의 dep_airport로 방향 검증
            sample_dep = flights[0].get("dep_airport")
            if sample_dep and sample_dep != meta["dep"]:
                print(f"[GoogleFlights WARN] 공항 불일치: "
                      f"기대 {meta['dep']}→{meta['arr']}, "
                      f"실제 출발공항 {sample_dep}. 해당 결과 스킵")
                continue

            enriched = []
            for f in flights[:topk]:
                booking_url = _build_booking_url(f, meta["dep"], meta["arr"], meta["date"])
                enriched.append({"date": meta["date"], "search_url": meta["url"], "booking_url": booking_url, **f})

            if meta["direction"] == "out":
                out_flights.extend(enriched)
            else:
                in_flights.extend(enriched)

        if i + _BATCH_SIZE < len(urls):
            await asyncio.sleep(delay)

    # 편도 레그를 flight_legs 테이블에 저장
    from flight_monitor.storage import save_legs
    now_iso = datetime.now(KST).isoformat()
    leg_records = []
    for direction, flights in [("out", out_flights), ("in", in_flights)]:
        for f in flights:
            leg_records.append({
                "source": "google_flights",
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
                "booking_url": f.get("booking_url"),
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
        print(f"[GoogleFlights] {airport_code}: {len(offers)}건")
        return offers


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

    if not JAPAN_AIRPORTS:
        print("[GoogleFlights] JAPAN_AIRPORTS 비어 있음 — airports 테이블 확인 필요")
        return []

    # 오늘부터 search_range_months 개월 뒤까지 수집
    today = date.today()
    range_months = SEARCH_CONFIG.get("search_range_months", 12)
    end_date = date(today.year, today.month, 1) + timedelta(days=32 * range_months)
    # end_date를 해당 월 말일로 보정
    _, last_day = calendar.monthrange(end_date.year, end_date.month)
    end_date = date(end_date.year, end_date.month, last_day)
    # 마지막 출발일의 복귀편도 수집되도록 stay 최대 박수만큼 연장
    max_stay = max(SEARCH_CONFIG["stay_durations"])
    end_date = end_date + timedelta(days=max_stay)

    # Option D: 오늘 이미 수집한 URL 스킵
    from flight_monitor.storage import get_collected_today
    skip_set = get_collected_today("google_flights")
    if skip_set:
        print(f"[GoogleFlights] {len(skip_set)}건 오늘 이미 수집됨, 스킵")

    # Option F: 공항 병렬화
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
            print(f"[GoogleFlights ERROR] {airport_code}: {result}")
            empty_routes += 1
        else:
            all_results.extend(result)
            if not result:
                empty_routes += 1

    if len(tasks) > 0 and empty_routes == len(tasks):
        print(f"[GoogleFlights WARN] 전체 {len(tasks)}개 노선 모두 0건 — DOM 셀렉터 변경 또는 크롤링 차단 가능성")

    return all_results


def fetch_google_flights_offers(on_route_done=None) -> list[dict]:
    """Google Flights 크롤링으로 항공권 최저가 수집 (동기 래퍼).
    on_route_done: 노선별 수집 완료 시 호출되는 콜백 (offers 리스트 전달)."""
    return asyncio.run(_fetch_all(on_route_done=on_route_done))
