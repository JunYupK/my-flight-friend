#!/usr/bin/env python3
# Google Flights 크롤 리소스 차단(text_mode) 효과 검증 벤치.
#
# 목적: 이미지/미디어를 끈 text_mode 가
#   (1) 카드 추출(가격 데이터)을 깨지 않는지 [correctness]
#   (2) 페이지 로드를 실제로 단축하는지 [speed]
# 를 "실제 OCI 환경 + 실제 IP"에서 같은 URL로 A/B 측정한다.
# 이 컨테이너(원격 dev)에서는 crawl4ai/Chromium/실 IP가 없어 의미가 없으므로
# 반드시 프로덕션 collector 컨테이너에서 실행할 것:
#
#   docker compose --profile collect run --rm collector \
#       python scripts/bench_gf_resource_block.py
#
# DB는 읽기만 한다 (TFS_TEMPLATES / JAPAN_AIRPORTS 로드용). 저장은 하지 않는다.

import asyncio
import sys
import time
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()
import flight_monitor.config  # noqa: F401 — sys.modules 선등록
from flight_monitor.config_db import apply_db_config

apply_db_config()

from flight_monitor.config import ORIGIN, JAPAN_AIRPORTS, SEARCH_CONFIG
from flight_monitor.collector_google_flights import (
    _build_tfs_url,
    _extract_js,
    _parse_flight_cards,
)
from flight_monitor.crawler_utils import make_scroll_js

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
except ImportError:
    print("crawl4ai 미설치 — collector 컨테이너에서 실행해야 합니다.")
    sys.exit(1)

# 측정 파라미터: GF를 과하게 때리지 않도록 소규모. 출발일은 근미래로.
N_DATES = 6
DAYS_AHEAD = 21
ROUNDS = 2  # baseline/text 를 교대로 ROUNDS회 반복 → 안티봇 throttle 드리프트 평균화


def pick_urls() -> tuple[str, list[str]]:
    """템플릿이 있는 첫 공항의 근미래 N_DATES개 out 방향 URL."""
    today = date.today()
    for code in JAPAN_AIRPORTS:
        urls = []
        for i in range(N_DATES):
            ds = (today + timedelta(days=DAYS_AHEAD + i)).strftime("%Y-%m-%d")
            u = _build_tfs_url(ORIGIN, code, ds)
            if u:
                urls.append(u)
        if urls:
            return code, urls
    return "", []


def _browser(text_mode: bool) -> "BrowserConfig":
    return BrowserConfig(
        headless=True,
        viewport={"width": 1920, "height": 1080},
        text_mode=text_mode,
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )


def _run_config() -> "CrawlerRunConfig":
    # 실제 collector 와 동일한 설정 (gf_page_timeout_ms 포함)
    return CrawlerRunConfig(
        magic=True,
        js_code=[make_scroll_js(), _extract_js()],
        wait_for="js:() => !!document.querySelector('li.pIav2d')",
        delay_before_return_html=4.0,
        cache_mode="bypass",
        page_timeout=SEARCH_CONFIG.get("gf_page_timeout_ms", 15000),
    )


async def crawl_once(text_mode: bool, urls: list[str]) -> tuple[float, int, int]:
    """반환: (소요초, 성공 URL 수, 추출 카드 합)."""
    t0 = time.monotonic()
    success = 0
    cards = 0
    async with AsyncWebCrawler(config=_browser(text_mode)) as crawler:
        results = await crawler.arun_many(urls=urls, config=_run_config())
        for r in results:
            if not getattr(r, "success", False):
                continue
            success += 1
            cards += len(_parse_flight_cards(r.html or ""))
    return time.monotonic() - t0, success, cards


async def main() -> None:
    code, urls = pick_urls()
    if not urls:
        print("유효한 GF URL 없음 — DB의 TFS_TEMPLATES / airports 확인 필요.")
        return

    print(
        f"대상: {ORIGIN}->{code} out {len(urls)}개 날짜 | "
        f"page_timeout={SEARCH_CONFIG.get('gf_page_timeout_ms', 15000)}ms | "
        f"rounds={ROUNDS}\n"
    )

    agg = {"baseline": [0.0, 0, 0], "text_mode": [0.0, 0, 0]}
    for rnd in range(1, ROUNDS + 1):
        for label, text_mode in [("baseline", False), ("text_mode", True)]:
            dt, ok, cards = await crawl_once(text_mode, urls)
            agg[label][0] += dt
            agg[label][1] += ok
            agg[label][2] += cards
            print(
                f"[round {rnd}] {label:9s}: {dt:6.1f}s "
                f"({dt / len(urls):4.1f}s/url) | 성공 {ok}/{len(urls)} | 카드 {cards}"
            )
            await asyncio.sleep(5)  # 라운드 간 간격 (안티봇 완화)

    b_dt, b_ok, b_cards = agg["baseline"]
    t_dt, t_ok, t_cards = agg["text_mode"]
    print("\n=== 합계 (ROUNDS 누적) ===")
    print(f"baseline : {b_dt:6.1f}s | 성공 {b_ok} | 카드 {b_cards}")
    print(f"text_mode: {t_dt:6.1f}s | 성공 {t_ok} | 카드 {t_cards}")

    if b_dt > 0:
        if t_dt < b_dt:
            print(f"속도   : {(1 - t_dt / b_dt) * 100:4.0f}% 단축")
        else:
            print(f"속도   : {(t_dt / b_dt - 1) * 100:4.0f}% 악화 (text_mode 비채택)")
    # 카드 80% 이상 보존되면 correctness OK 로 간주
    if b_cards == 0:
        print("판정   : baseline 카드 0건 — GF 차단/IP 문제. 측정 무효, 재시도 필요.")
    elif t_cards >= b_cards * 0.8:
        print(f"correctness: OK (카드 {b_cards}→{t_cards}, 보존율 {t_cards / b_cards * 100:.0f}%)")
    else:
        print(f"correctness: 경고 — 추출 손실 (카드 {b_cards}→{t_cards}). text_mode 비채택 권장.")


if __name__ == "__main__":
    asyncio.run(main())
