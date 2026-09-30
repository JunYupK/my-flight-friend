# tests/test_results_legs.py

from datetime import UTC, date, datetime, timedelta

from flight_friend.domain.results import current_legs, near_miss, violations
from flight_friend.types import LegQuote, Preferences, Snapshot

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
W = timedelta(hours=6)


def leg(
    key: str,
    price: int,
    dep: str = "10:00",
    airline: str = "KE",
    stops: int | None = 0,
    duration: int | None = 120,
) -> LegQuote:
    return LegQuote(
        flight_key=key,
        airline_iata=airline,
        airline_name=airline,
        flight_numbers=[key],
        dep_airport="ICN",
        arr_airport="NRT",
        dep_time=dep,
        arr_time="12:00",
        duration_min=duration,
        stops=stops,
        price=price,
        booking_url=None,
        search_url=None,
    )


_id = 0


def snap(
    provider: str,
    legs: list[LegQuote],
    observed_at: datetime | None = None,
    direction: str = "out",
    status: str = "ok",
    kind: str = "oneway",
) -> Snapshot:
    global _id
    _id += 1
    return Snapshot(
        id=_id,
        run_id=1,
        trip_id=1,
        provider=provider,
        kind=kind,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        date=date(2026, 12, 1),
        status=status,
        card_count=len(legs),
        observed_at=observed_at or NOW - timedelta(hours=1),
        error=None if status == "ok" else "boom",
        legs=legs,
        rts=[],
    )


def merged(legs: list[LegQuote], direction: str = "out"):
    return current_legs([snap("gf", legs, direction=direction)], NOW, W)[direction]


def test_latest_ok_snapshot_only():
    old = snap("gf", [leg("A", 100_000), leg("B", 90_000)], NOW - timedelta(hours=3))
    new = snap("gf", [leg("A", 110_000)], NOW - timedelta(hours=1))
    out = current_legs([old, new], NOW, W)["out"]
    assert [m.flight_key for m in out] == ["A"]
    assert out[0].best_price == 110_000


def test_failed_provider_keeps_previous_ok():
    ok = snap("gf", [leg("A", 100_000)], NOW - timedelta(hours=3))
    err = snap("gf", [], NOW - timedelta(hours=1), status="error")
    out = current_legs([ok, err], NOW, W)["out"]
    assert out[0].best_price == 100_000


def test_stale_excluded_from_best():
    fresh = snap("gf", [leg("A", 120_000)], NOW - timedelta(hours=1))
    stale = snap("nv", [leg("A", 90_000)], NOW - timedelta(hours=7))
    m = current_legs([fresh, stale], NOW, W)["out"][0]
    assert [(p.provider, p.stale) for p in m.prices] == [("nv", True), ("gf", False)]
    assert m.best_price == 120_000
    assert m.best_provider == "gf"


def test_stale_boundary_is_fresh():
    s = snap("gf", [leg("A", 100_000)], NOW - W)
    assert current_legs([s], NOW, W)["out"][0].prices[0].stale is False


def test_all_stale_best_price_none():
    s = snap("gf", [leg("A", 100_000), leg("B", 90_000)], NOW - timedelta(hours=9))
    out = current_legs([s], NOW, W)["out"]
    assert all(m.best_price is None and m.best_provider is None for m in out)


def test_sorted_none_last_and_roundtrip_ignored():
    s1 = snap("gf", [leg("A", 200_000)])
    s2 = snap("nv", [leg("B", 100_000)], NOW - timedelta(hours=9))
    rt = snap("gf", [leg("C", 1)], kind="roundtrip", direction=None)  # type: ignore[arg-type]
    out = current_legs([s1, s2, rt], NOW, W)["out"]
    assert [m.flight_key for m in out] == ["A", "B"]


def test_merge_across_providers_representative_and_tie():
    a = snap("nv", [leg("A", 100_000, dep="09:00")])
    b = snap("gf", [leg("A", 100_000, dep="10:00")])
    m = current_legs([a, b], NOW, W)["out"][0]
    assert m.leg.dep_time == "10:00"  # tie -> smallest provider name (gf)
    assert m.best_provider == "gf"


