#!/usr/bin/env python3
"""OCI 서버에서 실행 — Google Flights가 실제로 뭘 내려주는지 확인.

사용법:
  python scripts/diagnose_oci.py
"""

import asyncio
import time
from pathlib import Path

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# 실제 tfs URL 하나만 넣으세요
TEST_URL = (
    "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA0LTAxagcIARIDSUNOcgcIARIDRFBTQAFIAXABggELCP___________wGYAQI&hl=ko&curr=KRW"
)


def make_browser_config():
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


async def diagnose():
    print("=" * 60)
    print("  OCI 진단 스크립트")
    print("=" * 60)

    # ── 1단계: wait_for 없이 단순 fetch ──────────────────────
    print("\n[1단계] wait_for 없이 단순 fetch (timeout 원인 확인)")
    config_simple = CrawlerRunConfig(
        magic=True,
        wait_for=None,
        delay_before_return_html=5.0,
        cache_mode=CacheMode.BYPASS,
        page_timeout=20000,
    )

    t0 = time.perf_counter()
    async with AsyncWebCrawler(config=make_browser_config()) as crawler:
        result = await crawler.arun(url=TEST_URL, config=config_simple)
    elapsed = time.perf_counter() - t0

    print(f"  소요: {elapsed:.2f}s")
    print(f"  success: {result.success}")
    print(f"  status_code: {result.status_code}")
    html = result.html or ""
    print(f"  HTML 길이: {len(html)} bytes")

    Path("oci_raw_stage1.html").write_text(html, encoding="utf-8")
    print("  -> oci_raw_stage1.html 저장 완료")

    # CAPTCHA / 봇 탐지 징후 체크
    captcha_signals = [
        ("CAPTCHA", "captcha" in html.lower()),
        ("reCAPTCHA", "recaptcha" in html.lower()),
        ("unusual traffic", "unusual traffic" in html.lower()),
        ("항공편 카드 존재", "pIav2d" in html),
        ("flights 결과 텍스트", "항공편" in html or "flights" in html.lower()),
        ("빈 HTML (<1KB)", len(html) < 1000),
        ("리다이렉트 의심", "consent.google" in html or "accounts.google" in html),
    ]

    positive_labels = {"항공편 카드 존재", "flights 결과 텍스트"}
    print("\n  [봇 탐지 징후 체크]")
    for label, flag in captcha_signals:
        if label in positive_labels:
            icon = "OK" if flag else "X "
        else:
            icon = "!!" if flag else "OK"
        print(f"    {icon}  {label}: {flag}")

    # ── 2단계: wait_for 포함, 짧은 timeout ──────────────────
    print("\n[2단계] wait_for 포함, timeout=15s (실제 운영과 유사)")
    config_with_wait = CrawlerRunConfig(
        magic=True,
        wait_for="js:() => !!document.querySelector('li.pIav2d')",
        delay_before_return_html=4.0,
        cache_mode=CacheMode.BYPASS,
        page_timeout=15000,
    )

    t0 = time.perf_counter()
    async with AsyncWebCrawler(config=make_browser_config()) as crawler:
        result2 = await crawler.arun(url=TEST_URL, config=config_with_wait)
    elapsed2 = time.perf_counter() - t0

    print(f"  소요: {elapsed2:.2f}s")
    print(f"  success: {result2.success}")
    if not result2.success:
        print(f"  error: {result2.error_message}")

    html2 = result2.html or ""
    card_count = html2.count("pIav2d")
    print(f"  'pIav2d' 카드 발견: {card_count}개")

    Path("oci_raw_stage2.html").write_text(html2, encoding="utf-8")
    print("  -> oci_raw_stage2.html 저장 완료")

    # ── 3단계: 최종 진단 요약 ────────────────────────────────
    print("\n" + "=" * 60)
    print("  진단 요약")
    print("=" * 60)

    if elapsed > 30:
        print("  !! 1단계에서도 30s+ -> 네트워크 레이턴시 or Google 차단")
    elif elapsed < 15 and elapsed2 > 14:
        print("  !! fetch는 빠른데 wait_for에서 막힘 -> li.pIav2d 셀렉터 없음")
        print("     -> Google이 OCI IP에 다른 페이지 내려주는 중")
    elif card_count > 0:
        print("  OK 카드 정상 수신 — wait_for timeout 설정 문제일 수 있음")
    else:
        print("  !! 카드 0건 — IP 차단 또는 DOM 구조 변경 의심")

    print(f"\n  1단계(no wait_for): {elapsed:.1f}s")
    print(f"  2단계(with wait_for): {elapsed2:.1f}s")
    print(f"  차이: {elapsed2 - elapsed:.1f}s  <- 이게 크면 wait_for가 범인")

    print("\n  다음 단계:")
    print("  1. oci_raw_stage1.html 열어서 실제 페이지 내용 확인")
    print("  2. CAPTCHA 징후 있으면 -> IP 우회 or User-Agent 변경 필요")
    print("  3. 정상 페이지인데 카드 없으면 -> 셀렉터 변경 확인")


if __name__ == "__main__":
    asyncio.run(diagnose())
