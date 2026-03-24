# flight_monitor/storage.py

import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from flight_monitor.config import KST

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from .config import SEARCH_CONFIG

load_dotenv()

_DSN = os.environ["DATABASE_URL"]


@contextmanager
def get_conn():
    conn = psycopg2.connect(_DSN)
    conn.cursor().execute("SET TIME ZONE 'Asia/Seoul'")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id               SERIAL PRIMARY KEY,
                source           TEXT,
                trip_type        TEXT,
                origin           TEXT,
                destination      TEXT,
                destination_name TEXT,
                departure_date   TEXT,
                return_date      TEXT,
                stay_nights      INTEGER,
                price            REAL,
                currency         TEXT,
                out_airline      TEXT,
                in_airline       TEXT,
                is_mixed_airline INTEGER,
                checked_at       TIMESTAMP,
                out_dep_time     TEXT,
                out_arr_time     TEXT,
                out_duration_min INTEGER,
                out_stops        INTEGER,
                in_dep_time      TEXT,
                in_arr_time      TEXT,
                in_duration_min  INTEGER,
                in_stops         INTEGER,
                out_arr_airport  TEXT,
                in_dep_airport   TEXT,
                out_url          TEXT,
                in_url           TEXT,
                out_price        REAL,
                in_price         REAL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS alert_state (
                alert_key    TEXT PRIMARY KEY,
                last_price   REAL,
                last_sent_at TEXT
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_dest_dep_ret
            ON price_history(destination, departure_date, return_date)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_checked_at
            ON price_history(checked_at)
        """)

        # checked_at TEXT → TIMESTAMP 마이그레이션 (기존 테이블)
        cur.execute("SAVEPOINT pre_ts")
        try:
            cur.execute("""
                ALTER TABLE price_history
                ALTER COLUMN checked_at TYPE TIMESTAMP USING checked_at::TIMESTAMP
            """)
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT pre_ts")
        else:
            cur.execute("RELEASE SAVEPOINT pre_ts")

        # 기존 테이블에 컬럼 추가 (없을 때만)
        for col, col_type in [
            ("trip_type", "TEXT"), ("out_arr_airport", "TEXT"),
            ("in_dep_airport", "TEXT"), ("out_url", "TEXT"), ("in_url", "TEXT"),
            ("out_price", "REAL"), ("in_price", "REAL"),
        ]:
            cur.execute("SAVEPOINT pre_alter")
            try:
                cur.execute(f"ALTER TABLE price_history ADD COLUMN {col} {col_type}")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT pre_alter")
            else:
                cur.execute("RELEASE SAVEPOINT pre_alter")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key   TEXT PRIMARY KEY,
                value JSONB NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS airports (
                code    TEXT PRIMARY KEY,
                name    TEXT NOT NULL,
                tfs_out TEXT,
                tfs_in  TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS collection_runs (
                id             SERIAL PRIMARY KEY,
                started_at     TIMESTAMPTZ NOT NULL,
                finished_at    TIMESTAMPTZ,
                status         TEXT NOT NULL DEFAULT 'running',
                google_count   INTEGER DEFAULT 0,
                total_saved    INTEGER DEFAULT 0,
                alerts_sent    INTEGER DEFAULT 0,
                error_log      TEXT,
                duration_sec   REAL
            )
        """)

        # 기존 테이블에서 fsc_count 컬럼 제거 (있을 때만)
        cur.execute("SAVEPOINT pre_drop_fsc")
        try:
            cur.execute("ALTER TABLE collection_runs DROP COLUMN fsc_count")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT pre_drop_fsc")
        else:
            cur.execute("RELEASE SAVEPOINT pre_drop_fsc")

        cur.execute("DROP VIEW IF EXISTS v_best_observed")
        cur.execute("""
            CREATE VIEW v_best_observed AS
            SELECT
                origin,
                destination,
                destination_name,
                departure_date,
                return_date,
                stay_nights,
                trip_type,
                source,
                out_airline,
                in_airline,
                is_mixed_airline,
                out_dep_time,
                out_arr_time,
                out_duration_min,
                out_stops,
                in_dep_time,
                in_arr_time,
                in_duration_min,
                in_stops,
                out_arr_airport,
                in_dep_airport,
                MIN(price)      AS min_price,
                MAX(checked_at) AS last_checked_at,
                MAX(out_url)    AS out_url,
                MAX(in_url)     AS in_url,
                MIN(out_price)  AS out_price,
                MIN(in_price)   AS in_price
            FROM price_history
            GROUP BY
                origin, destination, destination_name,
                departure_date, return_date, stay_nights,
                trip_type,
                source, out_airline, in_airline, is_mixed_airline,
                out_dep_time, out_arr_time, out_duration_min, out_stops,
                in_dep_time, in_arr_time, in_duration_min, in_stops,
                out_arr_airport, in_dep_airport
        """)


