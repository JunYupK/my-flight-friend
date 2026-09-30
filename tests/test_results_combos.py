# tests/test_results_combos.py

from datetime import UTC, date, datetime, timedelta

from flight_friend.domain.results import (
    MergedLeg,
    cheapest_combo,
    in_condition,
    pareto_candidates,
    rt_reference,
    stay_minutes,
)
from flight_friend.types import LegQuote, Preferences, RtQuote, Snapshot

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
W = timedelta(hours=6)
OUT_DATE = date(2026, 10, 21)
RET_DATE = date(2026, 10, 25)


def lq(key: str, price: int, dep: str = "08:00", arr: str = "10:00", airline: str = "KE") -> LegQuote:
    return LegQuote(
        flight_key=key,
        airline_iata=airline,
        airline_name=airline,
        flight_numbers=[key],
        dep_airport="ICN",
        arr_airport="FUK",
        dep_time=dep,
        arr_time=arr,
        duration_min=120,
        stops=0,
        price=price,
        booking_url=None,
        search_url=None,
    )


def ml(
    key: str,
    price: int | None,
    direction: str = "out",
    dep: str = "08:00",
    arr: str = "10:00",
    airline: str = "KE",
) -> MergedLeg:
    return MergedLeg(
        flight_key=key,
        direction=direction,
        leg=lq(key, price or 0, dep, arr, airline),
        prices=[],
        best_price=price,
        best_provider="google_flights" if price is not None else None,
    )


def rt_snap(provider: str, rts: list[RtQuote], observed_at: datetime = NOW, status: str = "ok") -> Snapshot:
    return Snapshot(
        id=1,
        run_id=1,
        trip_id=1,
        provider=provider,
        kind="roundtrip",
        direction=None,
        date=OUT_DATE,
        status=status,
        card_count=len(rts),
        observed_at=observed_at,
        error=None,
        legs=[],
        rts=rts,
    )


def test_stay_minutes_same_day() -> None:
    out = lq("o", 1, dep="12:00", arr="16:00")
    inn = lq("i", 1, dep="10:30", arr="12:30")
    assert stay_minutes(out, OUT_DATE, inn, RET_DATE) == 4 * 24 * 60 - 330 == 5430


def test_stay_minutes_overnight_arrival() -> None:
    out = lq("o", 1, dep="23:40", arr="02:10")
    inn = lq("i", 1, dep="02:10", arr="04:00")
    # 도착은 10/22 02:10
    assert stay_minutes(out, OUT_DATE, inn, date(2026, 10, 22)) == 0
    assert stay_minutes(out, OUT_DATE, inn, date(2026, 10, 23)) == 24 * 60


def _pareto_legs() -> dict[str, list[MergedLeg]]:
    # 귀국편 1개(12:00 출발, 100,000) x 출국편 4개 -> 조합가 231k/263k/250k/302k
    inn = ml("i", 100_000, "in", dep="12:00", arr="14:00")
    outs = [
        ml("o1", 131_000, dep="08:00", arr="16:00"),  # 3일 20시간
        ml("o2", 163_000, dep="06:00", arr="11:00"),  # 4일 1시간
        ml("o3", 150_000, dep="06:00", arr="22:00"),  # 3일 10시간
        ml("o4", 202_000, dep="06:00", arr="07:00"),  # 4일 5시간
    ]
    return {"out": outs, "in": [inn]}


def test_pareto_frontier() -> None:
    result = pareto_candidates(_pareto_legs(), OUT_DATE, RET_DATE, None)
    assert [c.price for c in result] == [231_000, 263_000, 302_000]
    assert [c.out.flight_key for c in result] == ["o1", "o2", "o4"]
    assert result[0].stay_min == 3 * 1440 + 20 * 60


def test_pareto_limit_keeps_extremes() -> None:
    outs = [ml(f"o{i}", 100_000 + 10_000 * i, dep="05:00", arr=f"{20 - i:02d}:00") for i in range(7)]
    inn = ml("i", 0, "in", dep="12:00")
    full = pareto_candidates({"out": outs, "in": [inn]}, OUT_DATE, RET_DATE, None, limit=10)
    assert len(full) == 7
    result = pareto_candidates({"out": outs, "in": [inn]}, OUT_DATE, RET_DATE, None, limit=4)
    assert len(result) == 4
    assert result[0].price == 100_000
    assert result[-1].price == 160_000
    assert [c.price for c in result] == [100_000, 120_000, 140_000, 160_000]


