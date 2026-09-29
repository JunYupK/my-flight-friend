# flight_friend/domain/schedule.py

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flight_friend.config import MANUAL_COOLDOWN
from flight_friend.types import Trip

KST = ZoneInfo("Asia/Seoul")

# 갱신 주기 티어 (잠정치, 실측 후 재조정 예정)
FAR_TIER_DAYS: int = 60
NEAR_TIER_DAYS: int = 14
FAR_INTERVAL: timedelta = timedelta(hours=6)
MID_INTERVAL: timedelta = timedelta(hours=2)
NEAR_INTERVAL: timedelta = timedelta(hours=1)


def refresh_interval(days_to_departure: int) -> timedelta:
    if days_to_departure > FAR_TIER_DAYS:
        return FAR_INTERVAL
    if days_to_departure > NEAR_TIER_DAYS:
        return MID_INTERVAL
    return NEAR_INTERVAL


def freshness_window(days_to_departure: int) -> timedelta:
    return refresh_interval(days_to_departure) * 2


def days_to_departure(out_date: date, today: date) -> int:
    return (out_date - today).days


def is_due(trip: Trip, last_requested_at: datetime | None, now: datetime) -> bool:
    if not trip.tracking or trip.archived_at is not None:
        return False

    today = now.astimezone(KST).date()
    if trip.out_date < today:
        return False

    if last_requested_at is None:
        return True

    dtd = days_to_departure(trip.out_date, today)
    return now - last_requested_at >= refresh_interval(dtd)


def cooldown_remaining(last_requested_at: datetime | None, now: datetime) -> timedelta:
    if last_requested_at is None:
        return timedelta(0)

    remaining = MANUAL_COOLDOWN - (now - last_requested_at)
    return max(timedelta(0), remaining)
