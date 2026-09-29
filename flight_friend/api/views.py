# flight_friend/api/views.py
"""Service 레이어: repo + domain 결과를 JSON 직렬화 가능한 dict로 만든다 (FastAPI 의존 없음)."""

from datetime import date, datetime, timedelta

from flight_friend import repo
from flight_friend.domain.results import (
    Candidate,
    MergedLeg,
    NearMiss,
    RtReference,
    current_legs,
    in_condition,
    near_miss,
    pareto_candidates,
    rt_reference,
    violations,
)
from flight_friend.domain.schedule import KST, days_to_departure, freshness_window
from flight_friend.domain.tracking import (
    DayPoint,
    Stats,
    current_value,
    daily_series,
    run_values,
    tracking_stats,
)
from flight_friend.types import Run, Snapshot, Trip

JsonDict = dict[str, object]


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _today(now: datetime) -> date:
    return now.astimezone(KST).date()


def _window(trip: Trip, now: datetime) -> timedelta:
    return freshness_window(days_to_departure(trip.out_date, _today(now)))


def is_archived(trip: Trip, now: datetime) -> bool:
    return trip.archived_at is not None or trip.out_date < _today(now)


def _stats_view(s: Stats) -> JsonDict:
    return {
        "current": s.current,
        "start": s.start,
        "start_day": _iso(s.start_day),
        "low": s.low,
        "low_day": _iso(s.low_day),
        "median": s.median,
        "days": s.days,
        "comparable": s.comparable,
    }


def _leg_view(m: MergedLeg, direction: str, trip: Trip) -> JsonDict:
    v = violations(m, direction, trip.prefs)
    leg = m.leg
    return {
        "flight_key": m.flight_key,
        "dep_time": leg.dep_time,
        "arr_time": leg.arr_time,
        "airline_name": leg.airline_name,
        "airline_iata": leg.airline_iata,
        "flight_numbers": leg.flight_numbers,
        "stops": leg.stops,
        "duration_min": leg.duration_min,
        "dep_airport": leg.dep_airport,
        "arr_airport": leg.arr_airport,
        "best_price": m.best_price,
        "best_provider": m.best_provider,
        "in_condition": not v and m.best_price is not None,
        "violations": v,
        "prices": [
            {
                "provider": p.provider,
                "price": p.price,
                "observed_at": p.observed_at.isoformat(),
                "booking_url": p.booking_url,
                "stale": p.stale,
            }
            for p in m.prices
        ],
    }


def _candidate_view(c: Candidate) -> JsonDict:
    return {
        "out_flight_key": c.out.flight_key,
        "in_flight_key": c.inn.flight_key,
        "price": c.price,
        "stay_min": c.stay_min,
    }


def _near_miss_view(n: NearMiss | None) -> JsonDict | None:
    if n is None:
        return None
    return {
        "direction": n.direction,
        "flight_key": n.leg.flight_key,
        "violated": n.violated,
        "combo_price": n.combo_price,
        "saving": n.saving,
    }


def _rt_view(r: RtReference) -> JsonDict:
    return {"airline_iata": r.airline_iata, "rt_min": r.rt_min, "ow_sum": r.ow_sum, "diff": r.diff}


def _trip_dict(trip: Trip, now: datetime) -> JsonDict:
    return {
        "id": trip.id,
        "origin": trip.origin,
        "destination": trip.destination,
        "out_date": trip.out_date.isoformat(),
        "ret_date": trip.ret_date.isoformat(),
        "adults": trip.adults,
        "cabin": trip.cabin,
        "prefs": dict(trip.prefs.to_dict()),
        "target_price": trip.target_price,
        "tracking": trip.tracking,
        "archived": is_archived(trip, now),
        "days_to_departure": days_to_departure(trip.out_date, _today(now)),
        "created_at": trip.created_at.isoformat(),
    }