def get_airports() -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT code, name, tfs_out, tfs_in FROM airports ORDER BY code")
        return [dict(r) for r in cur.fetchall()]


def save_prices(offers: list[dict]):
    rows = [
        (
            o["source"], o["trip_type"], o["origin"], o["destination"], o["destination_name"],
            o["departure_date"], o["return_date"], o["stay_nights"], o["price"], o["currency"],
            o["out_airline"], o["in_airline"], int(o["is_mixed_airline"]), o["checked_at"],
            o.get("out_dep_time"), o.get("out_arr_time"), o.get("out_duration_min"), o.get("out_stops"),
            o.get("in_dep_time"),  o.get("in_arr_time"),  o.get("in_duration_min"),  o.get("in_stops"),
            o.get("out_arr_airport"), o.get("in_dep_airport"),
            o.get("out_url"), o.get("in_url"),
            o.get("out_price"), o.get("in_price"),
        )
        for o in offers
    ]
    with get_conn() as conn:
        cur = conn.cursor()
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO price_history
            (source, trip_type, origin, destination, destination_name,
             departure_date, return_date, stay_nights, price, currency,
             out_airline, in_airline, is_mixed_airline, checked_at,
             out_dep_time, out_arr_time, out_duration_min, out_stops,
             in_dep_time,  in_arr_time,  in_duration_min,  in_stops,
             out_arr_airport, in_dep_airport,
             out_url, in_url,
             out_price, in_price)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, rows)


def make_alert_key(offer: dict) -> str:
    return "|".join([
        offer["destination"],
        offer["departure_date"],
        offer["return_date"],
        offer["out_airline"],
        offer["in_airline"],
        str(int(offer["is_mixed_airline"])),
    ])


def should_notify(offer: dict) -> bool:
    key = make_alert_key(offer)
    cooldown_h = SEARCH_CONFIG["alert_cooldown_hours"]
    drop_krw   = SEARCH_CONFIG["alert_realert_drop_krw"]

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT last_price, last_sent_at FROM alert_state WHERE alert_key = %s", (key,)
        )
        row = cur.fetchone()

    if row is None:
        return True

    last_price   = row["last_price"]
    last_sent_at = datetime.fromisoformat(row["last_sent_at"])
    if last_sent_at.tzinfo is None:
        last_sent_at = last_sent_at.replace(tzinfo=KST)
    now          = datetime.now(KST)

    cooldown_passed = (now - last_sent_at) >= timedelta(hours=cooldown_h)
    price_dropped   = offer["price"] <= last_price - drop_krw

    return cooldown_passed or price_dropped


def record_alert(offer: dict):
    key = make_alert_key(offer)
    now_str = datetime.now(KST).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO alert_state (alert_key, last_price, last_sent_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (alert_key) DO UPDATE SET
                last_price   = EXCLUDED.last_price,
                last_sent_at = EXCLUDED.last_sent_at
        """, (key, offer["price"], now_str))


def start_collection_run() -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO collection_runs (started_at) VALUES (%s) RETURNING id",
            (datetime.now(KST),),
        )
        return cur.fetchone()[0]


def finish_collection_run(
    run_id: int,
    *,
    status: str,
    google_count: int = 0,
    total_saved: int = 0,
    alerts_sent: int = 0,
    error_log: str | None = None,
):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE collection_runs
            SET finished_at  = %s,
                status       = %s,
                google_count = %s,
                total_saved  = %s,
                alerts_sent  = %s,
                error_log    = %s,
                duration_sec = EXTRACT(EPOCH FROM (%s::timestamptz - started_at))
            WHERE id = %s
        """, (datetime.now(KST), status, google_count, total_saved, alerts_sent, error_log, datetime.now(KST), run_id))


def get_recent_runs(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, started_at, finished_at, status,
                   google_count, total_saved, alerts_sent,
                   duration_sec, error_log IS NOT NULL AS has_error
            FROM collection_runs
            ORDER BY started_at DESC
            LIMIT %s
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]


def get_run_detail(run_id: int) -> dict | None:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM collection_runs WHERE id = %s", (run_id,))
        row = cur.fetchone()
        return dict(row) if row else None
