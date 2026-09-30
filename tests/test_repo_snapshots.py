# tests/test_repo_snapshots.py

from datetime import UTC, date, datetime, timedelta

from flight_friend import repo
from flight_friend.types import LegQuote, Preferences, ProviderResult, RtQuote


def _make_trip(**overrides: object) -> int:
    defaults: dict[str, object] = {
        "destination": "FUK",
        "out_date": date(2026, 10, 1),
        "ret_date": date(2026, 10, 5),
        "prefs": Preferences(),
        "target_price": None,
    }
    defaults.update(overrides)
    return repo.create_trip(**defaults)  # type: ignore[arg-type]


def _leg(**overrides: object) -> LegQuote:
    defaults: dict[str, object] = {
        "flight_key": "TW123-2026-10-01",
        "airline_iata": "TW",
        "airline_name": "티웨이항공",
        "flight_numbers": ["TW123"],
        "dep_airport": "ICN",
        "arr_airport": "FUK",
        "dep_time": "09:00",
        "arr_time": "10:30",
        "duration_min": 90,
        "stops": 0,
        "price": 150_000,
        "booking_url": "https://example.com/book",
        "search_url": "https://example.com/search",
    }
    defaults.update(overrides)
    return LegQuote(**defaults)  # type: ignore[arg-type]


def test_save_and_load_snapshot_with_quotes():
    trip_id = _make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")

    leg1 = _leg(flight_key="TW123-2026-10-01", price=150_000)
    leg2 = _leg(
        flight_key="TW456-2026-10-01",
        flight_numbers=["TW456", "TW457"],
        price=160_000,
    )
    rt = RtQuote(airline_iata="TW", out_flight_key="TW123-2026-10-01", total_price=300_000)

    result = ProviderResult(
        status="ok",
        legs=[leg1, leg2],
        rts=[rt],
        error=None,
        seconds=1.23,
    )
    observed_at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

    snapshot_id = repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="google_flights",
        kind="oneway",
        direction="out",
        date_=date(2026, 10, 1),
        result=result,
        observed_at=observed_at,
    )
    assert isinstance(snapshot_id, int)

    snapshots = repo.load_snapshots(trip_id)
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.id == snapshot_id
    assert snap.run_id == run_id
    assert snap.trip_id == trip_id
    assert snap.provider == "google_flights"
    assert snap.kind == "oneway"
    assert snap.direction == "out"
    assert snap.date == date(2026, 10, 1)
    assert snap.status == "ok"
    assert snap.card_count == 3  # 2 legs + 1 rt
    assert snap.error is None

    assert len(snap.legs) == 2
    by_key = {leg.flight_key: leg for leg in snap.legs}
    assert by_key["TW123-2026-10-01"].price == 150_000
    assert by_key["TW123-2026-10-01"].flight_numbers == ["TW123"]
    assert by_key["TW456-2026-10-01"].flight_numbers == ["TW456", "TW457"]
    assert by_key["TW456-2026-10-01"].airline_name == "티웨이항공"
    assert by_key["TW456-2026-10-01"].booking_url == "https://example.com/book"

    assert len(snap.rts) == 1
    assert snap.rts[0].airline_iata == "TW"
    assert snap.rts[0].out_flight_key == "TW123-2026-10-01"
    assert snap.rts[0].total_price == 300_000


def test_load_snapshots_since_filter():
    trip_id = _make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")

    empty_result = ProviderResult(status="empty", legs=[], rts=[], error=None, seconds=0.5)

    old_at = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
    new_at = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)

    repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="amadeus",
        kind="oneway",
        direction="out",
        date_=date(2026, 10, 1),
        result=empty_result,
        observed_at=old_at,
    )
    repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="amadeus",
        kind="oneway",
        direction="out",
        date_=date(2026, 10, 1),
        result=empty_result,
        observed_at=new_at,
    )

    all_snapshots = repo.load_snapshots(trip_id)
    assert len(all_snapshots) == 2
    # ascending order by observed_at
    assert all_snapshots[0].observed_at <= all_snapshots[1].observed_at

    since = datetime(2026, 9, 25, 0, 0, tzinfo=UTC)
    filtered = repo.load_snapshots(trip_id, since=since)
    assert len(filtered) == 1
    assert filtered[0].observed_at == new_at


