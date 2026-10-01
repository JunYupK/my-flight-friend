# flight_friend/worker.py
"""검색 워커: queued run을 claim → Google Flights·Naver 검색 → 스냅샷 저장 → 자동 갱신 스케줄 · 알림."""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import partial
from typing import Literal

from flight_friend import db, repo
from flight_friend.config import ORIGIN, RUN_TIMEOUT, STUCK_RUN_AFTER
from flight_friend.domain.results import (
    MergedLeg,
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
from flight_friend.notifier import send_alert
from flight_friend.providers import google_flights, naver
from flight_friend.types import ProviderResult, Run, Trip

logger = logging.getLogger(__name__)

OPS_COOLDOWN = timedelta(hours=6)
PROVIDER_LABELS = {"google_flights": "Google Flights", "naver": "Naver"}

Sender = Callable[[str], str | None]
AlertKind = Literal["new_low", "target"]


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    oneway: Callable[[str, str, date], Awaitable[ProviderResult]]
    roundtrip: Callable[[str, str, date, date], Awaitable[ProviderResult]]


async def _guarded(name: str, factory: Callable[[], Awaitable[ProviderResult]]) -> ProviderResult:
    try:
        return await factory()
    except Exception as e:
        logger.exception("provider %s failed", name)
        return ProviderResult(status="error", legs=[], rts=[], error=str(e), seconds=0.0)


async def _execute(run: Run, trip: Trip, providers: list[ProviderSpec], timeout: float | None) -> bool:
    """제공자 호출을 각각 태스크로 돌리고 각 호출이 끝나는 즉시 그 스냅샷을 저장한다. google_flights 호출이 시간 초과되면 True.

    어떤 제공자든 시간 초과면 run은 error로 닫지만, 브라우저 재생성 신호(True)는 GF 시간 초과만 낸다."""
    gf_timed_out = False
    timed_out = False
    try:
        if repo.get_trip(trip.id) is None:
            raise LookupError(f"trip {trip.id} not found")
        plan: list[tuple[str, Literal["oneway", "roundtrip"], Literal["out", "in"] | None, date]] = []
        saved: set[int] = set()

        async def call_and_save(index: int, factory: Callable[[], Awaitable[ProviderResult]]) -> None:
            name, kind, direction, day = plan[index]
            result = await _guarded(name, factory)
            repo.save_snapshot(run.id, trip.id, name, kind, direction, day, result, datetime.now(UTC))
            saved.add(index)

        tasks: list[asyncio.Task[None]] = []
        for spec in providers:
            plan += [
                (spec.name, "oneway", "out", trip.out_date),
                (spec.name, "oneway", "in", trip.ret_date),
                (spec.name, "roundtrip", None, trip.out_date),
            ]
            factories: list[Callable[[], Awaitable[ProviderResult]]] = [
                partial(spec.oneway, ORIGIN, trip.destination, trip.out_date),
                partial(spec.oneway, trip.destination, ORIGIN, trip.ret_date),
                partial(spec.roundtrip, ORIGIN, trip.destination, trip.out_date, trip.ret_date),
            ]
            for f in factories:
                tasks.append(asyncio.ensure_future(call_and_save(len(tasks), f)))
        started = time.monotonic()
        _, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in tasks:
            if task not in pending and (error := task.exception()) is not None:
                raise error  # 저장 실패 등: 바깥 except에서 run을 error로 닫는다
        elapsed = time.monotonic() - started
        timed_out = bool(pending)
        observed_at = datetime.now(UTC)
        for index, (name, kind, direction, day) in enumerate(plan):
            if index in saved:
                continue
            logger.error("run %s: provider %s %s timed out", run.id, name, kind)
            gf_timed_out = gf_timed_out or name == "google_flights"
            result = ProviderResult(status="error", legs=[], rts=[], error="timeout", seconds=elapsed)
            repo.save_snapshot(run.id, trip.id, name, kind, direction, day, result, observed_at)
    except Exception:
        logger.exception("run %s failed", run.id)
        repo.finish_run(run.id, "error")
        return gf_timed_out
    repo.finish_run(run.id, "error" if timed_out else "done")
    return gf_timed_out


async def execute_run(run: Run, trip: Trip, providers: list[ProviderSpec]) -> None:
    await _execute(run, trip, providers, None)


async def run_with_timeout(
    run: Run, trip: Trip, providers: list[ProviderSpec], timeout: timedelta = RUN_TIMEOUT
) -> bool:
    """execute_run에 시간 상한을 둔다. 시간 초과면 끝난 결과는 저장하고 run을 error로 닫는다. google_flights가 시간 초과됐을 때만 True."""
    return await _execute(run, trip, providers, timeout.total_seconds())


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


def _alert_url(merged: MergedLeg) -> str | None:
    """알림 링크는 최저가 제공자의 예약 링크 (웹 SelectionBar.cheapestUrl 과 같은 선택)."""
    for p in merged.prices:
        if not p.stale and p.provider == merged.best_provider and p.booking_url:
            return p.booking_url
    return merged.leg.booking_url


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
    conds = [m.best_cond for m in (out_leg, in_leg) if m.best_cond is not None]
    if conds:
        total = sum(
            min(m.best_cond.price, m.best_price) if m.best_cond else m.best_price
            for m in (out_leg, in_leg)
            if m.best_price is not None
        )
        extras.append(f"카드 조건 시 {total:,}원 ({conds[0].label} 등)")
    for label, merged in (("가는편", out_leg), ("오는편", in_leg)):
        url = _alert_url(merged)
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


def _provider_failing(name: str, runs: list[dict]) -> bool:
    for run in runs:
        oneways = [s for s in run["snapshots"] if s["kind"] == "oneway" and s["provider"] == name]
        if any(s["status"] == "ok" for s in oneways):
            return False
        if not oneways and run["status"] != "error":
            return False
    return True


def evaluate_ops(
    now: datetime, send: Sender = send_alert, providers: tuple[str, ...] = ("google_flights", "naver")
) -> list[str]:
    finished = [r for r in repo.recent_runs(limit=30) if r["status"] in ("done", "error")]
    runs = finished[:3]
    if len(runs) < 3:
        return []
    alerted: list[str] = []
    for name in providers:
        if not _provider_failing(name, runs):
            continue
        kind = f"ops:{name}"
        last = repo.last_alert(None, kind)
        if last is not None and now - last[1] < OPS_COOLDOWN:
            continue
        if send(f"[Flight Friend] {PROVIDER_LABELS[name]} 최근 3회 검색 연속 실패 — /admin 확인") is None:
            continue
        repo.record_alert(None, kind, None)
        alerted.append(name)
    return alerted


async def main_loop() -> None:
    db.init_schema()
    import httpx
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
    client = httpx.AsyncClient()
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
                        providers = [
                            ProviderSpec(
                                "google_flights",
                                partial(google_flights.search_oneway, crawler),
                                partial(google_flights.search_roundtrip, crawler),
                            ),
                            ProviderSpec(
                                "naver",
                                partial(naver.search_oneway, client),
                                partial(naver.search_roundtrip, client),
                            ),
                        ]
                        if await run_with_timeout(run, trip, providers):
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
        try:
            await crawler.close()
        finally:
            await client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_loop())
