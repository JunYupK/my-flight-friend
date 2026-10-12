# tests/test_history.py — 수집별 요약 캐시와 "현재 상태용" 스냅샷 로딩

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from flight_friend import db, history, repo
from flight_friend.domain.results import current_legs, rt_reference
from flight_friend.domain.tracking import run_values
from flight_friend.types import LegQuote, Preferences, ProviderResult, RtQuote

NOW = datetime(2026, 10, 12, 3, 0, tzinfo=UTC)
OUT = date(2026, 12, 1)
RET = date(2026, 12, 4)


def _leg(key: str, price: int, dep: str = "08:00", stops: int = 0) -> LegQuote:
    return LegQuote(
        flight_key=key, airline_iata="KE", airline_name="KE", flight_numbers=[key], dep_airport="ICN",
        arr_airport="NRT", dep_time=dep, arr_time="10:00", duration_min=120, stops=stops, price=price,
        booking_url=None, search_url=None,
    )


def _run(trip_id: int, at: datetime, base: int, finish: bool = True, providers: tuple[str, ...] = ("google_flights", "naver")) -> int:
    run_id = repo.enqueue_run(trip_id, "schedule")
    for p in providers:
        for direction, d in (("out", OUT), ("in", RET)):
            legs = [_leg(f"{direction}A", base), _leg(f"{direction}B", base - 5000, dep="05:00", stops=1)]
            repo.save_snapshot(run_id, trip_id, p, "oneway", direction, d, ProviderResult("ok", legs, [], None, 1.0), at)
        rts = [RtQuote("KE", "outA", base * 2 - 1000)]
        repo.save_snapshot(run_id, trip_id, p, "roundtrip", None, OUT, ProviderResult("ok", [], rts, None, 1.0), at)
    if finish:
        repo.finish_run(run_id, "done")
    return run_id


def _summary_count(trip_id: int) -> int:
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM run_summaries WHERE trip_id = %s", (trip_id,))
        return cur.fetchone()[0]


def test_run_values_match_full_computation_and_are_cached():
    trip_id = repo.create_trip("NRT", OUT, RET, Preferences())
    for i in range(4):
        _run(trip_id, NOW - timedelta(hours=6 * (4 - i)), 200_000 + i * 3000)
    trip = repo.get_trip(trip_id)
    assert trip is not None
    expected = run_values(repo.load_snapshots(trip_id), trip.prefs)
    assert history.run_values_for(trip) == expected
    assert _summary_count(trip_id) == 4
    assert history.run_values_for(trip) == expected  # 두 번째는 캐시에서


def test_prefs_change_recomputes_summaries():
    trip_id = repo.create_trip("NRT", OUT, RET, Preferences())
    _run(trip_id, NOW - timedelta(hours=3), 200_000)
    trip = repo.get_trip(trip_id)
    assert trip is not None
    before = history.run_values_for(trip)
    repo.update_trip(trip_id, prefs=Preferences(nonstop_only=True))
    trip = repo.get_trip(trip_id)
    assert trip is not None
    after = history.run_values_for(trip)
    assert after == run_values(repo.load_snapshots(trip_id), trip.prefs)
    assert after[0].combo != before[0].combo  # 직항만 → 경유편(더 쌈) 제외


def test_open_run_is_computed_live_and_not_cached():
    trip_id = repo.create_trip("NRT", OUT, RET, Preferences())
    _run(trip_id, NOW - timedelta(hours=3), 200_000)
    _run(trip_id, NOW - timedelta(minutes=5), 190_000, finish=False, providers=("google_flights",))
    trip = repo.get_trip(trip_id)
    assert trip is not None
    assert history.run_values_for(trip) == run_values(repo.load_snapshots(trip_id), trip.prefs)
    assert _summary_count(trip_id) == 1


def test_snapshot_added_after_summary_recomputes():
    trip_id = repo.create_trip("NRT", OUT, RET, Preferences())
    run_id = _run(trip_id, NOW - timedelta(hours=3), 200_000, providers=("google_flights",))
    trip = repo.get_trip(trip_id)
    assert trip is not None
    history.run_values_for(trip)
    late = [_leg("outC", 100_000)]
    repo.save_snapshot(run_id, trip_id, "naver", "oneway", "out", OUT, ProviderResult("ok", late, [], None, 1.0), NOW - timedelta(hours=2))
    assert history.run_values_for(trip) == run_values(repo.load_snapshots(trip_id), trip.prefs)


def test_current_snapshots_give_same_current_state():
    trip_id = repo.create_trip("NRT", OUT, RET, Preferences())
    for i in range(3):
        _run(trip_id, NOW - timedelta(hours=6 * (3 - i)), 200_000 + i * 3000)
    full = repo.load_snapshots(trip_id)
    current = history.current_snapshots([trip_id])[trip_id]
    window = timedelta(hours=12)
    assert [replace(s, legs=[], rts=[]) for s in current] == [replace(s, legs=[], rts=[]) for s in full]
    assert sum(len(s.legs) + len(s.rts) for s in current) < sum(len(s.legs) + len(s.rts) for s in full)
    legs_full = current_legs(full, NOW, window)
    assert current_legs(current, NOW, window) == legs_full
    assert rt_reference(current, legs_full, NOW, window) == rt_reference(full, legs_full, NOW, window)


def test_batched_run_values_match_per_trip():
    a = repo.create_trip("NRT", OUT, RET, Preferences())
    b = repo.create_trip("FUK", OUT, RET, Preferences(nonstop_only=True))
    _run(a, NOW - timedelta(hours=5), 200_000)
    _run(b, NOW - timedelta(hours=4), 210_000)
    trips = [t for t in repo.list_trips() if t.id in (a, b)]
    batched = history.run_values_for_trips(trips)
    for t in trips:
        assert batched[t.id] == run_values(repo.load_snapshots(t.id), t.prefs)
