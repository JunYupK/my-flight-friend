# flight_friend/repo.py

import json
from datetime import date, datetime, timedelta
from typing import Literal

from psycopg2.extras import RealDictCursor, RealDictRow, execute_values

from flight_friend.db import get_conn
from flight_friend.types import (
    LegQuote,
    Preferences,
    ProviderResult,
    RtQuote,
    Run,
    Snapshot,
    Trip,
)


def _row_to_trip(row: RealDictRow) -> Trip:
    return Trip(
        id=row["id"],
        origin=row["origin"],
        destination=row["destination"],
        out_date=row["out_date"],
        ret_date=row["ret_date"],
        adults=row["adults"],
        cabin=row["cabin"],
        prefs=Preferences.from_dict(row["prefs"]),
        target_price=row["target_price"],
        tracking=row["tracking"],
        created_at=row["created_at"],
        archived_at=row["archived_at"],
    )


def _row_to_run(row: RealDictRow) -> Run:
    return Run(
        id=row["id"],
        trip_id=row["trip_id"],
        trigger=row["trigger"],
        status=row["status"],
        requested_at=row["requested_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def create_trip(
    destination: str,
    out_date: date,
    ret_date: date,
    prefs: Preferences,
    target_price: int | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO trips (destination, out_date, ret_date, prefs, target_price)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (destination, out_date, ret_date, json.dumps(prefs.to_dict()), target_price),
        )
        trip_id: int = cur.fetchone()[0]
        return trip_id


def get_trip(trip_id: int) -> Trip | None:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM trips WHERE id = %s", (trip_id,))
        row = cur.fetchone()
        return _row_to_trip(row) if row else None


def list_trips() -> list[Trip]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM trips ORDER BY out_date ASC")
        return [_row_to_trip(row) for row in cur.fetchall()]


def delete_trip(trip_id: int) -> None:
    """Trip과 그 run·snapshot·견적·알림을 함께 지운다 (FK ON DELETE CASCADE)."""
    with get_conn() as conn:
        conn.cursor().execute("DELETE FROM trips WHERE id = %s", (trip_id,))


def update_trip(
    trip_id: int,
    *,
    prefs: Preferences | None = None,
    tracking: bool | None = None,
    target_price: int | None = None,
    clear_target: bool = False,
) -> None:
    sets: list[str] = []
    params: list[object] = []

    if prefs is not None:
        sets.append("prefs = %s")
        params.append(json.dumps(prefs.to_dict()))
    if tracking is not None:
        sets.append("tracking = %s")
        params.append(tracking)
    if clear_target:
        sets.append("target_price = NULL")
    elif target_price is not None:
        sets.append("target_price = %s")
        params.append(target_price)

    if not sets:
        return

    params.append(trip_id)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE trips SET {', '.join(sets)} WHERE id = %s",
            params,
        )


def enqueue_run(trip_id: int, trigger: Literal["schedule", "manual"]) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO search_runs (trip_id, trigger)
            VALUES (%s, %s)
            RETURNING id
            """,
            (trip_id, trigger),
        )
        run_id: int = cur.fetchone()[0]
        return run_id


def get_run(run_id: int) -> Run | None:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM search_runs WHERE id = %s", (run_id,))
        row = cur.fetchone()
        return _row_to_run(row) if row else None


def latest_run(trip_id: int) -> Run | None:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT * FROM search_runs
            WHERE trip_id = %s
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (trip_id,),
        )
        row = cur.fetchone()
        return _row_to_run(row) if row else None


def latest_runs(trip_ids: list[int]) -> dict[int, Run | None]:
    """Trip별 최신 run (없으면 None) — latest_run을 Trip마다 부르지 않게 한 번에 읽는다."""
    runs: dict[int, Run | None] = {tid: None for tid in trip_ids}
    if not trip_ids:
        return runs
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT DISTINCT ON (trip_id) * FROM search_runs
            WHERE trip_id = ANY(%s)
            ORDER BY trip_id, requested_at DESC
            """,
            (list(trip_ids),),
        )
        for row in cur.fetchall():
            runs[row["trip_id"]] = _row_to_run(row)
    return runs


def claim_next_run() -> Run | None:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            UPDATE search_runs
            SET status = 'running', started_at = now()
            WHERE id = (
                SELECT id FROM search_runs
                WHERE status = 'queued'
                ORDER BY requested_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *
            """
        )
        row = cur.fetchone()
        return _row_to_run(row) if row else None


def finish_run(run_id: int, status: Literal["done", "error"]) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE search_runs
            SET status = %s, finished_at = now()
            WHERE id = %s
            """,
            (status, run_id),
        )


