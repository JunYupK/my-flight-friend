# tests/v2/test_tracking.py

import os
import sys
from datetime import UTC, date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flight_friend.domain.tracking import (
    DayPoint,
    RunValue,
    daily_series,
    run_values,
    should_alert_new_low,
    should_alert_target,
    tracking_stats,
)
from flight_friend.types import LegQuote, Preferences, Snapshot

T0 = datetime(2026, 9, 20, 3, 0, tzinfo=UTC)  # KST 12:00


def lq(key: str, price: int, dep: str = "08:00") -> LegQuote:
    return LegQuote(
        flight_key=key,
        airline_iata="KE",
        airline_name="KE",
        flight_numbers=[key],
        dep_airport="ICN",
        arr_airport="FUK",
        dep_time=dep,
        arr_time="10:00",
        duration_min=120,
        stops=0,
        price=price,
        booking_url=None,
        search_url=None,
    )


def snap(
    run_id: int,
    direction: str,
    price: int,
    observed_at: datetime = T0,
    status: str = "ok",
    dep: str = "08:00",
    provider: str = "google_flights",
) -> Snapshot:
    legs = [lq(f"{direction}-{dep}", price, dep)] if status == "ok" else []
    return Snapshot(
        id=0,
        run_id=run_id,
        trip_id=1,
        provider=provider,
        kind="oneway",
        direction="out" if direction == "out" else "in",
        date=date(2026, 10, 21),
        status=status,
        card_count=len(legs),
        observed_at=observed_at,
        error=None,
        legs=legs,
        rts=[],
    )


def run_pair(run_id: int, out: int, inn: int, at: datetime = T0) -> list[Snapshot]:
    return [snap(run_id, "out", out, at), snap(run_id, "in", inn, at)]


def dp(day: int, combo: int | None, partial: bool = False) -> DayPoint:
    return DayPoint(date(2026, 9, day), combo, combo, combo, partial)


def series(combos: list[int]) -> list[DayPoint]:
    return [dp(20 + i, c) for i, c in enumerate(combos)]


def test_run_values_partial_flag() -> None:
    snaps = run_pair(1, 100_000, 150_000) + [
        snap(2, "out", 90_000),
        snap(2, "in", 0, status="error"),
    ]
    vals = run_values(snaps, Preferences())
    assert [(v.run_id, v.combo, v.partial) for v in vals] == [(1, 250_000, False), (2, None, True)]
    assert vals[0].out_min == 100_000 and vals[0].in_min == 150_000
    assert vals[1].out_min == 90_000 and vals[1].in_min is None


def test_run_values_respect_prefs() -> None:
    snaps = [
        snap(1, "out", 80_000, dep="05:00"),
        snap(1, "out", 100_000, dep="09:00", provider="amadeus"),
        snap(1, "in", 150_000),
    ]
    vals = run_values(snaps, Preferences(out_dep_window=("07:00", "12:00")))
    assert vals[0].out_min == 100_000
    assert vals[0].combo == 250_000


def test_run_values_max_price_and_order() -> None:
    later = T0 + timedelta(hours=6)
    snaps = run_pair(2, 100_000, 150_000, later) + run_pair(1, 100_000, 150_000, T0)
    vals = run_values(snaps, Preferences(max_price=200_000))
    assert [v.run_id for v in vals] == [1, 2]
    assert vals[0].combo is None and vals[0].observed_at == T0


def test_daily_series_takes_daily_min() -> None:
    snaps = (
        run_pair(1, 100_000, 150_000, T0)
        + run_pair(2, 100_000, 140_000, T0 + timedelta(hours=1))
        + run_pair(3, 100_000, 160_000, T0 + timedelta(hours=2))
    )
    s = daily_series(run_values(snaps, Preferences()))
    assert len(s) == 1
    assert s[0].combo == 240_000
    assert s[0].day == date(2026, 9, 20)


