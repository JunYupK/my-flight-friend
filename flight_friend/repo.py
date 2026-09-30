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


def _row_to_leg(row: RealDictRow) -> LegQuote:
    return LegQuote(
        flight_key=row["flight_key"],
        airline_iata=row["airline_iata"],
        airline_name=row["airline_name"],
        flight_numbers=list(row["flight_numbers"]) if row["flight_numbers"] else [],
        dep_airport=row["dep_airport"],
        arr_airport=row["arr_airport"],
        dep_time=row["dep_time"],
        arr_time=row["arr_time"],
        duration_min=row["duration_min"],
        stops=row["stops"],
        price=row["price"],
        booking_url=row["booking_url"],
        search_url=row["search_url"],
        cond_price=row["cond_price"],
        cond_label=row["cond_label"],
        cond_booking_url=row["cond_booking_url"],
    )


def _row_to_rt(row: RealDictRow) -> RtQuote:
    return RtQuote(
        airline_iata=row["airline_iata"],
        out_flight_key=row["out_flight_key"],
        total_price=row["total_price"],
        cond_total_price=row["cond_total_price"],
        cond_label=row["cond_label"],
    )


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


def load_snapshots(trip_id: int, since: datetime | None = None) -> list[Snapshot]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if since is not None:
            cur.execute(
                """
                SELECT * FROM snapshots
                WHERE trip_id = %s AND observed_at >= %s
                ORDER BY observed_at ASC
                """,
                (trip_id, since),
            )
        else:
            cur.execute(
                """
                SELECT * FROM snapshots
                WHERE trip_id = %s
                ORDER BY observed_at ASC
                """,
                (trip_id,),
            )
        snapshot_rows = cur.fetchall()
        snapshot_ids = [row["id"] for row in snapshot_rows]

        legs_by_snapshot: dict[int, list[LegQuote]] = {sid: [] for sid in snapshot_ids}
        rts_by_snapshot: dict[int, list[RtQuote]] = {sid: [] for sid in snapshot_ids}

        if snapshot_ids:
            cur.execute(
                "SELECT * FROM leg_quotes WHERE snapshot_id = ANY(%s) ORDER BY id ASC",
                (snapshot_ids,),
            )
            for leg_row in cur.fetchall():
                legs_by_snapshot[leg_row["snapshot_id"]].append(_row_to_leg(leg_row))

            cur.execute(
                "SELECT * FROM rt_quotes WHERE snapshot_id = ANY(%s) ORDER BY id ASC",
                (snapshot_ids,),
            )
            for rt_row in cur.fetchall():
                rts_by_snapshot[rt_row["snapshot_id"]].append(_row_to_rt(rt_row))

        snapshots: list[Snapshot] = []
        for row in snapshot_rows:
            snapshots.append(
                Snapshot(
                    id=row["id"],
                    run_id=row["run_id"],
                    trip_id=row["trip_id"],
                    provider=row["provider"],
                    kind=row["kind"],
                    direction=row["direction"],
                    date=row["date"],
                    status=row["status"],
                    card_count=row["card_count"],
                    observed_at=row["observed_at"],
                    error=row["error"],
                    legs=legs_by_snapshot[row["id"]],
                    rts=rts_by_snapshot[row["id"]],
                )
            )
        return snapshots


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
                SELECT run_id, provider, kind, direction, status
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