def _providers_view(snapshots: list[Snapshot]) -> list[JsonDict]:
    if not snapshots:
        return []
    last_run_id = max(s.run_id for s in snapshots)
    in_run = [s for s in snapshots if s.run_id == last_run_id]
    views: list[JsonDict] = []
    for provider in sorted({s.provider for s in in_run}):
        mine = [s for s in in_run if s.provider == provider]
        oneway = [s for s in mine if s.kind == "oneway"] or mine
        status = next((s.status for s in oneway if s.status != "ok"), "ok")
        ok_times = [
            s.observed_at
            for s in snapshots
            if s.provider == provider and s.kind == "oneway" and s.status == "ok"
        ]
        views.append(
            {
                "provider": provider,
                "status": status,
                "observed_at": max(s.observed_at for s in mine).isoformat(),
                "last_ok_at": _iso(max(ok_times) if ok_times else None),
            }
        )
    return views


def _run_summary(run: Run | None) -> JsonDict | None:
    if run is None:
        return None
    return {"id": run.id, "status": run.status, "requested_at": run.requested_at.isoformat()}


def trip_view(trip: Trip, now: datetime) -> JsonDict:
    snaps = repo.load_snapshots(trip.id)
    window = _window(trip, now)
    legs = current_legs(snaps, now, window)
    current = current_value(snaps, trip.prefs, now, window)
    stats = tracking_stats(daily_series(run_values(snaps, trip.prefs)), current)
    candidates = pareto_candidates(
        in_condition(legs, trip.prefs), trip.out_date, trip.ret_date, trip.prefs.max_price
    )
    return {
        "trip": _trip_dict(trip, now),
        "run": _run_summary(repo.latest_run(trip.id)),
        "providers": _providers_view(snaps),
        "stats": _stats_view(stats),
        "legs": {d: [_leg_view(m, d, trip) for m in legs[d]] for d in ("out", "in")},
        "candidates": [_candidate_view(c) for c in candidates],
        "near_miss": _near_miss_view(near_miss(legs, trip.prefs)),
        "rt_reference": [_rt_view(r) for r in rt_reference(snaps, legs, now, window)],
        "window_minutes": int(window.total_seconds() // 60),
    }


def trip_list_item(trip: Trip, now: datetime) -> JsonDict:
    snaps = repo.load_snapshots(trip.id)
    window = _window(trip, now)
    current = current_value(snaps, trip.prefs, now, window)
    stats = tracking_stats(daily_series(run_values(snaps, trip.prefs)), current)
    legs = current_legs(snaps, now, window)
    used = [p.observed_at for d in legs.values() for m in d for p in m.prices if not p.stale]
    change: float | None = None
    if stats.comparable and stats.start and current is not None:
        change = round((current / stats.start - 1) * 100, 1)
    return {
        "id": trip.id,
        "destination": trip.destination,
        "out_date": trip.out_date.isoformat(),
        "ret_date": trip.ret_date.isoformat(),
        "days_to_departure": days_to_departure(trip.out_date, _today(now)),
        "tracking": trip.tracking,
        "current": current,
        "current_observed_at": _iso(max(used) if used else None),
        "change_vs_start_pct": change,
        "archived": is_archived(trip, now),
    }


def trip_list(now: datetime) -> list[JsonDict]:
    return [trip_list_item(t, now) for t in repo.list_trips()]


def run_view(run: Run) -> JsonDict:
    return {
        "id": run.id,
        "status": run.status,
        "snapshots": [
            {"provider": s.provider, "kind": s.kind, "direction": s.direction, "status": s.status}
            for s in repo.load_snapshots(run.trip_id)
            if s.run_id == run.id
        ],
    }


def _day_point(p: DayPoint) -> JsonDict:
    return {
        "day": p.day.isoformat(),
        "combo": p.combo,
        "out_min": p.out_min,
        "in_min": p.in_min,
        "partial": p.partial,
    }


def history_view(trip: Trip) -> list[JsonDict]:
    series = daily_series(run_values(repo.load_snapshots(trip.id), trip.prefs))
    return [_day_point(p) for p in series]


def admin_runs_view(limit: int = 50) -> list[JsonDict]:
    return [
        {
            **{k: v for k, v in r.items() if k not in ("requested_at", "started_at", "finished_at")},
            "requested_at": _iso(r["requested_at"]),
            "started_at": _iso(r["started_at"]),
            "finished_at": _iso(r["finished_at"]),
        }
        for r in repo.recent_runs(limit)
    ]


def admin_providers_view(days: int) -> list[JsonDict]:
    return [{**r, "day": _iso(r["day"])} for r in repo.provider_stats(days)]
