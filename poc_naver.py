"""
네이버 항공권 crawl4ai PoC — 브라우저 기반 크롤링
실행: python poc_naver.py

Naver 항공편 검색 페이지를 headless 브라우저로 접근하여
DOM에서 항공편 데이터를 추출한다.
"""

import asyncio
import json
import re
from datetime import date, timedelta

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
except ImportError:
    print("crawl4ai 미설치. pip install crawl4ai")
    exit(1)


def build_naver_url(origin, dest, dep_date, ret_date=None, trip_type="OW"):
    """
    네이버 항공권 검색 URL 생성.
    dep_date, ret_date: "YYYYMMDD" 형식
    """
    base = "https://flight.naver.com/flights/international"
    # OW: /ICN-NRT-20260421
    # RT: /ICN-NRT-20260421/NRT-ICN-20260424
    path = f"{base}/{origin}-{dest}-{dep_date}"
    if trip_type == "RT" and ret_date:
        path += f"/{dest}-{origin}-{ret_date}"
    params = f"?adult=1&fareType=Y&tripType={trip_type}"
    return path + params


# JS: 페이지 로딩 완료까지 스크롤
SCROLL_JS = """
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

# JS: DOM에서 항공편 데이터 추출 (결과를 #__nv__ div에 저장)
# 네이버 DOM 구조를 탐색하기 위해 우선 raw 정보를 최대한 수집한다
EXTRACT_JS = """
(function() {
    var results = [];

    // 네이버 항공편 카드 셀렉터 탐색
    // 알려진 셀렉터 후보들을 시도
    var selectors = [
        'div[class*="result"] div[class*="item"]',
        'div[class*="flight"] div[class*="item"]',
        'div[class*="domestic_Flight"] li',
        'ul[class*="result"] > li',
        'div[class*="concurrent_ConcurrentList"] > div',
        'div[class*="indivisual_IndivisualItem"]',
    ];

    var cards = [];
    var usedSelector = '';
    for (var i = 0; i < selectors.length; i++) {
        cards = document.querySelectorAll(selectors[i]);
        if (cards.length > 0) {
            usedSelector = selectors[i];
            break;
        }
    }

    // 페이지 내 주요 텍스트 컨텐츠 덤프 (디버깅용)
    var bodyText = document.body ? document.body.innerText.substring(0, 3000) : '';

    // 가격이 포함된 요소 찾기 (숫자+원 패턴)
    var priceElements = [];
    var allElements = document.querySelectorAll('*');
    for (var j = 0; j < allElements.length && priceElements.length < 20; j++) {
        var el = allElements[j];
        if (el.children.length === 0) {
            var txt = (el.textContent || '').trim();
            if (/[\\d,]+원/.test(txt) && txt.length < 30) {
                priceElements.push({
                    tag: el.tagName,
                    class: el.className,
                    text: txt,
                    parentClass: el.parentElement ? el.parentElement.className : ''
                });
            }
        }
    }

    var el = document.getElementById('__nv__');
    if (!el) {
        el = document.createElement('div');
        el.id = '__nv__';
        el.style.display = 'none';
        document.body.appendChild(el);
    }
    el.textContent = JSON.stringify({
        usedSelector: usedSelector,
        cardCount: cards.length,
        priceElements: priceElements,
        bodyTextPreview: bodyText,
        url: window.location.href,
        title: document.title,
    });
})();
"""


def parse_naver_result(raw_html):
    """#__nv__ div에서 추출 결과 파싱"""
    m = re.search(r'id="__nv__"[^>]*>(.*?)</div>', raw_html, re.DOTALL)
    if not m:
        return None
    try:
        from html import unescape
        return json.loads(unescape(m.group(1).strip()))
    except (json.JSONDecodeError, ValueError):
        return None


async def test_search(crawler, origin, dest, dep_date, ret_date=None, trip_type="OW"):
    url = build_naver_url(origin, dest, dep_date, ret_date, trip_type)
    label = f"{trip_type} {origin}→{dest} {dep_date}"
    if ret_date:
        label += f" ~ {ret_date}"

    print(f"\n{'='*60}")
    print(f"[TEST] {label}")
    print(f"  URL: {url}")
    print(f"{'='*60}")

    try:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                magic=True,
                js_code=[SCROLL_JS, EXTRACT_JS],
                delay_before_return_html=8.0,  # 네이버 SSE 로딩 대기
                cache_mode="bypass",
                page_timeout=30000,
            ),
        )
    except Exception as e:
        print(f"  크롤링 에러: {e}")
        return

    if not result.success:
        print(f"  크롤링 실패: {result.error_message}")
        return

    print(f"  크롤링 성공! HTML 길이: {len(result.html or '')}자")

    data = parse_naver_result(result.html or "")
    if data:
        print(f"  페이지 제목: {data.get('title')}")
        print(f"  최종 URL: {data.get('url')}")
        print(f"  사용된 셀렉터: {data.get('usedSelector') or '(없음)'}")
        print(f"  카드 수: {data.get('cardCount')}")
        print(f"\n  가격 요소 ({len(data.get('priceElements', []))}개):")
        for pe in data.get("priceElements", [])[:10]:
            print(f"    <{pe['tag']} class=\"{pe['class'][:60]}\">{pe['text']}")
        print(f"\n  본문 텍스트 미리보기:")
        body = data.get("bodyTextPreview", "")
        # 처음 1000자만 출력
        for line in body[:1000].split("\n"):
            line = line.strip()
            if line:
                print(f"    {line}")
    else:
        print("  #__nv__ 데이터 추출 실패")
        # HTML 일부 출력
        html = result.html or ""
        print(f"  HTML 앞부분:\n{html[:500]}")


async def main():
    dep = (date.today() + timedelta(days=14)).strftime("%Y%m%d")
    ret = (date.today() + timedelta(days=17)).strftime("%Y%m%d")

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

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # 1) 편도 테스트
        await test_search(crawler, "ICN", "NRT", dep, trip_type="OW")

        # 2) 왕복 테스트
        await test_search(crawler, "ICN", "NRT", dep, ret, trip_type="RT")

        # 3) 귀국편 편도
        await test_search(crawler, "NRT", "ICN", ret, trip_type="OW")

    print("\n✅ PoC 완료")


if __name__ == "__main__":
    asyncio.run(main())