def test_daily_series_kst_day_and_partial() -> None:
    # 2026-09-20 16:00 UTC == 2026-09-21 01:00 KST
    a = RunValue(1, datetime(2026, 9, 20, 16, 0, tzinfo=UTC), 250_000, 100_000, 150_000, True)
    b = RunValue(2, datetime(2026, 9, 20, 3, 0, tzinfo=UTC), 260_000, 110_000, 150_000, False)
    c = RunValue(3, datetime(2026, 9, 20, 4, 0, tzinfo=UTC), None, 90_000, None, True)
    s = daily_series([a, b, c])
    assert [p.day for p in s] == [date(2026, 9, 20), date(2026, 9, 21)]
    assert s[0].combo == 260_000 and s[0].partial is False
    assert s[0].out_min == 90_000 and s[0].in_min == 150_000
    assert s[1].combo == 250_000 and s[1].partial is True


def test_daily_series_no_combo_day_partial_if_any() -> None:
    a = RunValue(1, T0, None, 90_000, None, False)
    b = RunValue(2, T0 + timedelta(hours=1), None, None, None, True)
    s = daily_series([a, b])
    assert s[0].combo is None and s[0].partial is True


def test_stats_not_comparable_under_3_days() -> None:
    st = tracking_stats(series([300_000, 290_000]), 280_000)
    assert st.days == 2 and st.comparable is False
    assert st.start is None and st.start_day is None
    assert st.low is None and st.low_day is None and st.median is None
    assert st.current == 280_000


def test_stats_start_low_median() -> None:
    st = tracking_stats(series([312_000, 298_000, 301_000, 274_000, 249_000]), 249_000)
    assert st.comparable is True and st.days == 5
    assert st.start == 312_000 and st.start_day == date(2026, 9, 20)
    assert st.low == 249_000 and st.low_day == date(2026, 9, 24)
    assert st.median == 298_000


def test_stats_days_ignore_none_combo_and_low_tie_earliest() -> None:
    s = [dp(20, 300_000), dp(21, None), dp(22, 250_000), dp(23, 250_000)]
    st = tracking_stats(s, None)
    assert st.days == 3 and st.low_day == date(2026, 9, 22)
    assert st.median == 250_000


def test_stats_recomputed_with_new_prefs() -> None:
    snaps: list[Snapshot] = []
    for i, (early, late) in enumerate([(300_000, 320_000), (290_000, 310_000), (280_000, 300_000)]):
        at = T0 + timedelta(days=i)
        snaps += [
            snap(i, "out", early, at, dep="05:00"),
            snap(i, "out", late, at, dep="09:00", provider="amadeus"),
            snap(i, "in", 100_000, at),
        ]
    a = tracking_stats(daily_series(run_values(snaps, Preferences())), None)
    b = tracking_stats(daily_series(run_values(snaps, Preferences(out_dep_window=("07:00", "12:00")))), None)
    assert a.start == 400_000
    assert b.start == 420_000


def test_new_low_alert_threshold() -> None:
    s = series([300_000, 250_000, 260_000, 999_999])
    assert should_alert_new_low(s, 245_000, None) is False
    assert should_alert_new_low(s, 240_000, None) is True


def test_new_low_not_before_3_days() -> None:
    assert should_alert_new_low(series([300_000, 290_000]), 100_000, None) is False
    assert should_alert_new_low(series([300_000, 290_000, 280_000]), None, None) is False


def test_new_low_dedup_against_last_alert() -> None:
    s = series([300_000, 250_000, 260_000, 999_999])
    assert should_alert_new_low(s, 240_000, 245_000) is False
    assert should_alert_new_low(s, 230_000, 245_000) is True


def test_target_alert_once_then_further_drop() -> None:
    assert should_alert_target(240_000, 250_000, None) is True
    assert should_alert_target(260_000, 250_000, None) is False
    assert should_alert_target(None, 250_000, None) is False
    assert should_alert_target(240_000, None, None) is False
    assert should_alert_target(240_000, 250_000, 245_000) is False
    assert should_alert_target(230_000, 250_000, 245_000) is True
