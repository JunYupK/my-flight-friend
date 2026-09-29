# tests/v2/test_worker.py

import asyncio
import os
import sys
from datetime import UTC, date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flight_friend import repo
from flight_friend.providers.google_flights import Crawler, CrawlResult
from flight_friend.types import LegQuote, Preferences, ProviderResult, Run, Trip
from flight_friend.worker import (
    OnewaySearch,
    RoundtripSearch,
    evaluate_alerts,
    evaluate_ops,
    execute_run,
    schedule_due_trips,
)

NOW = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)
OUT = date(2026, 12, 20)
RET = date(2026, 12, 23)


class FakeCrawler:
    async def arun(self, *, url: str, config: object) -> CrawlResult:
        raise AssertionError("fake search functions must not touch the crawler")


def leg(key: str, price: int) -> LegQuote:
    return LegQuote(
        flight_key=key,
        airline_iata="KE",
        airline_name="KE",
        flight_numbers=[key],
        dep_airport="ICN",
        arr_airport="FUK",
        dep_time="08:00",
        arr_time="10:00",
        duration_min=120,
        stops=0,
        price=price,
        booking_url=None,
        search_url=None,
    )


def ok(price: int) -> ProviderResult:
    return ProviderResult(status="ok", legs=[leg(f"k{price}", price)], rts=[], error=None, seconds=0.1)


def failed() -> ProviderResult:
    return ProviderResult(status="error", legs=[], rts=[], error="boom", seconds=0.1)


def make_trip(target: int | None = None, out: date = OUT) -> Trip:
    trip_id = repo.create_trip("FUK", out, RET, Preferences(), target)
    trip = repo.get_trip(trip_id)
    assert trip is not None
    return trip


def claim(trip: Trip) -> Run:
    repo.enqueue_run(trip.id, "schedule")
    run = repo.claim_next_run()
    assert run is not None
    return run


def fake_searches(
    calls: list[tuple[str, str, str]], in_result: ProviderResult | None = None
) -> tuple[OnewaySearch, RoundtripSearch]:
    async def oneway(crawler: Crawler, dep: str, arr: str, date_: date) -> ProviderResult:
        calls.append((dep, arr, date_.isoformat()))
        if dep != "ICN" and in_result is not None:
            return in_result
        return ok(100_000)

    async def roundtrip(crawler: Crawler, dep: str, arr: str, out_date: date, ret_date: date) -> ProviderResult:
        calls.append((dep, arr, f"{out_date.isoformat()}~{ret_date.isoformat()}"))
        return ok(250_000)

    return oneway, roundtrip


def run_execute(run: Run, trip: Trip, in_result: ProviderResult | None = None) -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []
    oneway, roundtrip = fake_searches(calls, in_result)
    asyncio.run(execute_run(run, trip, FakeCrawler(), oneway, roundtrip))
    return calls


def test_execute_run_saves_three_snapshots() -> None:
    trip = make_trip()
    run = claim(trip)
    calls = run_execute(run, trip)
    assert sorted(calls) == sorted(
        [("ICN", "FUK", "2026-12-20"), ("FUK", "ICN", "2026-12-23"), ("ICN", "FUK", "2026-12-20~2026-12-23")]
    )
    snaps = repo.load_snapshots(trip.id)
    assert sorted((s.kind, s.direction, s.date) for s in snaps if s.kind == "oneway") == [
        ("oneway", "in", RET),
        ("oneway", "out", OUT),
    ]
    assert [(s.kind, s.direction, s.date) for s in snaps if s.kind == "roundtrip"] == [("roundtrip", None, OUT)]
    assert len({s.observed_at for s in snaps}) == 1
    finished = repo.get_run(run.id)
    assert finished is not None and finished.status == "done"


def test_execute_run_partial_failure_still_done() -> None:
    trip = make_trip()
    run = claim(trip)
    run_execute(run, trip, in_result=failed())
    snaps = repo.load_snapshots(trip.id)
    by_dir = {s.direction: s.status for s in snaps if s.kind == "oneway"}
    assert by_dir == {"out": "ok", "in": "error"}
    finished = repo.get_run(run.id)
    assert finished is not None and finished.status == "done"


