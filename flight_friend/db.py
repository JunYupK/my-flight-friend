# flight_friend/db.py

import os
import threading
from collections.abc import Generator
from contextlib import contextmanager

import psycopg2
import psycopg2.extensions
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

_DSN = os.environ["DATABASE_URL"]
_POOL_MAX = 10

# 요청마다 새로 접속하던 비용(~7ms)을 없애는 프로세스 단위 풀. 처음 쓸 때 만든다.
# psycopg2 풀은 고갈되면 기다리지 않고 PoolError를 내므로 세마포어로 빈 연결을 기다린다.
_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()
_slots = threading.BoundedSemaphore(_POOL_MAX)


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    1, _POOL_MAX, _DSN, options="-c timezone=Asia/Seoul"
                )
    return _pool


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    _slots.acquire()
    pool = _get_pool()
    conn = pool.getconn()
    broken = False
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except psycopg2.Error:
            broken = True  # 끊긴 연결은 풀에 돌려놓지 않는다
        raise
    finally:
        pool.putconn(conn, close=broken or conn.closed != 0)
        _slots.release()


def init_schema() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        # app + worker가 동시에 기동해도 CREATE ... IF NOT EXISTS 경합이 나지 않도록 직렬화 (트랜잭션 종료 시 해제)
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('flight_friend.init_schema'))")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id SERIAL PRIMARY KEY,
                origin TEXT NOT NULL DEFAULT 'ICN',
                destination TEXT NOT NULL,
                out_date DATE NOT NULL,
                ret_date DATE NOT NULL,
                adults INT NOT NULL DEFAULT 1,
                cabin TEXT NOT NULL DEFAULT 'economy',
                prefs JSONB NOT NULL DEFAULT '{}',
                target_price INT,
                tracking BOOL NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                archived_at TIMESTAMPTZ
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS search_runs (
                id SERIAL PRIMARY KEY,
                trip_id INT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                trigger TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_runs_status_requested_at
                ON search_runs (status, requested_at)
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id SERIAL PRIMARY KEY,
                run_id INT NOT NULL REFERENCES search_runs(id) ON DELETE CASCADE,
                trip_id INT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                kind TEXT NOT NULL,
                direction TEXT,
                date DATE NOT NULL,
                status TEXT NOT NULL,
                card_count INT NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                error TEXT
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_trip_id_observed_at
                ON snapshots (trip_id, observed_at)
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS leg_quotes (
                id SERIAL PRIMARY KEY,
                snapshot_id INT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
                flight_key TEXT NOT NULL,
                airline_iata TEXT NOT NULL,
                airline_name TEXT NOT NULL,
                flight_numbers TEXT[],
                dep_airport TEXT NOT NULL,
                arr_airport TEXT NOT NULL,
                dep_time TEXT NOT NULL,
                arr_time TEXT NOT NULL,
                duration_min INT,
                stops INT,
                price INT NOT NULL,
                booking_url TEXT,
                search_url TEXT
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_leg_quotes_snapshot_id
                ON leg_quotes (snapshot_id)
        """)
        cur.execute("ALTER TABLE leg_quotes ADD COLUMN IF NOT EXISTS cond_price INT")
        cur.execute("ALTER TABLE leg_quotes ADD COLUMN IF NOT EXISTS cond_label TEXT")
        cur.execute("ALTER TABLE leg_quotes ADD COLUMN IF NOT EXISTS cond_booking_url TEXT")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS rt_quotes (
                id SERIAL PRIMARY KEY,
                snapshot_id INT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
                airline_iata TEXT NOT NULL,
                out_flight_key TEXT NOT NULL,
                total_price INT NOT NULL
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_rt_quotes_snapshot_id
                ON rt_quotes (snapshot_id)
        """)
        cur.execute("ALTER TABLE rt_quotes ADD COLUMN IF NOT EXISTS cond_total_price INT")
        cur.execute("ALTER TABLE rt_quotes ADD COLUMN IF NOT EXISTS cond_label TEXT")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                trip_id INT REFERENCES trips(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                price INT,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_trip_id_kind_sent_at
                ON alerts (trip_id, kind, sent_at)
        """)


def schema_ready() -> bool:
    """V2 스키마가 존재하고 DB에 닿는지. 어떤 실패든 False."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT to_regclass('public.trips') IS NOT NULL")
            row = cur.fetchone()
            return bool(row and row[0])
    except Exception:  # noqa: BLE001 — 헬스체크는 예외 대신 False
        return False
