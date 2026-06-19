# flight_monitor/crawler_utils.py
#
# crawl4ai 기반 collector 공통 유틸.
# 배치 크롤 루프(arun_many) / 무한 스크롤 JS 등 Google Flights·Naver가 공유하는 패턴.
# crawl4ai 타입은 TYPE_CHECKING 하에서만 참조 — CI(crawl4ai 미설치)에서도 import 가능.

from __future__ import annotations

import asyncio
import calendar
import math
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig


def _add_months(base: date, months: int) -> date:
    """base가 속한 달의 1일 기준 months개월 뒤 달의 1일."""
    total = (base.year * 12 + (base.month - 1)) + months
    return date(total // 12, total % 12 + 1, 1)


def compute_sweep_window(
    today: date,
    now: datetime,
    range_months: int,
    tick_months: int,
    max_stay: int,
) -> tuple[date, date]:
    """이번 cron tick이 수집할 [start_date, end_date] 슬라이스를 stateless하게 계산.

    전체 range_months(예: 12)를 tick_months(예: 3) 단위 슬라이스로 나누고, 3시간 cron
    tick마다 근미래 슬라이스부터 round-robin으로 하나만 고른다. 한 run의 크롤 분량을
    1/num_slices로 줄여, 첫-run-of-day의 12개월 full-sweep이 cron 주기(3h)를 넘겨 죽고
    save_deals에 도달 못 해 데이터가 0건이 되던 death spiral을 끊는다.

    tick_index는 시각에서 유도(stateless) — 별도 커서 저장 없이 ephemeral collector
    컨테이너에서도 동작한다. tick_months >= range_months(또는 <=0)면 슬라이싱 비활성
    → 전체 범위(기존 동작). end_date는 마지막 출발일의 복귀편까지 담도록 max_stay만큼
    연장한다.
    """
    if tick_months <= 0 or tick_months >= range_months:
        slice_start_month = 0
        slice_len = range_months
    else:
        num_slices = math.ceil(range_months / tick_months)
        tick_index = (now.hour // 3) % num_slices
        slice_start_month = tick_index * tick_months
        slice_len = min(tick_months, range_months - slice_start_month)

    base = date(today.year, today.month, 1)
    start_date = max(today, _add_months(base, slice_start_month))

    last_month_first = _add_months(base, slice_start_month + slice_len - 1)
    _, last_day = calendar.monthrange(last_month_first.year, last_month_first.month)
    end_date = date(last_month_first.year, last_month_first.month, last_day) + timedelta(days=max_stay)
    return start_date, end_date


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


async def crawl_one_way_batches(
    crawler: "AsyncWebCrawler",
    urls: list[str],
    metas: list[dict],
    run_config: "CrawlerRunConfig",
    *,
    source_label: str,
    parse_cards: Callable[[str], list[dict]],
    request_delay: float,
    batch_size: int = 5,
) -> list[tuple[dict, list[dict]]]:
    """URL 목록을 batch_size 단위로 arun_many() 크롤링.

    개별 실패는 로깅 후 계속 진행한다 (AGENTS.md §4 — raise 금지).
    반환: 성공한 URL별 (meta, 가격 오름차순 정렬된 flights) 튜플 리스트.
    topk 절단·소스별 enrichment는 호출측 책임.
    """
    collected: list[tuple[dict, list[dict]]] = []

    for i in range(0, len(urls), batch_size):
        batch_urls = urls[i:i + batch_size]
        batch_metas = metas[i:i + batch_size]
        url_to_meta = {u: m for u, m in zip(batch_urls, batch_metas)}

        try:
            results = await crawler.arun_many(urls=batch_urls, config=run_config)
        except Exception as e:
            print(f"[{source_label} ERROR] batch {i // batch_size}: {e}")
            continue

        for result in results:
            meta = url_to_meta.get(result.url)
            if meta is None:
                print(f"[{source_label} WARN] 매칭 메타 없음: {result.url[:80]}")
                continue
            if not result.success:
                print(f"[{source_label} FAIL] {meta['dep']}-{meta['arr']} {meta['date']}: {result.error_message}")
                continue

            flights = parse_cards(result.html or "")
            if not flights:
                print(f"[{source_label} WARN] 카드 추출 0건 {meta['dep']}-{meta['arr']} {meta['date']}")
                continue

            flights.sort(key=lambda x: x["price"])
            collected.append((meta, flights))

        if i + batch_size < len(urls):
            await asyncio.sleep(request_delay)

    return collected
