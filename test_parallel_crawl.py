"""
병렬 크롤링 동작 검증 스크립트 — 완전 독립형 (flight_monitor 패키지 불필요)

의존성: pip install crawl4ai
        playwright install chromium

사용법:
    python test_parallel_crawl.py
    python test_parallel_crawl.py --days 3 --parallel 2
    python test_parallel_crawl.py --days 2 --parallel 1  # 순차 비교용

TFS 템플릿 설정 방법:
    1. Google Flights에서 "인천(ICN) → 도쿄(TYO)" 검색 (날짜 아무거나)
    2. 결과 페이지 URL에서 tfs=XXXXXX 부분을 복사
    3. 아래 TFS_TEMPLATES 딕셔너리에 붙여넣기
    또는 운영 중인 서비스 → Settings → Airports 탭에서 확인
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import time
from datetime import date, timedelta
from html import unescape

# ──────────────────────────────────────────────────────────────────────
# 설정: 여기만 수정
# ──────────────────────────────────────────────────────────────────────

ORIGIN = "ICN"

# key: "출발_도착" IATA 코드 / value: Google Flights URL의 tfs= 값 (또는 전체 URL)
# 아래 예시를 실제 값으로 교체. 템플릿 없는 공항은 자동 스킵.
TFS_TEMPLATES: dict[str, str] = {
    "ICN_TYO": "",   # 예: "CAAqBwgDEgNJQ04..."  또는 전체 URL 붙여넣기 가능
    "TYO_ICN": "",
    "ICN_OSA": "",
    "OSA_ICN": "",
    # 더 추가하려면: "ICN_OKA": "", "OKA_ICN": "", 등
}

# 테스트할 공항 목록 (코드: 이름)
AIRPORTS: dict[str, str] = {
    "TYO": "도쿄",
    "OSA": "오사카",
}

BATCH_SIZE = 5        # 배치당 동시 URL 수
REQUEST_DELAY = 1.0   # 배치 간 대기 (초)
TOPK = 3              # 날짜별 최대 결과 수 (테스트용으로 축소)

# ──────────────────────────────────────────────────────────────────────
# TFS URL 빌더 (collector_google_flights.py에서 발췌)
# ──────────────────────────────────────────────────────────────────────

_TFS_DATE_RE = re.compile(rb"\d{4}-\d{2}-\d{2}")


def _build_tfs_url(dep: str, arr: str, date_str: str) -> str | None:
    template = TFS_TEMPLATES.get(f"{dep}_{arr}", "")
    if not template:
        return None
    if template.startswith("http"):
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(template).query)
        tfs_list = qs.get("tfs")
        if not tfs_list:
            return None
        template = tfs_list[0]
    raw = base64.urlsafe_b64decode(template + "==")
    m = _TFS_DATE_RE.search(raw)
    if m:
        raw = raw[:m.start()] + date_str.encode() + raw[m.end():]
    tfs = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return f"https://www.google.com/travel/flights/search?tfs={tfs}&curr=KRW&hl=ko"


# ──────────────────────────────────────────────────────────────────────
# JS 인젝션 코드 (collector_google_flights.py에서 발췌)
# ──────────────────────────────────────────────────────────────────────

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
            arr_airport: arrAirport,
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


# ──────────────────────────────────────────────────────────────────────
# 크롤링 로직
# ──────────────────────────────────────────────────────────────────────

async def _crawl_route(crawler, airport_code: str, start_date: date, end_date: date) -> dict:
    """공항 하나에 대해 지정 날짜 범위 크롤링. 결과 통계 반환."""
    from crawl4ai import CrawlerRunConfig

    urls, metas = [], []
    d = start_date
    while d <= end_date:
        date_str = d.strftime("%Y-%m-%d")
        for dep, arr, direction in [
            (ORIGIN, airport_code, "out"),
            (airport_code, ORIGIN, "in"),
        ]:
            url = _build_tfs_url(dep, arr, date_str)
            if url:
                urls.append(url)
                metas.append({"date": date_str, "direction": direction})
        d += timedelta(days=1)

    if not urls:
        return {"airport": airport_code, "urls": 0, "flights": 0, "skipped": True}

    config = CrawlerRunConfig(
        magic=True,
        js_code=[_make_scroll_js(), _extract_js()],
        wait_for="js:() => !!document.querySelector('li.pIav2d')",
        delay_before_return_html=4.0,
        cache_mode="bypass",
        page_timeout=30000,
    )

    total_flights = 0
    for i in range(0, len(urls), BATCH_SIZE):
        batch_urls = urls[i:i + BATCH_SIZE]
        batch_metas = metas[i:i + BATCH_SIZE]
        url_to_meta = dict(zip(batch_urls, batch_metas))

        try:
            results = await crawler.arun_many(urls=batch_urls, config=config)
        except Exception as e:
            print(f"  [{airport_code}] batch {i // BATCH_SIZE} 오류: {e}")
            continue

        for result in results:
            meta = url_to_meta.get(result.url, {})
            if not result.success:
                continue
            flights = _parse_flight_cards(result.html or "")
            total_flights += len(flights[:TOPK])
            if flights:
                cheapest = sorted(flights, key=lambda x: x["price"])[0]
                print(f"  [{airport_code}] {meta.get('date')} {meta.get('direction')}: "
                      f"{len(flights)}건, 최저 {cheapest['price']:,}원 ({cheapest.get('airline','')})")

        if i + BATCH_SIZE < len(urls):
            await asyncio.sleep(REQUEST_DELAY)

    return {"airport": airport_code, "urls": len(urls), "flights": total_flights, "skipped": False}


async def _crawl_airport_parallel(
    airport_code: str,
    airport_name: str,
    start_date: date,
    end_date: date,
    semaphore: asyncio.Semaphore,
) -> tuple[str, dict, float]:
    """세마포어로 동시 실행 수를 제한하며 단일 공항 크롤링."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig

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

    t0 = time.perf_counter()
    async with semaphore:
        print(f"[{airport_code}({airport_name})] 시작 — {start_date} ~ {end_date}")
        async with AsyncWebCrawler(config=browser_config) as crawler:
            stats = await _crawl_route(crawler, airport_code, start_date, end_date)
        elapsed = time.perf_counter() - t0
        print(f"[{airport_code}] 완료: {stats['flights']}건, {elapsed:.1f}s"
              + (" (TFS 없음, 스킵)" if stats["skipped"] else ""))
        return airport_code, stats, elapsed


