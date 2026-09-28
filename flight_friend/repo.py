# flight_friend/repo.py

import json
from datetime import date, timedelta
from typing import Literal

from psycopg2.extras import RealDictCursor, RealDictRow

from flight_friend.db import get_conn
from flight_friend.types import Preferences, Run, Trip


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
