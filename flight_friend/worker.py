# flight_friend/worker.py
"""검색 워커: queued run을 claim → Google Flights 검색 → 스냅샷 저장 → 자동 갱신 스케줄 · 알림."""

import asyncio
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Literal, Protocol

from flight_friend import db, repo
from flight_friend.config import ORIGIN, RUN_TIMEOUT, STUCK_RUN_AFTER
from flight_friend.domain.results import (
    cheapest_combo,
    current_legs,
    in_condition,
    stay_minutes,
)
from flight_friend.domain.schedule import days_to_departure, freshness_window, is_due
from flight_friend.domain.tracking import (
    KST,
    daily_series,
    run_values,
    should_alert_new_low,
    should_alert_target,
)
from flight_friend.providers import google_flights
from flight_friend.providers.google_flights import Crawler
from flight_friend.types import ProviderResult, Run, Trip
from flight_monitor.notifier import send_alert

logger = logging.getLogger(__name__)

PROVIDER = "google_flights"
OPS_COOLDOWN = timedelta(hours=6)
OPS_MESSAGE = "[Flight Friend] Google Flights 최근 3회 검색 연속 실패 — /admin 확인"

Sender = Callable[[str], str | None]
AlertKind = Literal["new_low", "target"]


class OnewaySearch(Protocol):
    async def __call__(self, crawler: Crawler, dep: str, arr: str, date_: date) -> ProviderResult: ...


class RoundtripSearch(Protocol):
    async def __call__(
        self, crawler: Crawler, dep: str, arr: str, out_date: date, ret_date: date
    ) -> ProviderResult: ...


async def execute_run(
    run: Run,
    trip: Trip,
    crawler: Crawler,
    search_oneway: OnewaySearch = google_flights.search_oneway,
    search_roundtrip: RoundtripSearch = google_flights.search_roundtrip,
) -> None:
    try:
        if repo.get_trip(trip.id) is None:
            raise LookupError(f"trip {trip.id} not found")
        out, inn, rt = await asyncio.gather(
            search_oneway(crawler, ORIGIN, trip.destination, trip.out_date),
            search_oneway(crawler, trip.destination, ORIGIN, trip.ret_date),
            search_roundtrip(crawler, ORIGIN, trip.destination, trip.out_date, trip.ret_date),
        )
        observed_at = datetime.now(UTC)
        repo.save_snapshot(run.id, trip.id, PROVIDER, "oneway", "out", trip.out_date, out, observed_at)
        repo.save_snapshot(run.id, trip.id, PROVIDER, "oneway", "in", trip.ret_date, inn, observed_at)
        repo.save_snapshot(run.id, trip.id, PROVIDER, "roundtrip", None, trip.out_date, rt, observed_at)
    except Exception:
        logger.exception("run %s failed", run.id)
        repo.finish_run(run.id, "error")
        return
    repo.finish_run(run.id, "done")


async def run_with_timeout(
    run: Run,
    trip: Trip,
    crawler: Crawler,
    timeout: timedelta = RUN_TIMEOUT,
    search_oneway: OnewaySearch = google_flights.search_oneway,
    search_roundtrip: RoundtripSearch = google_flights.search_roundtrip,
) -> bool:
    """execute_run에 시간 상한을 둔다. 시간 초과면 run을 error로 닫고 True를 반환한다."""
    try:
        await asyncio.wait_for(
            execute_run(run, trip, crawler, search_oneway, search_roundtrip),
            timeout=timeout.total_seconds(),
        )
    except TimeoutError:
        logger.error("run %s timed out after %s", run.id, timeout)
        repo.finish_run(run.id, "error")
        return True
    return False


def schedule_due_trips(now: datetime) -> int:
    count = 0
    for trip in repo.list_trips():
        last = repo.latest_run(trip.id)
        if is_due(trip, last.requested_at if last else None, now) and not repo.has_open_run(trip.id):
            repo.enqueue_run(trip.id, "schedule")
            count += 1
    return count


def _trip_url(trip_id: int) -> str:
    path = f"/trips/{trip_id}"
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        domain = os.environ.get("DOMAIN", "").strip()
        if domain and not domain.startswith("localhost"):
            base = f"https://{domain}"
    return f"{base}{path}"


