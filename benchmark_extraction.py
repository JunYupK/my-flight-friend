#!/usr/bin/env python3
"""
Google Flights 편명 추출 + booking URL 생성 검증 스크립트.

실제 Google Flights 페이지를 크롤링하여:
1. 기존 항공편 데이터(가격, 시간, 항공사 등) 추출 검증
2. 새로 추가한 편명(flight_numbers) 추출률 확인
3. booking URL 생성 성공률 확인
4. 생성된 booking URL 유효성 검증

사용법:
    python benchmark_extraction.py
"""

import asyncio
import json
import re
import sys
import time
from html import unescape

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# flight_monitor 모듈에서 실제 로직 임포트
from flight_monitor.collector_google_flights import (
    _extract_js,
    _make_scroll_js,
    _build_booking_url,
    _AIRLINE_IATA,
)

# ─────────────────────────────────────────────
#  테스트 URL
#  주의: tfs= 값은 실제 노선에 맞는 값으로 교체해야 합니다.
#  아래는 airports 테이블에 등록된 tfs 템플릿 기반 URL입니다.
# ─────────────────────────────────────────────
TEST_CASES = [
    # ICN → TYO (NRT)
    {"label": "ICN→NRT 05-01", "dep": "ICN", "arr": "NRT", "date": "2026-05-01",
     "url": "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTAxagcIARIDSUNOcgcIARIDQ0VCQAFIAXABggELCP___________wGYAQI&tfu=EgYIABAAGAA&curr=KRW&hl=ko"},
    {"label": "NRT→ICN 05-01", "dep": "NRT", "arr": "ICN", "date": "2026-05-01",
     "url": "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTAxagcIARIDQ0VCcgcIARIDSUNOQAFIAXABggELCP___________wGYAQI&tfu=EgYIABAAGAA&curr=KRW&hl=ko"},
    # ICN → OSA (KIX)
    {"label": "ICN→KIX 05-01", "dep": "ICN", "arr": "KIX", "date": "2026-05-01",
     "url": "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTAxagcIARIDSUNOcgcIARIDQ0VCQAFIAXABggELCP___________wGYAQI&tfu=EgYIABAAGAA&curr=KRW&hl=ko"},
    {"label": "KIX→ICN 05-01", "dep": "KIX", "arr": "ICN", "date": "2026-05-01",
     "url": "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTAxagcIARIDQ0VCcgcIARIDSUNOQAFIAXABggELCP___________wGYAQI&tfu=EgYIABAAGAA&curr=KRW&hl=ko"},
    # ICN → FUK
    {"label": "ICN→FUK 05-01", "dep": "ICN", "arr": "FUK", "date": "2026-05-01",
     "url": "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTAxagcIARIDSUNOcgcIARIDQ0VCQAFIAXABggELCP___________wGYAQI&tfu=EgYIABAAGAA&curr=KRW&hl=ko"},
    {"label": "FUK→ICN 05-01", "dep": "FUK", "arr": "ICN", "date": "2026-05-01",
     "url": "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTAxagcIARIDQ0VCcgcIARIDSUNOQAFIAXABggELCP___________wGYAQI&tfu=EgYIABAAGAA&curr=KRW&hl=ko"},
]