async def run_parallel(airports: dict, start_date: date, end_date: date, parallel: int):
    semaphore = asyncio.Semaphore(parallel)
    tasks = [
        _crawl_airport_parallel(code, name, start_date, end_date, semaphore)
        for code, name in airports.items()
    ]

    t_total = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_elapsed = time.perf_counter() - t_total

    print("\n" + "=" * 60)
    print(f"[결과 요약] parallel={parallel}, 날짜 범위={end_date - start_date + timedelta(days=1)}일")
    total_flights = 0
    for r in results:
        if isinstance(r, BaseException):
            print(f"  ERROR: {r}")
        else:
            code, stats, elapsed = r
            status = "SKIPPED" if stats["skipped"] else f"{stats['flights']}건 / {elapsed:.1f}s"
            print(f"  {code}: {status}")
            total_flights += stats.get("flights", 0)
    print(f"  총계: {total_flights}건, 전체 소요 {total_elapsed:.1f}s")
    print("=" * 60)
    return total_elapsed


# ──────────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────────

def main():
    try:
        import crawl4ai  # noqa: F401
    except ImportError:
        print("ERROR: crawl4ai 미설치\n  pip install crawl4ai && playwright install chromium")
        return

    # TFS 설정 검증
    configured = {k: v for k, v in TFS_TEMPLATES.items() if v.strip()}
    if not configured:
        print("⚠  TFS_TEMPLATES가 비어 있습니다.")
        print("   이 파일 상단 TFS_TEMPLATES 딕셔너리에 Google Flights tfs= 값을 채워주세요.")
        print()
        print("   [tfs= 값 얻는 법]")
        print("   1. https://www.google.com/travel/flights 에서 ICN → TYO 검색")
        print("   2. 결과 URL에서 tfs=XXXX 부분 복사")
        print("   3. TFS_TEMPLATES['ICN_TYO'] = 'XXXX' 로 설정")
        print("   (전체 URL 붙여넣기도 됨)")
        return

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3, help="수집 날짜 범위 (기본 3일)")
    parser.add_argument("--parallel", type=int, default=2, help="동시 실행 공항 수 (기본 2)")
    args = parser.parse_args()

    # TFS 없는 공항 필터
    testable = {
        code: name for code, name in AIRPORTS.items()
        if TFS_TEMPLATES.get(f"ICN_{code}") or TFS_TEMPLATES.get(f"{code}_ICN")
    }
    if not testable:
        print("⚠  AIRPORTS에 등록된 공항 중 TFS_TEMPLATES가 설정된 공항이 없습니다.")
        return

    today = date.today()
    end_date = today + timedelta(days=args.days - 1)

    print(f"테스트 공항: {list(testable.keys())}")
    print(f"날짜 범위:   {today} ~ {end_date} ({args.days}일)")
    print(f"동시 실행:   {args.parallel}개 공항")
    print(f"예상 URL:    {len(testable)} 공항 × {args.days}일 × 2방향 = {len(testable) * args.days * 2}개")
    print("-" * 60)

    asyncio.run(run_parallel(testable, today, end_date, args.parallel))


if __name__ == "__main__":
    main()