def test_load_snapshots_attaches_quotes_to_correct_snapshot():
    trip_id = _make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")

    leg_a = _leg(flight_key="TW-A", price=111_000)
    result_a = ProviderResult(
        status="ok",
        legs=[leg_a],
        rts=[RtQuote(airline_iata="TW", out_flight_key="TW-A", total_price=222_000)],
        error=None,
        seconds=1.0,
    )
    leg_b1 = _leg(flight_key="OZ-B1", airline_iata="OZ", price=133_000)
    leg_b2 = _leg(flight_key="OZ-B2", airline_iata="OZ", price=144_000)
    result_b = ProviderResult(status="ok", legs=[leg_b1, leg_b2], rts=[], error=None, seconds=1.0)
    result_c = ProviderResult(status="empty", legs=[], rts=[], error=None, seconds=1.0)

    id_a = repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="amadeus",
        kind="oneway",
        direction="out",
        date_=date(2026, 10, 1),
        result=result_a,
        observed_at=datetime(2026, 9, 26, 0, 0, tzinfo=UTC),
    )
    id_b = repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="naver",
        kind="oneway",
        direction="out",
        date_=date(2026, 10, 1),
        result=result_b,
        observed_at=datetime(2026, 9, 27, 0, 0, tzinfo=UTC),
    )
    id_c = repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="skyscanner",
        kind="oneway",
        direction="out",
        date_=date(2026, 10, 1),
        result=result_c,
        observed_at=datetime(2026, 9, 28, 0, 0, tzinfo=UTC),
    )

    snapshots = repo.load_snapshots(trip_id)
    assert [s.id for s in snapshots] == [id_a, id_b, id_c]

    by_id = {s.id: s for s in snapshots}

    assert [leg.flight_key for leg in by_id[id_a].legs] == ["TW-A"]
    assert [rt.out_flight_key for rt in by_id[id_a].rts] == ["TW-A"]

    assert [leg.flight_key for leg in by_id[id_b].legs] == ["OZ-B1", "OZ-B2"]
    assert by_id[id_b].rts == []

    assert by_id[id_c].legs == []
    assert by_id[id_c].rts == []


def test_error_snapshot_has_no_quotes():
    trip_id = _make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")

    result = ProviderResult(
        status="error",
        legs=[],
        rts=[],
        error="timeout",
        seconds=30.0,
    )
    snapshot_id = repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="skyscanner",
        kind="oneway",
        direction="in",
        date_=date(2026, 10, 5),
        result=result,
        observed_at=datetime.now(UTC),
    )

    snapshots = repo.load_snapshots(trip_id)
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.id == snapshot_id
    assert snap.status == "error"
    assert snap.error == "timeout"
    assert snap.card_count == 0
    assert snap.legs == []
    assert snap.rts == []


def test_last_alert_returns_latest():
    trip_id = _make_trip()

    assert repo.last_alert(trip_id, "target") is None

    repo.record_alert(trip_id, "target", 250_000)
    repo.record_alert(trip_id, "target", 230_000)

    latest = repo.last_alert(trip_id, "target")
    assert latest is not None
    price, sent_at = latest
    assert price == 230_000
    assert isinstance(sent_at, datetime)

    # different kind is independent
    assert repo.last_alert(trip_id, "new_low") is None

    # global ops alert (trip_id=None)
    repo.record_alert(None, "ops", None)
    ops_latest = repo.last_alert(None, "ops")
    assert ops_latest is not None
    assert ops_latest[0] is None

    # ops alert must not leak into trip-scoped lookup
    assert repo.last_alert(trip_id, "ops") is None