def test_directions_separate():
    res = current_legs(
        [snap("gf", [leg("A", 1)]), snap("gf", [leg("B", 2)], direction="in")], NOW, W
    )
    assert [m.flight_key for m in res["out"]] == ["A"]
    assert [m.flight_key for m in res["in"]] == ["B"]


def test_violations_time_window_inclusive():
    prefs = Preferences(out_dep_window=("08:00", "14:00"))
    assert violations(merged([leg("A", 1, dep="08:00")])[0], "out", prefs) == []
    assert violations(merged([leg("A", 1, dep="14:00")])[0], "out", prefs) == []
    assert violations(merged([leg("A", 1, dep="14:01")])[0], "out", prefs) == ["time_window"]
    assert violations(merged([leg("A", 1, dep="07:59")])[0], "out", prefs) == ["time_window"]
    # in-direction uses in window
    m_in = merged([leg("A", 1, dep="20:00")], "in")[0]
    assert violations(m_in, "in", prefs) == []
    assert violations(m_in, "in", Preferences(in_dep_window=("08:00", "14:00"))) == ["time_window"]


def test_violations_nonstop_airline_duration():
    m = merged([leg("A", 1, airline="7C", stops=1, duration=300)])[0]
    prefs = Preferences(
        out_dep_window=("11:00", "12:00"),
        nonstop_only=True,
        include_airlines=["KE"],
        max_duration_min=200,
    )
    assert violations(m, "out", prefs) == ["time_window", "nonstop", "airline", "duration"]
    unknown = merged([leg("A", 1, stops=None, duration=None)])[0]
    assert violations(unknown, "out", Preferences(nonstop_only=True, max_duration_min=100)) == [
        "nonstop"
    ]
    ke = merged([leg("A", 1, airline="KE")])[0]
    assert violations(ke, "out", Preferences(exclude_airlines=["KE"])) == ["airline"]
    assert violations(ke, "out", Preferences(include_airlines=["KE"])) == []


def _legs(out: list[LegQuote], inn: list[LegQuote]):
    return current_legs(
        [snap("gf", out), snap("gf", inn, direction="in")], NOW, W
    )


PREFS = Preferences(out_dep_window=("08:00", "14:00"))


def test_near_miss_one_violation_with_saving():
    legs = _legs(
        [leg("A", 200_000, dep="09:00"), leg("E", 148_000, dep="07:30")],
        [leg("I", 100_000)],
    )
    nm = near_miss(legs, PREFS)
    assert nm is not None
    assert (nm.direction, nm.violated) == ("out", "time_window")
    assert nm.leg.flight_key == "E"
    assert nm.combo_price == 248_000
    assert nm.saving == 52_000


def test_near_miss_ignores_two_violations():
    legs = _legs(
        [leg("A", 200_000, dep="09:00"), leg("E", 100_000, dep="07:30", stops=1)],
        [leg("I", 100_000)],
    )
    assert near_miss(legs, Preferences(out_dep_window=("08:00", "14:00"), nonstop_only=True)) is None


def test_near_miss_below_threshold_none():
    legs = _legs(
        [leg("A", 200_000, dep="09:00"), leg("E", 195_000, dep="07:30")],
        [leg("I", 100_000)],
    )
    assert near_miss(legs, PREFS) is None


def test_near_miss_pct_threshold():
    # saving 20,000 < 30,000 but >= 10% of M=100,000? no: 10% = 10,000 -> yes
    legs = _legs(
        [leg("A", 50_000, dep="09:00"), leg("E", 30_000, dep="07:30")],
        [leg("I", 50_000)],
    )
    nm = near_miss(legs, PREFS)
    assert nm is not None and nm.saving == 20_000


def test_near_miss_when_no_in_condition_leg():
    legs = _legs(
        [leg("E", 150_000, dep="07:30"), leg("F", 140_000, dep="06:00")],
        [leg("I", 100_000)],
    )
    nm = near_miss(legs, PREFS)
    assert nm is not None
    assert nm.saving == 0
    assert nm.leg.flight_key == "F"
    assert nm.combo_price == 240_000


def test_near_miss_none_without_candidates():
    assert near_miss({"out": [], "in": []}, PREFS) is None