# ─────────────────────────────────────────────
#  HTML 파싱
# ─────────────────────────────────────────────
def _parse_flight_cards(raw_html: str) -> list[dict]:
    m = re.search(r'id="__fl__"[^>]*>(.*?)</div>', raw_html, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(unescape(m.group(1).strip()))
    except (json.JSONDecodeError, ValueError):
        return []


# ─────────────────────────────────────────────
#  크롤러 설정
# ─────────────────────────────────────────────
def make_browser_config() -> BrowserConfig:
    return BrowserConfig(
        headless=True,
        viewport={"width": 1920, "height": 1080},
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )


def make_run_config() -> CrawlerRunConfig:
    return CrawlerRunConfig(
        magic=True,
        js_code=[_make_scroll_js(), _extract_js()],
        wait_for="js:() => !!document.querySelector('li.pIav2d')",
        delay_before_return_html=4.0,
        cache_mode=CacheMode.BYPASS,
    )


# ─────────────────────────────────────────────
#  출력 헬퍼
# ─────────────────────────────────────────────
def print_flights(flights: list[dict], dep: str, arr: str, date: str):
    if not flights:
        print("  ⚠️  추출 0건")
        return

    print(f"  ✅ {len(flights)}건 추출")

    # 편명 추출 통계
    with_fn = sum(1 for f in flights if f.get("flight_numbers"))
    print(f"  📋 편명 추출: {with_fn}/{len(flights)}건 "
          f"({with_fn/len(flights)*100:.0f}%)")

    # booking URL 생성 통계
    booking_ok = 0
    for f in flights:
        url = _build_booking_url(f, dep, arr, date)
        if url:
            booking_ok += 1

    print(f"  🔗 booking URL 생성: {booking_ok}/{len(flights)}건 "
          f"({booking_ok/len(flights)*100:.0f}%)")

    # 상위 5개 상세 출력
    for i, f in enumerate(flights[:5]):
        stops_str = "직항" if f.get("stops") == 0 else f"{f.get('stops', '?')}회 경유"
        dur = f.get("duration_min")
        dur_str = f"{dur // 60}h{dur % 60:02d}m" if dur else "??"

        fn_list = f.get("flight_numbers", [])
        fn_str = ", ".join(fn_list) if fn_list else "(편명 없음)"

        seg_ap = f.get("segment_airports", [])
        seg_str = "→".join(seg_ap) if seg_ap else ""

        booking_url = _build_booking_url(f, dep, arr, date)
        booking_status = "✅ booking" if booking_url else "🔍 search"

        print(f"    [{i+1}] {f.get('airline', '?'):<12} "
              f"{f.get('dep_airport', '?')}→{f.get('arr_airport', '?')}  "
              f"{f.get('dep_time', '??')}~{f.get('arr_time', '??')}  "
              f"{stops_str}  {dur_str}  "
              f"₩{f.get('price', 0):,}")
        print(f"         편명: {fn_str}"
              f"{('  경유지: ' + seg_str) if seg_str else ''}")
        print(f"         {booking_status}"
              f"{('  ' + booking_url[:80] + '...') if booking_url else ''}")

    if len(flights) > 5:
        print(f"    ... 외 {len(flights) - 5}건")


def print_data_quality(all_results: list[dict]):
    """필드별 null 비율 체크"""
    if not all_results:
        return
    fields = [
        "price", "dep_time", "arr_time", "stops", "duration_min",
        "airline", "dep_airport", "arr_airport",
        "flight_numbers", "segment_airports",
    ]
    print("\n  [데이터 품질 체크]")
    print(f"  {'필드':<20} {'null/빈 비율':>10}  {'샘플값'}")
    print(f"  {'-' * 65}")
    for f in fields:
        vals = [r.get(f) for r in all_results]
        if f in ("flight_numbers", "segment_airports"):
            null_cnt = sum(1 for v in vals if not v)  # 빈 리스트도 "null"
            sample = next((v for v in vals if v), "N/A")
        else:
            null_cnt = sum(1 for v in vals if v is None or v == "")
            sample = next((v for v in vals if v is not None and v != ""), "N/A")
        null_pct = null_cnt / len(vals) * 100
        flag = "⚠️ " if null_pct > 30 else "✅"
        print(f"  {flag} {f:<18} {null_pct:>8.1f}%   {sample}")


def print_booking_summary(all_results: list[dict], all_metas: list[dict]):
    """전체 booking URL 생성 요약"""
    total = len(all_results)
    if total == 0:
        return

    booking_ok = 0
    booking_urls = []
    for f, meta in zip(all_results, all_metas):
        url = _build_booking_url(f, meta["dep"], meta["arr"], meta["date"])
        if url:
            booking_ok += 1
            booking_urls.append((f, url))

    print(f"\n  [Booking URL 생성 요약]")
    print(f"  전체: {total}건 / booking URL 생성 성공: {booking_ok}건 "
          f"({booking_ok / total * 100:.1f}%)")

    if booking_ok == 0:
        print("\n  ⚠️  편명이 하나도 추출되지 않았습니다.")
        print("  → Google Flights DOM에서 편명이 축소된 카드에 포함되지 않을 수 있습니다.")
        print("  → 카드 확장(클릭) 후 편명 추출이 필요할 수 있습니다.")
    elif booking_ok < total:
        # 실패 원인 분석
        no_fn = sum(1 for f in all_results if not f.get("flight_numbers"))
        no_ap = sum(1 for f in all_results
                    if f.get("flight_numbers") and len(f["flight_numbers"]) > 1
                    and not f.get("segment_airports"))
        print(f"  실패 원인: 편명 미추출 {no_fn}건, 경유지 공항 부족 {no_ap}건")

    # 샘플 booking URL 출력
    if booking_urls:
        print(f"\n  [샘플 booking URL (처음 3개)]")
        for f, url in booking_urls[:3]:
            fn_str = ", ".join(f.get("flight_numbers", []))
            print(f"  • {f.get('airline', '?')} {fn_str}")
            print(f"    {url}")


# ─────────────────────────────────────────────
#  메인 실행
# ─────────────────────────────────────────────
async def run_and_verify():
    cases = TEST_CASES
    urls = [c["url"] for c in cases]

    config = make_run_config()
    all_flights: list[dict] = []
    all_metas: list[dict] = []

    print(f"\n{'=' * 60}")
    print(f"  Google Flights 편명 추출 + Booking URL 생성 검증")
    print(f"  테스트 URL: {len(urls)}개")
    print(f"  IATA 매핑 등록 항공사: {len(_AIRLINE_IATA)}개")
    print(f"{'=' * 60}\n")

    async with AsyncWebCrawler(config=make_browser_config()) as crawler:
        start = time.perf_counter()
        results = await crawler.arun_many(urls=urls, config=config)
        elapsed = time.perf_counter() - start

    print(f"⏱  크롤링 소요: {elapsed:.2f}s")
    print(f"{'=' * 60}")

    for result, meta in zip(results, cases):
        print(f"\n▶ {meta['label']}  ({meta['dep']}→{meta['arr']}  {meta['date']})")

        if not result.success:
            print(f"  ❌ 크롤링 실패: {result.error_message}")
            print(f"     status_code={result.status_code}")
            continue

        flights = _parse_flight_cards(result.html or "")
        print_flights(flights, meta["dep"], meta["arr"], meta["date"])

        for f in flights:
            all_flights.append(f)
            all_metas.append(meta)

    # ── 전체 요약 ──
    print(f"\n{'=' * 60}")
    print(f"  전체 추출 합계: {len(all_flights)}건")
    print_data_quality(all_flights)
    print_booking_summary(all_flights, all_metas)

    # ── JSON 덤프 ──
    dump_data = []
    for f, meta in zip(all_flights, all_metas):
        booking_url = _build_booking_url(f, meta["dep"], meta["arr"], meta["date"])
        dump_data.append({
            **f,
            "_meta_dep": meta["dep"],
            "_meta_arr": meta["arr"],
            "_meta_date": meta["date"],
            "_booking_url": booking_url,
            "_search_url": meta["url"],
        })

    with open("flight_extraction_dump.json", "w", encoding="utf-8") as fp:
        json.dump(dump_data, fp, ensure_ascii=False, indent=2)
    print(f"\n  💾 전체 결과 → flight_extraction_dump.json 저장 완료")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(run_and_verify())