def expire_stuck_runs(older_than: timedelta) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE search_runs
            SET status = 'error', finished_at = now()
            WHERE status = 'running' AND started_at < now() - %s
            """,
            (older_than,),
        )
        return cur.rowcount


def open_run_ids(trip_id: int) -> set[int]:
    """아직 끝나지 않은(queued/running) run id 전부."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM search_runs WHERE trip_id = %s AND status IN ('queued', 'running')",
            (trip_id,),
        )
        return {row[0] for row in cur.fetchall()}


def has_open_run(trip_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM search_runs
            WHERE trip_id = %s AND status IN ('queued', 'running')
            LIMIT 1
            """,
            (trip_id,),
        )
        return cur.fetchone() is not None


# 대량 조회(load_snapshots)는 dict 행 대신 튜플로 읽는다 — 행마다 dict를 만드는 비용이 응답 시간의 큰 몫이었다.
_LEG_COLS = (
    "snapshot_id, flight_key, airline_iata, airline_name, flight_numbers, dep_airport, arr_airport, "
    "dep_time, arr_time, duration_min, stops, price, booking_url, search_url, "
    "cond_price, cond_label, cond_booking_url"
)
_RT_COLS = "snapshot_id, airline_iata, out_flight_key, total_price, cond_total_price, cond_label"
_SNAPSHOT_COLS = "id, run_id, trip_id, provider, kind, direction, date, status, card_count, observed_at, error"


def _leg_from_tuple(r: tuple) -> LegQuote:
    return LegQuote(
        flight_key=r[1],
        airline_iata=r[2],
        airline_name=r[3],
        flight_numbers=list(r[4]) if r[4] else [],
        dep_airport=r[5],
        arr_airport=r[6],
        dep_time=r[7],
        arr_time=r[8],
        duration_min=r[9],
        stops=r[10],
        price=r[11],
        booking_url=r[12],
        search_url=r[13],
        cond_price=r[14],
        cond_label=r[15],
        cond_booking_url=r[16],
    )


def _rt_from_tuple(r: tuple) -> RtQuote:
    return RtQuote(airline_iata=r[1], out_flight_key=r[2], total_price=r[3], cond_total_price=r[4], cond_label=r[5])


def save_snapshot(
    run_id: int,
    trip_id: int,
    provider: str,
    kind: str,
    direction: str | None,
    date_: date,
    result: ProviderResult,
    observed_at: datetime,
) -> int:
    card_count = len(result.legs) + len(result.rts)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO snapshots
                (run_id, trip_id, provider, kind, direction, date, status, card_count, observed_at, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                run_id,
                trip_id,
                provider,
                kind,
                direction,
                date_,
                result.status,
                card_count,
                observed_at,
                result.error,
            ),
        )
        snapshot_id: int = cur.fetchone()[0]

        if result.legs:
            execute_values(
                cur,
                """
                INSERT INTO leg_quotes
                    (snapshot_id, flight_key, airline_iata, airline_name, flight_numbers,
                     dep_airport, arr_airport, dep_time, arr_time, duration_min, stops,
                     price, booking_url, search_url,
                     cond_price, cond_label, cond_booking_url)
                VALUES %s
                """,
                [
                    (
                        snapshot_id,
                        leg.flight_key,
                        leg.airline_iata,
                        leg.airline_name,
                        leg.flight_numbers,
                        leg.dep_airport,
                        leg.arr_airport,
                        leg.dep_time,
                        leg.arr_time,
                        leg.duration_min,
                        leg.stops,
                        leg.price,
                        leg.booking_url,
                        leg.search_url,
                        leg.cond_price,
                        leg.cond_label,
                        leg.cond_booking_url,
                    )
                    for leg in result.legs
                ],
            )

        if result.rts:
            execute_values(
                cur,
                """
                INSERT INTO rt_quotes
                    (snapshot_id, airline_iata, out_flight_key, total_price,
                     cond_total_price, cond_label)
                VALUES %s
                """,
                [
                    (
                        snapshot_id,
                        rt.airline_iata,
                        rt.out_flight_key,
                        rt.total_price,
                        rt.cond_total_price,
                        rt.cond_label,
                    )
                    for rt in result.rts
                ],
            )

        return snapshot_id


def _load_snapshots(where: str, params: tuple) -> list[Snapshot]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT {_SNAPSHOT_COLS} FROM snapshots WHERE {where} ORDER BY observed_at ASC, id ASC", params)
        snapshot_rows = cur.fetchall()
        snapshot_ids = [row[0] for row in snapshot_rows]

        legs_by_snapshot: dict[int, list[LegQuote]] = {sid: [] for sid in snapshot_ids}
        rts_by_snapshot: dict[int, list[RtQuote]] = {sid: [] for sid in snapshot_ids}

        if snapshot_ids:
            cur.execute(
                f"SELECT {_LEG_COLS} FROM leg_quotes WHERE snapshot_id = ANY(%s) ORDER BY id ASC",
                (snapshot_ids,),
            )
            for r in cur.fetchall():
                legs_by_snapshot[r[0]].append(_leg_from_tuple(r))

            cur.execute(
                f"SELECT {_RT_COLS} FROM rt_quotes WHERE snapshot_id = ANY(%s) ORDER BY id ASC",
                (snapshot_ids,),
            )
            for r in cur.fetchall():
                rts_by_snapshot[r[0]].append(_rt_from_tuple(r))

        return [
            Snapshot(
                id=r[0],
                run_id=r[1],
                trip_id=r[2],
                provider=r[3],
                kind=r[4],
                direction=r[5],
                date=r[6],
                status=r[7],
                card_count=r[8],
                observed_at=r[9],
                error=r[10],
                legs=legs_by_snapshot[r[0]],
                rts=rts_by_snapshot[r[0]],
            )
            for r in snapshot_rows
        ]


def load_snapshots(trip_id: int, since: datetime | None = None) -> list[Snapshot]:
    if since is not None:
        return _load_snapshots("trip_id = %s AND observed_at >= %s", (trip_id, since))
    return _load_snapshots("trip_id = %s", (trip_id,))


def load_snapshots_for_trips(trip_ids: list[int]) -> dict[int, list[Snapshot]]:
    """여러 Trip의 스냅샷을 쿼리 3개로 한 번에 읽는다 (대시보드용). 각 Trip은 load_snapshots와 같은 결과."""
    if not trip_ids:
        return {}
    by_trip: dict[int, list[Snapshot]] = {tid: [] for tid in trip_ids}
    for snap in _load_snapshots("trip_id = ANY(%s)", (list(trip_ids),)):
        by_trip[snap.trip_id].append(snap)
    return by_trip


def record_alert(trip_id: int | None, kind: str, price: int | None) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO alerts (trip_id, kind, price) VALUES (%s, %s, %s)",
            (trip_id, kind, price),
        )


def last_alert(trip_id: int | None, kind: str) -> tuple[int | None, datetime] | None:
    with get_conn() as conn:
        cur = conn.cursor()
        if trip_id is None:
            cur.execute(
                """
                SELECT price, sent_at FROM alerts
                WHERE trip_id IS NULL AND kind = %s
                ORDER BY sent_at DESC
                LIMIT 1
                """,
                (kind,),
            )
        else:
            cur.execute(
                """
                SELECT price, sent_at FROM alerts
                WHERE trip_id = %s AND kind = %s
                ORDER BY sent_at DESC
                LIMIT 1
                """,
                (trip_id, kind),
            )
        row = cur.fetchone()
        return (row[0], row[1]) if row else None


def recent_runs(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT sr.id, sr.trip_id, t.destination, sr.trigger, sr.status,
                   sr.requested_at, sr.started_at, sr.finished_at
            FROM search_runs sr
            JOIN trips t ON t.id = sr.trip_id
            ORDER BY sr.requested_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        run_rows = cur.fetchall()
        run_ids = [row["id"] for row in run_rows]

        snapshots_by_run: dict[int, list[dict]] = {rid: [] for rid in run_ids}
        if run_ids:
            cur.execute(
                """
                SELECT run_id, provider, kind, direction, status, error
                FROM snapshots
                WHERE run_id = ANY(%s)
                ORDER BY id ASC
                """,
                (run_ids,),
            )
            for snap_row in cur.fetchall():
                snapshots_by_run[snap_row["run_id"]].append(
                    {
                        "provider": snap_row["provider"],
                        "kind": snap_row["kind"],
                        "direction": snap_row["direction"],
                        "status": snap_row["status"],
                        "error": snap_row["error"],
                    }
                )

        runs: list[dict] = []
        for row in run_rows:
            runs.append(
                {
                    "id": row["id"],
                    "trip_id": row["trip_id"],
                    "destination": row["destination"],
                    "trigger": row["trigger"],
                    "status": row["status"],
                    "requested_at": row["requested_at"],
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                    "snapshots": snapshots_by_run[row["id"]],
                }
            )
        return runs


def provider_stats(days: int = 7) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT
                provider,
                (observed_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'ok') AS ok,
                COUNT(*) FILTER (WHERE status = 'empty') AS empty,
                COUNT(*) FILTER (WHERE status = 'blocked') AS blocked,
                COUNT(*) FILTER (WHERE status = 'error') AS error
            FROM snapshots
            WHERE observed_at >= now() - (%s || ' days')::interval
            GROUP BY provider, day
            ORDER BY day ASC, provider ASC
            """,
            (days,),
        )
        return [dict(row) for row in cur.fetchall()]
