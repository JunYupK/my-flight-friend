# flight_friend/domain/results.py
"""현재 편도 병합 · 선호 조건 위반 · 조건 밖 힌트 (순수 로직, DB 없음)."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

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
    cond_price: int | None = None
    cond_label: str | None = None
    cond_booking_url: str | None = None


@dataclass
class CondPrice:
    price: int
    label: str
    provider: str
    booking_url: str | None


@dataclass
class MergedLeg:
    flight_key: str
    direction: str
    leg: LegQuote
    prices: list[ProviderPrice]
    best_price: int | None
    best_provider: str | None
    best_cond: CondPrice | None = None


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


def _group(entries: list[tuple[Snapshot, LegQuote]]) -> list[list[tuple[Snapshot, LegQuote]]]:
    """flight_key가 같거나 (날짜, 공항, 편명)이 같은 견적을 (전이적으로) 한 묶음으로."""
    parent = list(range(len(entries)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    first_by_key: dict[object, int] = {}
    for i, (_, q) in enumerate(entries):
        keys: list[object] = [("key", q.flight_key)]
        if q.flight_numbers:
            keys.append(
                (q.flight_key.split("|")[0], q.dep_airport, q.arr_airport, tuple(q.flight_numbers))
            )
        for k in keys:
            if k in first_by_key:
                union(i, first_by_key[k])
            else:
                first_by_key[k] = i
    groups: dict[int, list[tuple[Snapshot, LegQuote]]] = {}
    for i, e in enumerate(entries):
        groups.setdefault(find(i), []).append(e)
    return list(groups.values())


def _merge(direction: str, entries: list[tuple[Snapshot, LegQuote]], cutoff: datetime) -> list[MergedLeg]:
    merged: list[MergedLeg] = []
    for items in _group(entries):
        gf = [sq for sq in items if sq[0].provider == "google_flights"]
        rep = min(gf or items, key=lambda sq: (sq[1].price, sq[1].flight_key))[1]
        cheapest: dict[str, tuple[Snapshot, LegQuote]] = {}
        for s, q in items:
            cur = cheapest.get(s.provider)
            if cur is None or q.price < cur[1].price:
                cheapest[s.provider] = (s, q)
        prices = [
            ProviderPrice(
                s.provider,
                q.price,
                s.observed_at,
                q.booking_url,
                s.observed_at < cutoff,
                q.cond_price,
                q.cond_label,
                q.cond_booking_url,
            )
            for s, q in cheapest.values()
        ]
        prices.sort(key=lambda p: (p.price, p.provider))
        fresh = [p for p in prices if not p.stale]
        best_cond: CondPrice | None = None
        conds = [p for p in fresh if p.cond_price is not None]
        if fresh and conds:
            c = min(conds, key=lambda p: (p.cond_price or 0, p.provider))
            if c.cond_price is not None and c.cond_price < fresh[0].price:
                best_cond = CondPrice(c.cond_price, c.cond_label or "", c.provider, c.cond_booking_url)
        merged.append(
            MergedLeg(
                flight_key=rep.flight_key,
                direction=direction,
                leg=rep,
                prices=prices,
                best_price=fresh[0].price if fresh else None,
                best_provider=fresh[0].provider if fresh else None,
                best_cond=best_cond,
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


@dataclass
class Candidate:
    out: MergedLeg
    inn: MergedLeg
    price: int
    stay_min: int


@dataclass
class RtReference:
    airline_iata: str
    rt_min: int
    ow_sum: int | None
    diff: int | None  # ow_sum - rt_min (양수 = 왕복이 쌈)


def stay_minutes(out: LegQuote, out_date: date, inn: LegQuote, ret_date: date) -> int:
    """출국편 도착(arr < dep면 +1일)부터 귀국편 출발까지의 분 (현지 시각 기준)."""
    arrive = datetime.combine(out_date, time.fromisoformat(out.arr_time))
    if out.arr_time < out.dep_time:
        arrive += timedelta(days=1)
    depart = datetime.combine(ret_date, time.fromisoformat(inn.dep_time))
    return int((depart - arrive).total_seconds() // 60)


def in_condition(legs: dict[str, list[MergedLeg]], prefs: Preferences) -> dict[str, list[MergedLeg]]:
    return {
        d: [m for m in legs.get(d, []) if m.best_price is not None and not violations(m, d, prefs)]
        for d in DIRECTIONS
    }


def _combos(
    legs: dict[str, list[MergedLeg]], out_date: date, ret_date: date, max_price: int | None
) -> list[Candidate]:
    combos: list[Candidate] = []
    for o in legs.get("out", []):
        for i in legs.get("in", []):
            if o.best_price is None or i.best_price is None:
                continue
            price = o.best_price + i.best_price
            if max_price is not None and price > max_price:
                continue
            combos.append(Candidate(o, i, price, stay_minutes(o.leg, out_date, i.leg, ret_date)))
    return combos


def pareto_candidates(
    legs_in_condition: dict[str, list[MergedLeg]],
    out_date: date,
    ret_date: date,
    max_price: int | None,
    limit: int = 4,
) -> list[Candidate]:
    """가격 오름차순으로 훑으며 체류시간이 지금까지 최대보다 긴 조합만 남긴다."""
    combos = _combos(legs_in_condition, out_date, ret_date, max_price)
    combos.sort(key=lambda c: (c.price, -c.stay_min))
    frontier: list[Candidate] = []
    best_stay: int | None = None
    for c in combos:
        if best_stay is None or c.stay_min > best_stay:
            frontier.append(c)
            best_stay = c.stay_min
    if len(frontier) <= limit:
        return frontier

    first, last = frontier[0], frontier[-1]
    chosen = {0, len(frontier) - 1}
    slots = limit - 2
    for k in range(1, slots + 1):
        target = first.price + (last.price - first.price) * k / (slots + 1)
        idx = min(
            (i for i in range(len(frontier)) if i not in chosen),
            key=lambda i: (abs(frontier[i].price - target), i),
        )
        chosen.add(idx)
    return [frontier[i] for i in sorted(chosen)]


def cheapest_combo(
    legs_in_condition: dict[str, list[MergedLeg]], max_price: int | None
) -> tuple[MergedLeg, MergedLeg, int] | None:
    best: tuple[MergedLeg, MergedLeg, int] | None = None
    for o in legs_in_condition.get("out", []):
        for i in legs_in_condition.get("in", []):
            if o.best_price is None or i.best_price is None:
                continue
            price = o.best_price + i.best_price
            if max_price is not None and price > max_price:
                continue
            if best is None or price < best[2]:
                best = (o, i, price)
    return best


def _cheapest_by_airline(legs: list[MergedLeg]) -> dict[str, int]:
    result: dict[str, int] = {}
    for m in legs:
        if m.best_price is not None and m.best_price < result.get(m.leg.airline_iata, m.best_price + 1):
            result[m.leg.airline_iata] = m.best_price
    return result


def rt_reference(
    snapshots: list[Snapshot],
    legs: dict[str, list[MergedLeg]],
    now: datetime,
    window: timedelta,
) -> list[RtReference]:
    """왕복으로 따로 살 때의 항공사별 최저가 vs 같은 항공사 편도 합."""
    cutoff = now - window
    latest: dict[str, Snapshot] = {}
    for s in snapshots:
        if s.kind != "roundtrip" or s.status != "ok":
            continue
        if s.provider not in latest or s.observed_at > latest[s.provider].observed_at:
            latest[s.provider] = s
    rt_min: dict[str, int] = {}
    for s in latest.values():
        if s.observed_at < cutoff:
            continue
        for q in s.rts:
            if q.total_price < rt_min.get(q.airline_iata, q.total_price + 1):
                rt_min[q.airline_iata] = q.total_price
    out_min = _cheapest_by_airline(legs.get("out", []))
    in_min = _cheapest_by_airline(legs.get("in", []))
    refs: list[RtReference] = []
    for airline, total in rt_min.items():
        if airline in out_min and airline in in_min:
            ow_sum: int | None = out_min[airline] + in_min[airline]
            diff = ow_sum - total
        else:
            ow_sum, diff = None, None
        refs.append(RtReference(airline, total, ow_sum, diff))
    refs.sort(key=lambda r: (r.rt_min, r.airline_iata))
    return refs
