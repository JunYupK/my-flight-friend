#!/usr/bin/env python3
"""
Google Flights 카드 DOM 구조 진단 + 항공편 데이터 추출 테스트.

프로젝트 의존성 없이 crawl4ai만 설치하면 어디서든 실행 가능.
카드의 <a href>, data 속성, jsaction 등을 덤프하여
네비게이션 URL 추출 가능 여부를 진단합니다.

설치:
    pip install crawl4ai
    crawl4ai-setup

실행:
    python standalone_flight_test.py
"""

import asyncio
import json
import re
import time
from html import unescape

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# ─────────────────────────────────────────────
#  테스트 케이스
# ─────────────────────────────────────────────
TEST_CASES = [
    {"label": "ICN→NRT 05-01", "dep": "ICN", "arr": "NRT", "date": "2026-05-01",
     "url": "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTAxagcIARIDSUNOcgcIARIDTlJUQAFIAXABggELCP___________wGYAQI&tfu=EgYIABAAGAA&hl=ko&curr=KRW"},
]

# ─────────────────────────────────────────────
#  JS 1: 스크롤
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

# ─────────────────────────────────────────────
#  JS 2: 기존 항공편 데이터 추출 (간소화)
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
#  JS 3: 카드 DOM 구조 진단 (핵심)
# ─────────────────────────────────────────────
def _diagnose_card_structure_js() -> str:
    return """(function() {
    var cards = Array.from(document.querySelectorAll('li.pIav2d'));
    var diag = [];

    for (var i = 0; i < Math.min(cards.length, 5); i++) {
        var card = cards[i];
        var info = { cardIndex: i };

        // 1. <a href> 태그 탐색
        var links = Array.from(card.querySelectorAll('a[href]'));
        info.a_tags = links.map(function(a) {
            return {
                href: a.href,
                text: a.textContent.trim().substring(0, 80),
                className: a.className,
                ariaLabel: a.getAttribute('aria-label') || ''
            };
        });

        // 2. li 자체의 속성
        var liAttrs = {};
        for (var j = 0; j < card.attributes.length; j++) {
            var attr = card.attributes[j];
            liAttrs[attr.name] = attr.value.substring(0, 300);
        }
        info.li_attrs = liAttrs;

        // 3. 카드 내 클릭 가능 요소 탐색 (button, [role=button], [jsaction])
        var clickables = Array.from(card.querySelectorAll('button, [role="button"], [role="link"], [jsaction], [data-flt]'));
        info.clickable_elements = clickables.slice(0, 10).map(function(el) {
            var attrs = {};
            for (var k = 0; k < el.attributes.length; k++) {
                attrs[el.attributes[k].name] = el.attributes[k].value.substring(0, 300);
            }
            return {
                tag: el.tagName.toLowerCase(),
                text: el.textContent.trim().substring(0, 80),
                attrs: attrs
            };
        });

        // 4. data-* 속성을 가진 모든 요소 (처음 15개)
        var dataEls = Array.from(card.querySelectorAll('[data-ved], [data-flt], [data-travelid], [data-routeid]'));
        info.data_attr_elements = dataEls.slice(0, 15).map(function(el) {
            var attrs = {};
            for (var k = 0; k < el.attributes.length; k++) {
                if (el.attributes[k].name.startsWith('data-')) {
                    attrs[el.attributes[k].name] = el.attributes[k].value.substring(0, 500);
                }
            }
            return {
                tag: el.tagName.toLowerCase(),
                className: el.className.substring(0, 100),
                dataAttrs: attrs
            };
        });

        // 5. outerHTML 스니펫 (처음 1000자)
        info.outerHTML_snippet = card.outerHTML.substring(0, 1000);

        // 6. 카드 내 모든 고유 class 이름 수집
        var allClasses = new Set();
        var allEls = card.querySelectorAll('*');
        for (var k = 0; k < allEls.length; k++) {
            var cls = allEls[k].className;
            if (typeof cls === 'string') {
                cls.split(/\\s+/).forEach(function(c) { if (c) allClasses.add(c); });
            }
        }
        info.unique_classes = Array.from(allClasses).sort();

        diag.push(info);
    }

    var el = document.getElementById('__card_diag__');
    if (!el) {
        el = document.createElement('div');
        el.id = '__card_diag__';
        el.style.display = 'none';
        document.body.appendChild(el);
    }
    el.textContent = JSON.stringify(diag);
})();"""


