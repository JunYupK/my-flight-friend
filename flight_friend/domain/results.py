# flight_friend/domain/results.py
"""현재 편도 병합 · 선호 조건 위반 · 조건 밖 힌트 (순수 로직, DB 없음)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from flight_friend.config import NEAR_MISS_MIN_KRW, NEAR_MISS_MIN_PCT
from flight_friend.types import LegQuote, Preferences, Snapshot

DIRECTIONS = ("out", "in")


@dataclass
class ProviderPrice:
    provider: str
    price: int
    observed_at: datetime
    booking_url: str | None
    stale: bool


@dataclass
class MergedLeg:
    flight_key: str
    direction: str
    leg: LegQuote
    prices: list[ProviderPrice]
    best_price: int | None
    best_provider: str | None


@dataclass
class NearMiss:
    direction: str
    leg: MergedLeg
    violated: str
    combo_price: int
    saving: int


def _latest_ok(snapshots: list[Snapshot]) -> dict[tuple[str, str], Snapshot]:
    latest: dict[tuple[str, str], Snapshot] = {}
    for s in snapshots:
        if s.kind != "oneway" or s.status != "ok" or s.direction is None:
            continue
        k = (s.provider, s.direction)
        if k not in latest or s.observed_at > latest[k].observed_at:
            latest[k] = s
    return latest


def _merge(direction: str, entries: list[tuple[Snapshot, LegQuote]], cutoff: datetime) -> list[MergedLeg]:
    by_key: dict[str, list[tuple[Snapshot, LegQuote]]] = {}
    for s, q in entries:
        by_key.setdefault(q.flight_key, []).append((s, q))
    merged: list[MergedLeg] = []
    for key, items in by_key.items():
        items.sort(key=lambda sq: (sq[1].price, sq[0].provider))
        prices = [
            ProviderPrice(s.provider, q.price, s.observed_at, q.booking_url, s.observed_at < cutoff)
            for s, q in items
        ]
        fresh = [p for p in prices if not p.stale]
        merged.append(
            MergedLeg(
                flight_key=key,
                direction=direction,
                leg=items[0][1],
                prices=prices,
                best_price=fresh[0].price if fresh else None,
                best_provider=fresh[0].provider if fresh else None,
            )
        )
    merged.sort(key=lambda m: (m.best_price is None, m.best_price or 0, m.flight_key))
    return merged


def current_legs(
    snapshots: list[Snapshot], now: datetime, window: timedelta
) -> dict[str, list[MergedLeg]]:
    """(provider, direction)별 최신 ok 편도 스냅샷만 병합한다."""
    cutoff = now - window
    latest = _latest_ok(snapshots)
    result: dict[str, list[MergedLeg]] = {}
    for direction in DIRECTIONS:
        entries = [(s, q) for (_, d), s in sorted(latest.items()) if d == direction for q in s.legs]
        result[direction] = _merge(direction, entries, cutoff)
    return result


def violations(m: MergedLeg, direction: str, prefs: Preferences) -> list[str]:
    out: list[str] = []
    window = prefs.out_dep_window if direction == "out" else prefs.in_dep_window
    leg = m.leg
    if window is not None and not (window[0] <= leg.dep_time <= window[1]):
        out.append("time_window")
    if prefs.nonstop_only and leg.stops != 0:
        out.append("nonstop")
    if (prefs.include_airlines and leg.airline_iata not in prefs.include_airlines) or (
        leg.airline_iata in prefs.exclude_airlines
    ):
        out.append("airline")
    if (
        prefs.max_duration_min is not None
        and leg.duration_min is not None
        and leg.duration_min > prefs.max_duration_min
    ):
        out.append("duration")
    return out


def near_miss(legs: dict[str, list[MergedLeg]], prefs: Preferences) -> NearMiss | None:
    """위반이 정확히 1개인 최저가 편이 조건 내 최저 조합보다 얼마나 싼지 힌트."""
    priced: dict[str, list[tuple[MergedLeg, list[str]]]] = {
        d: [(m, violations(m, d, prefs)) for m in legs.get(d, []) if m.best_price is not None]
        for d in DIRECTIONS
    }
    in_cond: dict[str, int | None] = {
        d: min((m.best_price for m, v in priced[d] if not v and m.best_price is not None), default=None)
        for d in DIRECTIONS
    }
    other = {"out": "in", "in": "out"}

    candidates: list[NearMiss] = []
    for d in DIRECTIONS:
        opposite = in_cond[other[d]]
        if opposite is None:
            continue
        singles = [(m, v) for m, v in priced[d] if len(v) == 1]
        if not singles:
            continue
        m, v = min(singles, key=lambda mv: (mv[0].best_price or 0, mv[0].flight_key))
        assert m.best_price is not None
        candidates.append(NearMiss(d, m, v[0], m.best_price + opposite, 0))
    if not candidates:
        return None

    out_min, in_min = in_cond["out"], in_cond["in"]
    if out_min is None or in_min is None:
        return min(candidates, key=lambda c: c.combo_price)

    base = out_min + in_min
    best: NearMiss | None = None
    for c in candidates:
        saving = base - c.combo_price
        if saving >= NEAR_MISS_MIN_KRW or saving >= NEAR_MISS_MIN_PCT * base:
            c.saving = saving
            if best is None or saving > best.saving:
                best = c
    return best