def _stay_text(minutes: int) -> str:
    return f"{minutes // 60}시간 {minutes % 60}분"


def evaluate_alerts(trip: Trip, now: datetime, send: Sender = send_alert) -> list[AlertKind]:
    today = now.astimezone(KST).date()
    if not trip.tracking or trip.archived_at is not None or trip.out_date < today:
        return []
    window = freshness_window(days_to_departure(trip.out_date, today))
    snaps = repo.load_snapshots(trip.id)
    best = cheapest_combo(in_condition(current_legs(snaps, now, window), trip.prefs), trip.prefs.max_price)
    if best is None:
        return []
    out_leg, in_leg, current = best
    series = daily_series(run_values(snaps, trip.prefs))
    head = f"[Flight Friend] {trip.destination} {trip.out_date:%m/%d}→{trip.ret_date:%m/%d}"
    extras = [f"현지 체류 {_stay_text(stay_minutes(out_leg.leg, trip.out_date, in_leg.leg, trip.ret_date))}"]
    for label, merged in (("가는편", out_leg), ("오는편", in_leg)):
        url = merged.leg.booking_url
        if url:
            extras.append(f"{label} {url}")
    tail = " · ".join([_trip_url(trip.id), *extras])

    last_low = repo.last_alert(trip.id, "new_low")
    last_target = repo.last_alert(trip.id, "target")
    candidates: list[tuple[AlertKind, str]] = []

    if should_alert_new_low(series, current, last_low[0] if last_low else None):
        previous = [p.combo for p in series[:-1] if p.combo is not None]
        pct = current / min(previous) - 1
        candidates.append(("new_low", f"{head} · 추적 시작 이후 최저 {current:,}원 ({pct:+.0%}) {tail}"))
    if trip.target_price is not None and should_alert_target(
        current, trip.target_price, last_target[0] if last_target else None
    ):
        candidates.append(
            ("target", f"{head} · 목표가 {trip.target_price:,}원 이하 진입 {current:,}원 {tail}")
        )

    sent: list[AlertKind] = []
    for kind, message in candidates:
        if send(message) is not None:
            repo.record_alert(trip.id, kind, current)
            sent.append(kind)
    return sent


def evaluate_ops(now: datetime, send: Sender = send_alert) -> bool:
    finished = [r for r in repo.recent_runs(limit=30) if r["status"] in ("done", "error")]
    runs = finished[:3]
    if len(runs) < 3:
        return False
    for run in runs:
        oneways = [s for s in run["snapshots"] if s["kind"] == "oneway" and s["provider"] == PROVIDER]
        if any(s["status"] == "ok" for s in oneways):
            return False
        if not oneways and run["status"] != "error":
            return False
    last = repo.last_alert(None, "ops")
    if last is not None and now - last[1] < OPS_COOLDOWN:
        return False
    if send(OPS_MESSAGE) is None:
        return False
    repo.record_alert(None, "ops", None)
    return True


async def main_loop() -> None:
    db.init_schema()
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    config = BrowserConfig(
        headless=True,
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )

    async def open_crawler() -> AsyncWebCrawler:
        opened = AsyncWebCrawler(config=config)
        await opened.start()
        return opened

    last_maintenance = 0.0
    crawler = await open_crawler()
    try:
        while True:
            try:
                if time.monotonic() - last_maintenance >= 60:
                    last_maintenance = time.monotonic()
                    repo.expire_stuck_runs(STUCK_RUN_AFTER)
                    schedule_due_trips(datetime.now(UTC))
                    evaluate_ops(datetime.now(UTC))
                run = repo.claim_next_run()
                if run is not None:
                    trip = repo.get_trip(run.trip_id)
                    if trip is not None:
                        if await run_with_timeout(run, trip, crawler):
                            # 멈춘 브라우저를 버리고 새로 연다 (닫기는 best-effort).
                            try:
                                await crawler.close()
                            except Exception:
                                logger.exception("closing stuck crawler failed")
                            crawler = await open_crawler()
                        trip = repo.get_trip(run.trip_id)
                        if trip is not None:
                            evaluate_alerts(trip, datetime.now(UTC))
                    else:
                        repo.finish_run(run.id, "error")
                    continue
            except Exception:
                logger.exception("worker iteration failed")
            await asyncio.sleep(2)
    finally:
        await crawler.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_loop())
