#!/usr/bin/env python3
"""
Google Flights 크롤링 독립 테스트 스크립트.

프로젝트 의존성 없이 crawl4ai만 설치하면 어디서든 실행 가능.
data-travelimpactmodelwebsiteurl에서 편명 추출 + booking URL 생성 검증.

설치:
    pip install crawl4ai
    crawl4ai-setup

실행:
    python standalone_flight_test.py
"""

import asyncio
import base64
import json
import re
import time
from html import unescape

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# ─────────────────────────────────────────────
#  테스트 케이스 — 실제 노선 URL로 교체하세요
# ─────────────────────────────────────────────
TEST_CASES = [
    {"label": "ICN→NRT 05-01", "dep": "ICN", "arr": "NRT", "date": "2026-05-01",
     "url": "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTAxagcIARIDSUNOcgcIARIDTlJUQAFIAXABggELCP___________wGYAQI&tfu=EgYIABAAGAA&hl=ko&curr=KRW"},
]

# ─────────────────────────────────────────────
#  Protobuf 인코딩 (booking URL 생성용)
# ─────────────────────────────────────────────
def _pb_varint(value: int) -> bytes:
    result = b""
    while value > 0x7F:
        result += bytes([0x80 | (value & 0x7F)])
        value >>= 7
    result += bytes([value])
    return result


def _pb_field(field_num: int, wire_type: int, data: int | bytes) -> bytes:
    tag = _pb_varint((field_num << 3) | wire_type)
    if wire_type == 0:
        return tag + _pb_varint(data)
    return tag + _pb_varint(len(data)) + data


def _pb_string(field_num: int, s: str) -> bytes:
    return _pb_field(field_num, 2, s.encode())


def _build_booking_tfs(
    date_str: str, segments: list[dict], origin: str, destination: str,
) -> str:
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


def _build_booking_url(
    flight: dict, dep: str, arr: str, date_str: str,
) -> str | None:
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