def test_execute_run_exception_marks_error() -> None:
    trip = make_trip()
    run = claim(trip)

    async def boom(crawler: Crawler, dep: str, arr: str, date_: date) -> ProviderResult:
        raise RuntimeError("crawler died")

    _, roundtrip = fake_searches([])
    asyncio.run(execute_run(run, trip, FakeCrawler(), boom, roundtrip))
    finished = repo.get_run(run.id)
    assert finished is not None and finished.status == "error"
    assert repo.load_snapshots(trip.id) == []


def test_execute_run_missing_trip_marks_error() -> None:
    trip = make_trip()
    run = claim(trip)
    ghost = Trip(**{**trip.__dict__, "id": 9999})
    run_execute(run, ghost)
    finished = repo.get_run(run.id)
    assert finished is not None and finished.status == "error"


def test_schedule_due_trips_skips_open_run_and_off_tracking() -> None:
    due = make_trip()
    open_run = make_trip()
    off = make_trip()
    repo.update_trip(off.id, tracking=False)
    repo.enqueue_run(open_run.id, "manual")
    assert schedule_due_trips(datetime.now(UTC)) == 1
    assert repo.has_open_run(due.id)
    latest = repo.latest_run(due.id)
    assert latest is not None and latest.trigger == "schedule"
    assert repo.latest_run(off.id) is None
    assert schedule_due_trips(datetime.now(UTC)) == 0


def seed_day(trip: Trip, days_ago: int, out: int, inn: int) -> None:
    at = NOW - timedelta(days=days_ago, hours=1)
    run = claim(trip)
    repo.save_snapshot(run.id, trip.id, "google_flights", "oneway", "out", trip.out_date, ok(out), at)
    repo.save_snapshot(run.id, trip.id, "google_flights", "oneway", "in", trip.ret_date, ok(inn), at)
    repo.finish_run(run.id, "done")


def test_evaluate_alerts_sends_once() -> None:
    trip = make_trip(target=280_000)
    seed_day(trip, 3, 150_000, 150_000)
    seed_day(trip, 2, 150_000, 150_000)
    seed_day(trip, 1, 150_000, 150_000)
    seed_day(trip, 0, 130_000, 120_000)
    sent: list[str] = []

    def send(message: str) -> str | None:
        sent.append(message)
        return "telegram"

    assert sorted(evaluate_alerts(trip, NOW, send)) == ["new_low", "target"]
    assert len(sent) == 2
    low = next(m for m in sent if "최저" in m)
    assert low == (
        f"[Flight Friend] FUK 12/20→12/23 · 추적 시작 이후 최저 250,000원 (-17%) /trips/{trip.id}"
    )
    target = next(m for m in sent if "목표가" in m)
    assert target == f"[Flight Friend] FUK 12/20→12/23 · 목표가 280,000원 이하 진입 250,000원 /trips/{trip.id}"
    assert evaluate_alerts(trip, NOW, send) == []
    assert len(sent) == 2


def test_evaluate_alerts_not_recorded_when_send_fails() -> None:
    trip = make_trip()
    for d in (3, 2, 1):
        seed_day(trip, d, 150_000, 150_000)
    seed_day(trip, 0, 130_000, 120_000)
    assert evaluate_alerts(trip, NOW, lambda m: None) == []
    assert repo.last_alert(trip.id, "new_low") is None


def seed_ops_run(trip: Trip, status: str) -> None:
    run = claim(trip)
    at = datetime.now(UTC)
    result = ok(100_000) if status == "ok" else failed()
    repo.save_snapshot(run.id, trip.id, "google_flights", "oneway", "out", trip.out_date, result, at)
    repo.save_snapshot(run.id, trip.id, "google_flights", "oneway", "in", trip.ret_date, result, at)
    repo.finish_run(run.id, "done")


def test_evaluate_ops_after_three_failures() -> None:
    trip = make_trip()
    sent: list[str] = []

    def send(message: str) -> str | None:
        sent.append(message)
        return "telegram"

    seed_ops_run(trip, "error")
    seed_ops_run(trip, "error")
    assert evaluate_ops(NOW, send) is False
    seed_ops_run(trip, "error")
    assert evaluate_ops(NOW, send) is True
    assert sent == ["[Flight Friend] Google Flights 최근 3회 검색 연속 실패 — /admin 확인"]
    assert evaluate_ops(NOW, send) is False
    assert len(sent) == 1


def test_evaluate_ops_not_triggered_when_a_run_succeeded() -> None:
    trip = make_trip()
    for status in ("error", "ok", "error"):
        seed_ops_run(trip, status)
    assert evaluate_ops(NOW, lambda m: "telegram") is False