def test_provider_stats_counts_by_status():
    trip_id = _make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")

    ok_result = ProviderResult(status="ok", legs=[_leg()], rts=[], error=None, seconds=1.0)
    empty_result = ProviderResult(status="empty", legs=[], rts=[], error=None, seconds=1.0)
    blocked_result = ProviderResult(status="blocked", legs=[], rts=[], error="blocked", seconds=1.0)
    error_result = ProviderResult(status="error", legs=[], rts=[], error="boom", seconds=1.0)

    now = datetime.now(UTC)

    for result in (ok_result, ok_result, empty_result, blocked_result, error_result):
        repo.save_snapshot(
            run_id=run_id,
            trip_id=trip_id,
            provider="naver",
            kind="oneway",
            direction="out",
            date_=date(2026, 10, 1),
            result=result,
            observed_at=now,
        )

    # snapshot outside the days window should not be counted
    repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="naver",
        kind="oneway",
        direction="out",
        date_=date(2026, 10, 1),
        result=ok_result,
        observed_at=now - timedelta(days=30),
    )

    stats = repo.provider_stats(days=7)
    naver_rows = [row for row in stats if row["provider"] == "naver"]
    assert len(naver_rows) == 1
    row = naver_rows[0]
    assert row["total"] == 5
    assert row["ok"] == 2
    assert row["empty"] == 1
    assert row["blocked"] == 1
    assert row["error"] == 1


def test_recent_runs_includes_snapshot_summaries():
    trip_id = _make_trip(destination="OKA")
    run_id = repo.enqueue_run(trip_id, "manual")

    result = ProviderResult(status="ok", legs=[_leg()], rts=[], error=None, seconds=1.0)
    repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="google_flights",
        kind="oneway",
        direction="out",
        date_=date(2026, 10, 1),
        result=result,
        observed_at=datetime.now(UTC),
    )

    runs = repo.recent_runs(limit=3)
    assert len(runs) == 1
    row = runs[0]
    assert row["id"] == run_id
    assert row["trip_id"] == trip_id
    assert row["destination"] == "OKA"
    assert row["trigger"] == "manual"
    assert len(row["snapshots"]) == 1
    snap_row = row["snapshots"][0]
    assert snap_row["provider"] == "google_flights"
    assert snap_row["kind"] == "oneway"
    assert snap_row["direction"] == "out"
    assert snap_row["status"] == "ok"


def _save_one(leg: LegQuote, rt: RtQuote):
    trip_id = _make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")
    repo.save_snapshot(
        run_id=run_id,
        trip_id=trip_id,
        provider="naver",
        kind="oneway",
        direction="out",
        date_=date(2026, 10, 1),
        result=ProviderResult(status="ok", legs=[leg], rts=[rt], error=None, seconds=0.1),
        observed_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
    )
    snap = repo.load_snapshots(trip_id)[0]
    return snap.legs[0], snap.rts[0]


def test_cond_fields_roundtrip():
    label = "하나카드(이용실적 충족시)"
    leg = _leg(cond_price=161_700, cond_label=label, cond_booking_url="https://x")
    rt = RtQuote(
        airline_iata="TW",
        out_flight_key="TW123-2026-10-01",
        total_price=310_000,
        cond_total_price=299_000,
        cond_label=label,
    )
    got_leg, got_rt = _save_one(leg, rt)

    assert got_leg.cond_price == 161_700
    assert got_leg.cond_label == label
    assert got_leg.cond_booking_url == "https://x"
    assert got_rt.cond_total_price == 299_000
    assert got_rt.cond_label == label


def test_cond_fields_default_none():
    rt = RtQuote(airline_iata="TW", out_flight_key="TW123-2026-10-01", total_price=300_000)
    got_leg, got_rt = _save_one(_leg(), rt)

    assert got_leg.cond_price is None
    assert got_leg.cond_label is None
    assert got_leg.cond_booking_url is None
    assert got_rt.cond_total_price is None
    assert got_rt.cond_label is None
