# tests/test_schedule.py

from datetime import UTC, date, datetime, timedelta, timezone

from flight_friend.domain.schedule import (
    cooldown_remaining,
    days_to_departure,
    freshness_window,
    is_due,
    refresh_interval,
)
from flight_friend.types import Preferences, Trip

KST = timezone(timedelta(hours=9))


def _trip(**overrides: object) -> Trip:
    defaults: dict = {
        "id": 1,
        "origin": "ICN",
        "destination": "NRT",
        "out_date": date(2026, 12, 1),
        "ret_date": date(2026, 12, 5),
        "adults": 1,
        "cabin": "economy",
        "prefs": Preferences(),
        "target_price": None,
        "tracking": True,
        "created_at": datetime(2026, 9, 1, tzinfo=KST),
        "archived_at": None,
    }
    defaults.update(overrides)
    return Trip(**defaults)


def test_interval_tiers():
    assert refresh_interval(61) == timedelta(hours=6)
    assert refresh_interval(60) == timedelta(hours=2)
    assert refresh_interval(15) == timedelta(hours=2)
    assert refresh_interval(14) == timedelta(hours=1)


def test_interval_on_departure_day():
    assert refresh_interval(0) == timedelta(hours=1)
    assert refresh_interval(-1) == timedelta(hours=1)


def test_window_is_double():
    assert freshness_window(61) == timedelta(hours=12)
    assert freshness_window(60) == timedelta(hours=4)
    assert freshness_window(14) == timedelta(hours=2)


def test_due_when_never_run():
    trip = _trip(out_date=date(2026, 12, 1))
    now = datetime(2026, 11, 1, tzinfo=KST)
    assert is_due(trip, None, now) is True


def test_not_due_within_interval():
    trip = _trip(out_date=date(2026, 10, 1))  # <=14일 tier -> 1h interval
    now = datetime(2026, 9, 28, 12, 0, tzinfo=KST)
    last_requested_at = now - timedelta(minutes=30)
    assert is_due(trip, last_requested_at, now) is False


def test_not_due_when_tracking_off():
    trip = _trip(out_date=date(2026, 10, 1), tracking=False)
    now = datetime(2026, 9, 28, 12, 0, tzinfo=KST)
    assert is_due(trip, None, now) is False


def test_not_due_after_departure():
    trip = _trip(out_date=date(2026, 9, 1))
    now = datetime(2026, 9, 28, 12, 0, tzinfo=KST)
    assert is_due(trip, None, now) is False


def test_cooldown_remaining():
    now = datetime(2026, 9, 28, 12, 0, tzinfo=KST)
    assert cooldown_remaining(None, now) == timedelta(0)
    assert cooldown_remaining(now - timedelta(minutes=3), now) == timedelta(minutes=2)
    assert cooldown_remaining(now - timedelta(minutes=10), now) == timedelta(0)


def test_days_to_departure():
    assert days_to_departure(date(2026, 12, 1), date(2026, 9, 28)) == 64
    assert days_to_departure(date(2026, 9, 28), date(2026, 9, 28)) == 0
    assert days_to_departure(date(2026, 9, 1), date(2026, 9, 28)) == -27


def test_due_after_interval_elapsed():
    trip = _trip(out_date=date(2026, 10, 1))  # 1h interval
    now = datetime(2026, 9, 28, 12, 0, tzinfo=KST)
    assert is_due(trip, now - timedelta(hours=1), now) is True


def test_not_due_when_archived():
    trip = _trip(out_date=date(2026, 10, 1), archived_at=datetime(2026, 9, 20, tzinfo=KST))
    now = datetime(2026, 9, 28, 12, 0, tzinfo=KST)
    assert is_due(trip, None, now) is False


def test_today_is_kst_date():
    # 2026-09-27 16:00 UTC == 2026-09-28 01:00 KST -> 출발일 9/28은 아직 유효
    trip = _trip(out_date=date(2026, 9, 28))
    now = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)
    assert is_due(trip, None, now) is True
    # 2026-09-28 16:00 UTC == 9/29 01:00 KST -> 출발 지남
    assert is_due(trip, None, datetime(2026, 9, 28, 16, 0, tzinfo=UTC)) is False
