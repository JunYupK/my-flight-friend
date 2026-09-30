# flight_friend/providers/google_flights.py
#
# Google Flights 어댑터: 템플릿 없는 protobuf tfs URL 생성, 카드 추출 JS/파서,
# 카드 → LegQuote/RtQuote 변환, crawl4ai 기반 편도/왕복 검색.
# V1 (커밋 d8e0422의 flight_monitor/collector_google_flights.py, crawler_utils.py)에서 순수 부품만 이전.

from __future__ import annotations

import base64
import json
import re
import time
from datetime import date
from html import unescape
from typing import Literal, Protocol

from flight_friend.providers.airlines import airline_iata, flight_key
from flight_friend.types import LegQuote, ProviderResult, RtQuote

_BLOCKED_MARKERS = ("unusual traffic", "sorry/index", "recaptcha")


class CrawlResult(Protocol):
    success: bool
    html: str | None
    error_message: str | None


class Crawler(Protocol):
    async def arun(self, *, url: str, config: object) -> CrawlResult: ...


# --- protobuf 인코딩 (V1 그대로) -------------------------------------------


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
        return tag + _pb_varint(data)  # type: ignore[arg-type]
    return tag + _pb_varint(len(data)) + data  # type: ignore[arg-type]


def _pb_string(field_num: int, s: str) -> bytes:
    return _pb_field(field_num, 2, s.encode())


# --- 검색 URL (템플릿 없음, 스펙 §5.2) --------------------------------------


def _flight_data_bytes(date_str: str, dep: str, arr: str) -> bytes:
    """FlightData: 2:date, 13:{1:1,2:dep}, 14:{1:1,2:arr}."""
    return (
        _pb_string(2, date_str)
        + _pb_field(13, 2, _pb_field(1, 0, 1) + _pb_string(2, dep))
        + _pb_field(14, 2, _pb_field(1, 0, 1) + _pb_string(2, arr))
    )


def _search_tfs(legs: list[tuple[str, str, str]], trip_type: int) -> str:
    """outer: 1:28, 2:2, 3:<FlightData>…, 8:1, 9:1, 14:1, 16:{08 ff×9 01}, 19:trip_type."""
    itin = b""
    for date_str, dep, arr in legs:
        itin += _pb_field(3, 2, _flight_data_bytes(date_str, dep, arr))
    outer = (
        _pb_field(1, 0, 28)
        + _pb_field(2, 0, 2)
        + itin
        + _pb_field(8, 0, 1)
        + _pb_field(9, 0, 1)
        + _pb_field(14, 0, 1)
        + _pb_field(16, 2, b"\x08" + b"\xff" * 9 + b"\x01")
        + _pb_field(19, 0, trip_type)
    )
    return base64.urlsafe_b64encode(outer).rstrip(b"=").decode()


def build_oneway_url(dep: str, arr: str, date_: date) -> str:
    tfs = _search_tfs([(date_.isoformat(), dep, arr)], 2)
    return f"https://www.google.com/travel/flights/search?tfs={tfs}&curr=KRW&hl=ko"


def build_roundtrip_url(dep: str, arr: str, out_date: date, ret_date: date) -> str:
    tfs = _search_tfs(
        [(out_date.isoformat(), dep, arr), (ret_date.isoformat(), arr, dep)], 1
    )
    return f"https://www.google.com/travel/flights/search?tfs={tfs}&curr=KRW&hl=ko"


# --- 예약 URL (V1 _build_booking_tfs/_build_booking_url 그대로) ------------


