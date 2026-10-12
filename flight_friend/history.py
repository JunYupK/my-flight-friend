# flight_friend/history.py
#
# 화면·알림이 쓰는 "이력" 읽기. 이력 전체를 매 요청 다시 병합하지 않도록
#  - 끝난 run의 조건 내 최저값(RunValue)은 run_summaries에 한 번 계산해 두고 (prefs·스냅샷 수가 바뀌면 다시),
#  - 현재 상태 계산에 필요한 스냅샷(제공자·방향별 최신 ok 편도, 제공자별 최신 ok 왕복)에만 견적을 붙인다.
# 결과는 run_values(load_snapshots(...)) / load_snapshots(...)를 그대로 쓴 것과 같다.

import json

from flight_friend import repo
from flight_friend.domain.results import latest_ok
from flight_friend.domain.tracking import RunValue, run_values
from flight_friend.types import Snapshot, Trip

_FINISHED = ("done", "error")


def _prefs_key(trip: Trip) -> str:
    return json.dumps(trip.prefs.to_dict(), sort_keys=True)


def run_values_for_trips(trips: list[Trip]) -> dict[int, list[RunValue]]:
    """Trip별 run_values — 끝난 run은 run_summaries 캐시, 진행 중인 run은 그 자리에서 계산."""
    ids = [t.id for t in trips]
    meta = repo.load_snapshot_meta(ids)
    counts: dict[int, int] = {}
    trip_of: dict[int, int] = {}
    for s in meta:
        counts[s.run_id] = counts.get(s.run_id, 0) + 1
        trip_of[s.run_id] = s.trip_id
    open_ids = {rid for tid in ids for rid in repo.open_run_ids(tid)} if ids else set()
    cached = repo.load_run_summaries(ids)
    keys = {t.id: _prefs_key(t) for t in trips}
    prefs = {t.id: t.prefs for t in trips}

    values: dict[int, list[RunValue]] = {tid: [] for tid in ids}
    stale: list[int] = []
    for run_id, count in counts.items():
        tid = trip_of[run_id]
        row = cached.get(run_id)
        if run_id in open_ids or row is None or row[1] != keys[tid] or row[2] != count:
            stale.append(run_id)
            continue
        observed_at, combo, out_min, in_min, partial = row[3:]
        values[tid].append(RunValue(run_id, observed_at, combo, out_min, in_min, partial))

    if stale:
        by_trip: dict[int, list[Snapshot]] = {}
        for s in repo.load_run_snapshots(stale):
            by_trip.setdefault(s.trip_id, []).append(s)
        rows: list[tuple] = []
        for tid, snaps in by_trip.items():
            for v in run_values(snaps, prefs[tid]):
                values[tid].append(v)
                if v.run_id not in open_ids:
                    rows.append((v.run_id, tid, keys[tid], counts[v.run_id], v.observed_at,
                                 v.combo, v.out_min, v.in_min, v.partial))
        repo.save_run_summaries(rows)

    for vs in values.values():
        vs.sort(key=lambda v: v.observed_at)
    return values


def run_values_for(trip: Trip) -> list[RunValue]:
    return run_values_for_trips([trip])[trip.id]


def current_snapshots(trip_ids: list[int]) -> dict[int, list[Snapshot]]:
    """Trip별 스냅샷 전체(시각·상태) — 견적은 현재 상태 계산에 쓰이는 최신 스냅샷에만 붙인다."""
    meta = repo.load_snapshot_meta(trip_ids)
    by_trip: dict[int, list[Snapshot]] = {tid: [] for tid in trip_ids}
    for s in meta:
        by_trip[s.trip_id].append(s)
    needed: list[Snapshot] = []
    for snaps in by_trip.values():
        needed.extend(latest_ok(snaps).values())
        latest_rt: dict[str, Snapshot] = {}
        for s in snaps:
            if s.kind == "roundtrip" and s.status == "ok" and (
                s.provider not in latest_rt or s.observed_at > latest_rt[s.provider].observed_at
            ):
                latest_rt[s.provider] = s
        needed.extend(latest_rt.values())
    repo.attach_quotes(needed)
    return by_trip