# ─────────────────────────────────────────────
#  JS: 스크롤 + 항공편 카드 추출
# ─────────────────────────────────────────────
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
            if (parts.length < 5) continue;
            if (i === 0) airports.push(parts[0]);
            airports.push(parts[1]);
            fns.push(parts[2] + ' ' + parts[3]);
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

        var priceEl = card.querySelector('.YMlIz.FpEdX.jLMuyc > span[aria-label]')
                   || card.querySelector('.YMlIz.FpEdX span[aria-label]');
        if (!priceEl) continue;
        var priceLabel = priceEl.getAttribute('aria-label') || '';
        var priceM = priceLabel.match(/^([\\d,]+)/);
        if (!priceM) continue;
        var price = parseInt(priceM[1].replace(/,/g, ''));
        if (price < 20000 || price > 3000000) continue;

        var depEl = card.querySelector('.wtdjmc.YMlIz');
        var arrEl = card.querySelector('.XWcVob.YMlIz');

        var stopsEl = card.querySelector('.VG3hNb');
        var stopsText = stopsEl ? stopsEl.textContent.trim() : '';
        if (!stopsText) {
            var tw = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
            while (tw.nextNode()) {
                var txt = tw.currentNode.textContent.trim();
                if (txt === '직항') { stopsText = '직항'; break; }
                var sm = txt.match(/경유\\s*(\\d+)회/);
                if (sm) { stopsText = sm[1]; break; }
            }
        }
        var stops = stopsText === '직항' ? 0 : (parseInt(stopsText) || null);

        var durEl = card.querySelector('.gvkrdb');
        var durText = durEl ? (durEl.getAttribute('aria-label') || durEl.textContent || '') : '';
        var durM = durText.match(/(\\d+)시간(?:\\s*(\\d+)분)?/);
        var duration_min = durM ? parseInt(durM[1]) * 60 + parseInt(durM[2] || 0) : null;

        var airlineEl = card.querySelector('.h1fkLb span');
        var airline = airlineEl ? airlineEl.textContent.trim() : '';

        var depAirport = null, arrAirport = null;
        var airportEls = card.querySelectorAll('.iCvNQ');
        if (airportEls.length >= 2) {
            depAirport = airportEls[0].textContent.trim();
            arrAirport = airportEls[airportEls.length - 1].textContent.trim();
        }

        var itin = extractItinerary(card);

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
    m = re.search(r'id="__fl__"[^>]*>(.*?)</div>', raw_html, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(unescape(m.group(1).strip()))
    except (json.JSONDecodeError, ValueError):
        return []


# ─────────────────────────────────────────────
#  출력
# ─────────────────────────────────────────────
def print_flights(flights: list[dict], dep: str, arr: str, date: str):
    if not flights:
        print("  ⚠️  추출 0건")
        return

    print(f"  ✅ {len(flights)}건 추출")

    with_fn = sum(1 for f in flights if f.get("flight_numbers"))
    print(f"  📋 편명 추출: {with_fn}/{len(flights)}건 "
          f"({with_fn / len(flights) * 100:.0f}%)")

    booking_ok = sum(1 for f in flights if _build_booking_url(f, dep, arr, date))
    print(f"  🔗 booking URL: {booking_ok}/{len(flights)}건 "
          f"({booking_ok / len(flights) * 100:.0f}%)")

    for i, f in enumerate(flights[:5]):
        stops_str = "직항" if f.get("stops") == 0 else f"{f.get('stops', '?')}회 경유"
        dur = f.get("duration_min")
        dur_str = f"{dur // 60}h{dur % 60:02d}m" if dur else "??"
        fn_list = f.get("flight_numbers", [])
        fn_str = ", ".join(fn_list) if fn_list else "(없음)"
        ap_list = f.get("segment_airports", [])
        ap_str = "→".join(ap_list) if ap_list else ""
        booking_url = _build_booking_url(f, dep, arr, date)

        print(f"    [{i + 1}] {f.get('airline', '?'):<12} "
              f"{f.get('dep_airport', '?')}→{f.get('arr_airport', '?')}  "
              f"{f.get('dep_time', '??')}~{f.get('arr_time', '??')}  "
              f"{stops_str}  {dur_str}  ₩{f.get('price', 0):,}")
        print(f"         편명: {fn_str}  경로: {ap_str}")
        if booking_url:
            print(f"         ✅ {booking_url[:100]}...")
        else:
            print(f"         🔍 search only")

    if len(flights) > 5:
        print(f"    ... 외 {len(flights) - 5}건")


def print_data_quality(all_results: list[dict]):
    if not all_results:
        return
    fields = [
        "price", "dep_time", "arr_time", "stops", "duration_min",
        "airline", "dep_airport", "arr_airport",
        "flight_numbers", "segment_airports",
    ]
    print(f"\n  [데이터 품질]")
    print(f"  {'필드':<20} {'null/빈':>8}  {'샘플'}")
    print(f"  {'-' * 60}")
    for f in fields:
        vals = [r.get(f) for r in all_results]
        if f in ("flight_numbers", "segment_airports"):
            null_cnt = sum(1 for v in vals if not v)
            sample = next((v for v in vals if v), "N/A")
        else:
            null_cnt = sum(1 for v in vals if v is None or v == "")
            sample = next((v for v in vals if v is not None and v != ""), "N/A")
        pct = null_cnt / len(vals) * 100
        flag = "⚠️ " if pct > 30 else "✅"
        print(f"  {flag} {f:<18} {pct:>6.1f}%   {sample}")


# ─────────────────────────────────────────────
#  메인
# ─────────────────────────────────────────────
async def main():
    urls = [c["url"] for c in TEST_CASES]

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

    run_config = CrawlerRunConfig(
        magic=True,
        js_code=[_make_scroll_js(), _extract_js()],
        wait_for="js:() => !!document.querySelector('li.pIav2d')",
        delay_before_return_html=4.0,
        cache_mode=CacheMode.BYPASS,
    )

    print(f"\n{'=' * 60}")
    print(f"  Google Flights 편명 추출 + Booking URL 검증")
    print(f"  URL: {len(urls)}개")
    print(f"{'=' * 60}\n")

    async with AsyncWebCrawler(config=browser_config) as crawler:
        start = time.perf_counter()
        results = await crawler.arun_many(urls=urls, config=run_config)
        elapsed = time.perf_counter() - start

    print(f"⏱  크롤링: {elapsed:.2f}s")
    print("=" * 60)

    all_flights: list[dict] = []
    all_metas: list[dict] = []

    for result, meta in zip(results, TEST_CASES):
        print(f"\n▶ {meta['label']}  ({meta['dep']}→{meta['arr']}  {meta['date']})")

        if not result.success:
            print(f"  ❌ 실패: {result.error_message}")
            continue

        flights = _parse_flight_cards(result.html or "")
        print_flights(flights, meta["dep"], meta["arr"], meta["date"])

        for f in flights:
            all_flights.append(f)
            all_metas.append(meta)

    # 전체 요약
    print(f"\n{'=' * 60}")
    print(f"  전체: {len(all_flights)}건")

    if all_flights:
        total_booking = sum(
            1 for f, m in zip(all_flights, all_metas)
            if _build_booking_url(f, m["dep"], m["arr"], m["date"])
        )
        print(f"  booking URL 성공: {total_booking}/{len(all_flights)}건 "
              f"({total_booking / len(all_flights) * 100:.1f}%)")

    print_data_quality(all_flights)

    # JSON 덤프
    dump = []
    for f, m in zip(all_flights, all_metas):
        booking_url = _build_booking_url(f, m["dep"], m["arr"], m["date"])
        dump.append({**f, "_dep": m["dep"], "_arr": m["arr"], "_date": m["date"],
                     "_booking_url": booking_url, "_search_url": m["url"]})

    with open("flight_extraction_dump.json", "w", encoding="utf-8") as fp:
        json.dump(dump, fp, ensure_ascii=False, indent=2)
    print(f"\n  💾 → flight_extraction_dump.json")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