def test_pareto_respects_max_price() -> None:
    result = pareto_candidates(_pareto_legs(), OUT_DATE, RET_DATE, 270_000)
    assert [c.price for c in result] == [231_000, 263_000]


def test_pareto_empty_when_one_side_filtered_out() -> None:
    assert pareto_candidates({"out": _pareto_legs()["out"], "in": []}, OUT_DATE, RET_DATE, None) == []
    assert pareto_candidates(_pareto_legs(), OUT_DATE, RET_DATE, 100_000) == []


def test_in_condition_filters_violations_and_unpriced() -> None:
    legs = {
        "out": [ml("o1", 100, dep="08:00"), ml("o2", 90, dep="02:00"), ml("o3", None)],
        "in": [ml("i1", 50, "in")],
    }
    prefs = Preferences(out_dep_window=("06:00", "12:00"))
    result = in_condition(legs, prefs)
    assert [m.flight_key for m in result["out"]] == ["o1"]
    assert [m.flight_key for m in result["in"]] == ["i1"]
    assert in_condition({"out": [], "in": []}, prefs) == {"out": [], "in": []}


def test_cheapest_combo() -> None:
    legs = _pareto_legs()
    combo = cheapest_combo(legs, None)
    assert combo is not None
    out, inn, price = combo
    assert (out.flight_key, inn.flight_key, price) == ("o1", "i", 231_000)
    assert cheapest_combo(legs, 200_000) is None
    assert cheapest_combo({"out": [], "in": legs["in"]}, None) is None


def _fuk_legs() -> dict[str, list[MergedLeg]]:
    return {
        "out": [
            ml("o7c", 200_000, airline="7C"),
            ml("o7c2", 250_000, airline="7C"),
            ml("ors", 190_000, airline="RS"),
        ],
        "in": [
            ml("i7c", 176_031, "in", airline="7C"),
            ml("irs", 174_317, "in", airline="RS"),
        ],
    }


def test_rt_reference_matches_spec_example() -> None:
    snaps = [
        rt_snap("google_flights", [RtQuote("7C", "o7c", 361_000), RtQuote("7C", "o7c2", 360_600)]),
        rt_snap("skyscanner", [RtQuote("RS", "ors", 372_300)]),
    ]
    result = rt_reference(snaps, _fuk_legs(), NOW, W)
    assert [(r.airline_iata, r.rt_min, r.ow_sum, r.diff) for r in result] == [
        ("7C", 360_600, 376_031, 15_431),
        ("RS", 372_300, 364_317, -7_983),
    ]


def test_rt_reference_ow_missing_gives_none() -> None:
    snaps = [rt_snap("google_flights", [RtQuote("LJ", "x", 300_000)])]
    result = rt_reference(snaps, _fuk_legs(), NOW, W)
    assert [(r.airline_iata, r.ow_sum, r.diff) for r in result] == [("LJ", None, None)]


def test_rt_reference_ignores_stale_roundtrip() -> None:
    stale = rt_snap("google_flights", [RtQuote("7C", "o7c", 360_600)], observed_at=NOW - W - timedelta(minutes=1))
    assert rt_reference([stale], _fuk_legs(), NOW, W) == []
    edge = rt_snap("google_flights", [RtQuote("7C", "o7c", 360_600)], observed_at=NOW - W)
    assert len(rt_reference([edge], _fuk_legs(), NOW, W)) == 1


def test_rt_reference_uses_latest_ok_per_provider() -> None:
    old = rt_snap("google_flights", [RtQuote("7C", "o7c", 300_000)], observed_at=NOW - timedelta(hours=2))
    new = rt_snap("google_flights", [RtQuote("7C", "o7c", 360_600)], observed_at=NOW - timedelta(hours=1))
    failed = rt_snap("google_flights", [], observed_at=NOW, status="blocked")
    result = rt_reference([old, new, failed], _fuk_legs(), NOW, W)
    assert [r.rt_min for r in result] == [360_600]