# ─────────────────────────────────────────────
#  파싱 헬퍼
# ─────────────────────────────────────────────
def _parse_div_json(raw_html: str, div_id: str) -> list | dict | None:
    m = re.search(rf'id="{div_id}"[^>]*>(.*?)</div>', raw_html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(unescape(m.group(1).strip()))
    except (json.JSONDecodeError, ValueError):
        return None


# ─────────────────────────────────────────────
#  진단 결과 출력
# ─────────────────────────────────────────────
def print_card_diagnosis(diag: list[dict]):
    print(f"\n{'=' * 60}")
    print(f"  카드 DOM 구조 진단 결과 ({len(diag)}개 카드)")
    print(f"{'=' * 60}")

    for card in diag:
        idx = card["cardIndex"]
        print(f"\n  ── 카드 #{idx} ──")

        # a 태그
        a_tags = card.get("a_tags", [])
        if a_tags:
            print(f"  ✅ <a> 태그: {len(a_tags)}개")
            for a in a_tags[:5]:
                href = a["href"]
                # booking URL인지 확인
                if "/booking" in href:
                    print(f"     🎯 BOOKING: {href[:120]}")
                elif "/flights" in href:
                    print(f"     ✈️  FLIGHT:  {href[:120]}")
                else:
                    print(f"     🔗 OTHER:   {href[:120]}")
                if a["text"]:
                    print(f"        text: {a['text'][:60]}")
        else:
            print(f"  ❌ <a> 태그 없음")

        # li 속성
        li_attrs = card.get("li_attrs", {})
        interesting = {k: v for k, v in li_attrs.items()
                       if k not in ("class", "style") and len(v) > 0}
        if interesting:
            print(f"  📋 li 속성:")
            for k, v in interesting.items():
                print(f"     {k}: {v[:100]}")

        # 클릭 가능 요소
        clickables = card.get("clickable_elements", [])
        if clickables:
            print(f"  🖱️  클릭 가능 요소: {len(clickables)}개")
            for el in clickables[:5]:
                attrs_str = ", ".join(f"{k}={v[:50]}" for k, v in el["attrs"].items()
                                      if k in ("jsaction", "jscontroller", "data-flt", "role", "aria-label"))
                print(f"     <{el['tag']}> {attrs_str}")
                if el["text"]:
                    print(f"       text: {el['text'][:60]}")

        # data 속성 요소
        data_els = card.get("data_attr_elements", [])
        if data_els:
            print(f"  📦 data-* 속성 요소: {len(data_els)}개")
            for el in data_els[:5]:
                for dk, dv in el["dataAttrs"].items():
                    print(f"     <{el['tag']}.{el['className'][:30]}> {dk}={dv[:80]}")


def print_flights_summary(flights: list[dict]):
    if not flights:
        print("  ⚠️  추출 0건")
        return
    print(f"  ✅ {len(flights)}건 추출")
    for i, f in enumerate(flights[:3]):
        stops_str = "직항" if f.get("stops") == 0 else f"{f.get('stops', '?')}회 경유"
        dur = f.get("duration_min")
        dur_str = f"{dur // 60}h{dur % 60:02d}m" if dur else "??"
        print(f"    [{i + 1}] {f.get('airline', '?'):<12} "
              f"{f.get('dep_airport', '?')}→{f.get('arr_airport', '?')}  "
              f"{f.get('dep_time', '??')}~{f.get('arr_time', '??')}  "
              f"{stops_str}  {dur_str}  ₩{f.get('price', 0):,}")
    if len(flights) > 3:
        print(f"    ... 외 {len(flights) - 3}건")


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
        js_code=[_make_scroll_js(), _extract_js(), _diagnose_card_structure_js()],
        wait_for="js:() => !!document.querySelector('li.pIav2d')",
        delay_before_return_html=4.0,
        cache_mode=CacheMode.BYPASS,
    )

    print(f"\n{'=' * 60}")
    print(f"  Google Flights 카드 DOM 구조 진단")
    print(f"  URL: {len(urls)}개")
    print(f"{'=' * 60}\n")

    async with AsyncWebCrawler(config=browser_config) as crawler:
        start = time.perf_counter()
        results = await crawler.arun_many(urls=urls, config=run_config)
        elapsed = time.perf_counter() - start

    print(f"⏱  크롤링: {elapsed:.2f}s")

    all_diag = []

    for result, meta in zip(results, TEST_CASES):
        print(f"\n▶ {meta['label']}  ({meta['dep']}→{meta['arr']}  {meta['date']})")

        if not result.success:
            print(f"  ❌ 크롤링 실패: {result.error_message}")
            continue

        html = result.html or ""

        # 항공편 데이터 추출 (참고용)
        flights = _parse_div_json(html, "__fl__") or []
        print_flights_summary(flights)

        # 카드 DOM 구조 진단
        diag = _parse_div_json(html, "__card_diag__")
        if diag:
            print_card_diagnosis(diag)
            all_diag.extend(diag)
        else:
            print("  ⚠️  카드 진단 데이터 없음")

    # JSON 덤프
    with open("card_structure_dump.json", "w", encoding="utf-8") as fp:
        json.dump(all_diag, fp, ensure_ascii=False, indent=2)
    print(f"\n{'=' * 60}")
    print(f"  💾 → card_structure_dump.json ({len(all_diag)}개 카드)")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
