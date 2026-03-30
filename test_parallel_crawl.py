"""
병렬 크롤링 동작 검증 스크립트.

기존 코드를 수정하지 않고, 새 병렬 로직만 독립적으로 실행해
실제 Google Flights 크롤링이 병렬로 잘 동작하는지 확인한다.

실행:
    python test_parallel_crawl.py
    python test_parallel_crawl.py --days 5 --parallel 2

옵션:
    --days N        수집할 날짜 범위 (오늘부터 N일, 기본 3)
    --parallel N    동시 실행 공항 수 (기본 3)
    --airports A B  특정 공항만 테스트 (예: TYO OSA)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date, timedelta

# 기존 인프라 초기화
from flight_monitor.config_db import apply_db_config
from flight_monitor.storage import init_db
from flight_monitor.config import JAPAN_AIRPORTS, SEARCH_CONFIG

apply_db_config()
init_db()

# crawl4ai 임포트 확인
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
except ImportError:
    print("[ERROR] crawl4ai 미설치. pip install crawl4ai 필요.")
    sys.exit(1)

# 기존 collector에서 필요한 함수들만 가져오기
from flight_monitor.collector_google_flights import (
    _fetch_route,
    _build_tfs_url,
)

# ──────────────────────────────────────────────────────────────────────
# 새 병렬 로직 (collector_google_flights.py에 반영 예정인 코드)
# ──────────────────────────────────────────────────────────────────────

def _make_browser_config() -> BrowserConfig:
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


async def _fetch_airport_parallel(
    airport_code: str,
    airport_name: str,
    today: date,
    end_date: date,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[dict], float]:
    """단일 공항 크롤링. 각 공항이 독립 AsyncWebCrawler를 사용."""
    t0 = time.perf_counter()
    async with semaphore:
        print(f"[{airport_code}] 시작 (세마포어 획득)")
        async with AsyncWebCrawler(config=_make_browser_config()) as crawler:
            offers = await _fetch_route(crawler, airport_code, airport_name, today, end_date)
        elapsed = time.perf_counter() - t0
        print(f"[{airport_code}] 완료: {len(offers)}건, {elapsed:.1f}s")
        return airport_code, offers, elapsed


async def run_parallel(airports: dict[str, str], today: date, end_date: date, parallel: int):
    """병렬 실행 (asyncio.gather + Semaphore)."""
    semaphore = asyncio.Semaphore(parallel)
    tasks = [
        _fetch_airport_parallel(code, name, today, end_date, semaphore)
        for code, name in airports.items()
    ]

    t_total = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_elapsed = time.perf_counter() - t_total

    total_offers = 0
    for r in results:
        if isinstance(r, BaseException):
            print(f"[ERROR] {r}")
        else:
            code, offers, _ = r
            total_offers += len(offers)

    print(f"\n[병렬 결과] 총 {total_offers}건, 소요 {total_elapsed:.1f}s (parallel={parallel})")
    return total_elapsed


# ──────────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3, help="수집 날짜 범위 (오늘 기준)")
    parser.add_argument("--parallel", type=int, default=3, help="동시 실행 공항 수")
    parser.add_argument("--airports", nargs="*", help="테스트할 공항 코드 (기본: 전체)")
    args = parser.parse_args()

    airports = dict(JAPAN_AIRPORTS)
    if args.airports:
        airports = {k: v for k, v in airports.items() if k in args.airports}

    if not airports:
        print(f"[ERROR] 공항 없음. DB에 airports 테이블 확인 필요.")
        sys.exit(1)

    today = date.today()
    end_date = today + timedelta(days=args.days)

    print(f"테스트 설정: 공항={list(airports.keys())}, 날짜={today}~{end_date} ({args.days}일), parallel={args.parallel}")
    print(f"예상 URL 수: {len(airports)} 공항 × {args.days}일 × 2방향 = {len(airports) * args.days * 2}개")
    print("-" * 60)

    asyncio.run(run_parallel(airports, today, end_date, args.parallel))


if __name__ == "__main__":
    main()