def _build_booking_tfs(
    date_str: str,
    segments: list[dict[str, str]],
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


def build_booking_url(
    card: dict, dep: str, arr: str, date_str: str,
) -> str | None:
    """편명이 있으면 booking URL 생성, 없으면 None."""
    flight_numbers = card.get("flight_numbers")
    if not flight_numbers:
        return None

    seg_dates = card.get("segment_dates") or []
    airports = card.get("segment_airports") or []

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


# --- 카드 추출 JS / 파서 (V1 _extract_js/_parse_flight_cards 그대로) -------


def extract_js() -> str:
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


def parse_cards(html: str) -> list[dict]:
    """JS가 주입한 #__fl__ div에서 구조화된 항공편 데이터를 추출."""
    m = re.search(r'id="__fl__"[^>]*>(.*?)</div>', html, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(unescape(m.group(1).strip()))
    except (json.JSONDecodeError, ValueError):
        return []


def make_scroll_js() -> str:
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


# --- 카드 → LegQuote/RtQuote ------------------------------------------------

_HHMM = re.compile(r"^\d{2}:\d{2}$")


def _valid_times(dep_time: object, arr_time: object) -> bool:
    """HH:MM 형식이 아닌 시각은 stay_minutes를 깨뜨리므로 카드를 버린다."""
    return (
        isinstance(dep_time, str)
        and isinstance(arr_time, str)
        and _HHMM.match(dep_time) is not None
        and _HHMM.match(arr_time) is not None
    )


def cards_to_legs(
    cards: list[dict], date_: date, dep: str, arr: str, search_url: str,
) -> list[LegQuote]:
    """flight_key로 dedupe(같은 키면 최저가 1건), 가격 오름차순."""
    date_str = date_.isoformat()
    best: dict[str, LegQuote] = {}
    for card in cards:
        dep_time = card.get("dep_time")
        arr_time = card.get("arr_time")
        if not _valid_times(dep_time, arr_time):
            continue
        dep_airport = card.get("dep_airport") or dep
        arr_airport = card.get("arr_airport") or arr
        if dep_airport != dep or arr_airport != arr:
            continue
        flight_numbers = card.get("flight_numbers") or []
        airline = airline_iata(card.get("airline", ""), flight_numbers)
        key = flight_key(
            date_, dep_airport, arr_airport, dep_time, arr_time, card.get("stops"), airline,
        )
        price = int(card["price"])
        existing = best.get(key)
        if existing is not None and existing.price <= price:
            continue
        best[key] = LegQuote(
            flight_key=key,
            airline_iata=airline,
            airline_name=card.get("airline", ""),
            flight_numbers=flight_numbers,
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_time=dep_time,
            arr_time=arr_time,
            duration_min=card.get("duration_min"),
            stops=card.get("stops"),
            price=price,
            booking_url=build_booking_url(card, dep, arr, date_str),
            search_url=search_url,
        )
    return sorted(best.values(), key=lambda leg: leg.price)


def cards_to_rts(
    cards: list[dict], out_date: date, dep: str, arr: str,
) -> list[RtQuote]:
    """왕복 페이지 카드(가격=왕복 총액)를 출국편 키로 dedupe(최저가), 가격 오름차순."""
    best: dict[str, RtQuote] = {}
    for card in cards:
        dep_time = card.get("dep_time")
        arr_time = card.get("arr_time")
        if not _valid_times(dep_time, arr_time):
            continue
        dep_airport = card.get("dep_airport") or dep
        arr_airport = card.get("arr_airport") or arr
        if dep_airport != dep or arr_airport != arr:
            continue
        flight_numbers = card.get("flight_numbers") or []
        airline = airline_iata(card.get("airline", ""), flight_numbers)
        key = flight_key(
            out_date, dep_airport, arr_airport, dep_time, arr_time, card.get("stops"), airline,
        )
        total_price = int(card["price"])
        existing = best.get(key)
        if existing is not None and existing.total_price <= total_price:
            continue
        best[key] = RtQuote(airline_iata=airline, out_flight_key=key, total_price=total_price)
    return sorted(best.values(), key=lambda rt: rt.total_price)


# --- 검색 실행 ---------------------------------------------------------------
#
# crawl4ai는 `_default_config()` 안에서 import한다 (미설치 환경 지원). 공개 시그니처는
# 브리프 §9.2 그대로(crawler, dep, arr, date(s)) — 별도 `config` 인자는 없다. crawl4ai
# 없이 상태 분기(ok/blocked/empty/error)만 검증하고 싶은 테스트는 컨트롤러 재정에 따라
# `monkeypatch.setattr(google_flights, "_default_config", lambda: <fake config>)`로 이
# 함수를 대체한다.


def _classify(cards: list[dict], html: str) -> Literal["ok", "blocked", "empty"]:
    if cards:
        return "ok"
    html_lower = html.lower()
    if any(marker in html_lower for marker in _BLOCKED_MARKERS):
        return "blocked"
    return "empty"


# 카드가 없는 페이지(차단 / 결과 없음)에서도 wait_for가 풀리도록 한다. 차단 표지는 V1과 같은
# 문자열, "결과 없음" 문구는 라이브 GF에서 검증하지 못한 보수적 추정(미검증).
_WAIT_FOR_JS = (
    "js:() => !!document.querySelector('li.pIav2d')"
    " || /unusual traffic|recaptcha|sorry\\/index/i.test(document.documentElement.innerHTML)"
    " || /항공편을 찾을 수 없|검색 결과가 없|No results|no flights/i.test(document.body.innerText)"
)


def _default_config() -> object | None:
    try:
        from crawl4ai import CrawlerRunConfig
    except ImportError:
        return None
    return CrawlerRunConfig(
        magic=True,
        js_code=[make_scroll_js(), extract_js()],
        wait_for=_WAIT_FOR_JS,
        delay_before_return_html=4.0,
        cache_mode="bypass",
        page_timeout=15000,
    )


def _is_wait_timeout(error_message: str | None) -> bool:
    """wait_for 타임아웃(=카드/차단/결과없음 표지가 안 뜸)이면 True. 네비게이션 실패(net::ERR_*)는 False."""
    message = (error_message or "").lower()
    if "net::err" in message:
        return False
    return "timeout" in message or "wait_for" in message or "waiting for" in message


def _outcome(
    result: CrawlResult,
) -> tuple[Literal["ok", "blocked", "empty", "error"], list[dict], str | None]:
    """크롤 결과 → (상태, 카드, 에러). 타임아웃 실패는 받은 HTML로 분류한다."""
    html = result.html or ""
    if not result.success:
        if not _is_wait_timeout(result.error_message):
            return "error", [], result.error_message
        return _classify([], html), [], None
    cards = parse_cards(html)
    return _classify(cards, html), cards, None


async def search_oneway(
    crawler: Crawler, dep: str, arr: str, date_: date,
) -> ProviderResult:
    start = time.perf_counter()
    config = _default_config()
    if config is None:
        return ProviderResult(status="error", legs=[], rts=[], error="crawl4ai not installed", seconds=0.0)

    url = build_oneway_url(dep, arr, date_)
    try:
        result = await crawler.arun(url=url, config=config)
    except Exception as e:  # noqa: BLE001 — 크롤러 예외는 error 상태로 흡수
        return ProviderResult(status="error", legs=[], rts=[], error=str(e), seconds=time.perf_counter() - start)

    seconds = time.perf_counter() - start
    status, cards, error = _outcome(result)
    legs = cards_to_legs(cards, date_, dep, arr, url) if status == "ok" else []
    return ProviderResult(status=status, legs=legs, rts=[], error=error, seconds=seconds)


async def search_roundtrip(
    crawler: Crawler, dep: str, arr: str, out_date: date, ret_date: date,
) -> ProviderResult:
    start = time.perf_counter()
    config = _default_config()
    if config is None:
        return ProviderResult(status="error", legs=[], rts=[], error="crawl4ai not installed", seconds=0.0)

    url = build_roundtrip_url(dep, arr, out_date, ret_date)
    try:
        result = await crawler.arun(url=url, config=config)
    except Exception as e:  # noqa: BLE001 — 크롤러 예외는 error 상태로 흡수
        return ProviderResult(status="error", legs=[], rts=[], error=str(e), seconds=time.perf_counter() - start)

    seconds = time.perf_counter() - start
    status, cards, error = _outcome(result)
    rts = cards_to_rts(cards, out_date, dep, arr) if status == "ok" else []
    return ProviderResult(status=status, legs=[], rts=rts, error=error, seconds=seconds)
