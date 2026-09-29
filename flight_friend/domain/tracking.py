# flight_friend/domain/tracking.py
"""추적 값 · 통계 · 알림 판정 (순수 로직). 통계는 추적 시작 이후 관측값만 설명한다."""

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flight_friend.config import ALERT_DROP_KRW, ALERT_DROP_PCT, MIN_TRACKING_DAYS
from flight_friend.domain.results import cheapest_combo, current_legs, in_condition
from flight_friend.types import Preferences, Snapshot

KST = ZoneInfo("Asia/Seoul")
_NEVER_STALE = timedelta(days=36500)


@dataclass
class RunValue:
    run_id: int
    observed_at: datetime
    combo: int | None
    out_min: int | None
    in_min: int | None
    partial: bool


@dataclass
class DayPoint:
    day: date
    combo: int | None
    out_min: int | None
    in_min: int | None
    partial: bool


@dataclass
class Stats:
    current: int | None
    start: int | None
    start_day: date | None
    low: int | None
    low_day: date | None
    median: int | None
    days: int
    comparable: bool


def _min_or_none(values: list[int | None]) -> int | None:
    present = [v for v in values if v is not None]
    return min(present) if present else None


def run_values(snapshots: list[Snapshot], prefs: Preferences) -> list[RunValue]:
    """run별로 그 run의 스냅샷만으로 조건 내 최저값을 계산한다 (W 무시)."""
    by_run: dict[int, list[Snapshot]] = {}
    for s in snapshots:
        by_run.setdefault(s.run_id, []).append(s)
    values: list[RunValue] = []
    for run_id, snaps in by_run.items():
        observed_at = max(s.observed_at for s in snaps)
        legs = in_condition(current_legs(snaps, observed_at, _NEVER_STALE), prefs)
        best = cheapest_combo(legs, prefs.max_price)
        values.append(
            RunValue(
                run_id=run_id,
                observed_at=observed_at,
                combo=best[2] if best else None,
                out_min=_min_or_none([m.best_price for m in legs["out"]]),
                in_min=_min_or_none([m.best_price for m in legs["in"]]),
                partial=any(s.kind == "oneway" and s.status != "ok" for s in snaps),
            )
        )
    values.sort(key=lambda v: v.observed_at)
    return values


def current_value(snapshots: list[Snapshot], prefs: Preferences, now: datetime, window: timedelta) -> int | None:
    """W 안의 최신 스냅샷으로 만든 조건 내 최저 왕복 조합 가격 (없으면 None)."""
    best = cheapest_combo(in_condition(current_legs(snapshots, now, window), prefs), prefs.max_price)
    return best[2] if best else None


def daily_series(values: list[RunValue]) -> list[DayPoint]:
    by_day: dict[date, list[RunValue]] = {}
    for v in values:
        by_day.setdefault(v.observed_at.astimezone(KST).date(), []).append(v)
    points: list[DayPoint] = []
    for day in sorted(by_day):
        runs = by_day[day]
        with_combo = [r for r in runs if r.combo is not None]
        if with_combo:
            best = min(with_combo, key=lambda r: (r.combo or 0, r.observed_at))
            combo: int | None = best.combo
            partial = best.partial
        else:
            combo, partial = None, any(r.partial for r in runs)
        points.append(
            DayPoint(
                day=day,
                combo=combo,
                out_min=_min_or_none([r.out_min for r in runs]),
                in_min=_min_or_none([r.in_min for r in runs]),
                partial=partial,
            )
        )
    return points


def tracking_stats(series: list[DayPoint], current: int | None) -> Stats:
    tracked = [p for p in series if p.combo is not None]
    days = len(tracked)
    if days < MIN_TRACKING_DAYS:
        return Stats(current, None, None, None, None, None, days, False)
    combos = [p.combo for p in tracked if p.combo is not None]
    first = tracked[0]
    lowest = min(tracked, key=lambda p: (p.combo or 0, p.day))
    return Stats(
        current=current,
        start=first.combo,
        start_day=first.day,
        low=lowest.combo,
        low_day=lowest.day,
        median=round(statistics.median(combos)),
        days=days,
        comparable=True,
    )


def _significant_drop(reference: int, current: int) -> bool:
    drop = reference - current
    return drop >= ALERT_DROP_KRW or drop >= ALERT_DROP_PCT * reference


def should_alert_new_low(series: list[DayPoint], current: int | None, last_alert_price: int | None) -> bool:
    if current is None or not tracking_stats(series, current).comparable:
        return False
    previous_low = _min_or_none([p.combo for p in series[:-1]])
    if previous_low is None or not _significant_drop(previous_low, current):
        return False
    return last_alert_price is None or _significant_drop(last_alert_price, current)


def should_alert_target(current: int | None, target: int | None, last_alert_price: int | None) -> bool:
    if current is None or target is None or current > target:
        return False
    return last_alert_price is None or _significant_drop(last_alert_price, current)
