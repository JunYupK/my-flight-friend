# flight_monitor/storage.py

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from .config import SEARCH_CONFIG

DB_PATH = "data/flights.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        # 관측값 누적
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
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
                checked_at       TEXT,
                out_dep_time     TEXT,
                out_arr_time     TEXT,
                out_duration_min INTEGER,
                out_stops        INTEGER,
                in_dep_time      TEXT,
                in_arr_time      TEXT,
                in_duration_min  INTEGER,
                in_stops         INTEGER
            )
        """)

        # 기존 DB 마이그레이션: 신규 컬럼 추가 (이미 있으면 무시)
        new_cols = [
            ("out_dep_time",     "TEXT"),
            ("out_arr_time",     "TEXT"),
            ("out_duration_min", "INTEGER"),
            ("out_stops",        "INTEGER"),
            ("in_dep_time",      "TEXT"),
            ("in_arr_time",      "TEXT"),
            ("in_duration_min",  "INTEGER"),
            ("in_stops",         "INTEGER"),
        ]
        for col, col_type in new_cols:
            try:
                conn.execute(f"ALTER TABLE price_history ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # 컬럼이 이미 존재함

        # alert_state (쿨다운/재알림 기준)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_state (
                alert_key    TEXT PRIMARY KEY,
                last_price   REAL,
                last_sent_at TEXT
            )
        """)

        # 인덱스
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_dest_dep_ret
            ON price_history(destination, departure_date, return_date)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_checked_at
            ON price_history(checked_at)
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_state_key
            ON alert_state(alert_key)
        """)

        # v_best_observed 뷰 — 스키마 변경 시 항상 재생성
        conn.execute("DROP VIEW IF EXISTS v_best_observed")
        conn.execute("""
            CREATE VIEW v_best_observed AS
            SELECT
                destination,
                destination_name,
                departure_date,
                return_date,
                stay_nights,
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
                MIN(price)      AS min_price,
                MAX(checked_at) AS last_checked_at
            FROM price_history
            GROUP BY
                destination, destination_name,
                departure_date, return_date, stay_nights,
                source, out_airline, in_airline, is_mixed_airline,
                out_dep_time, out_arr_time, out_duration_min, out_stops,
                in_dep_time, in_arr_time, in_duration_min, in_stops
        """)


def save_prices(offers: list[dict]):
    rows = [
        (
            o["source"], o["trip_type"], o["origin"], o["destination"], o["destination_name"],
            o["departure_date"], o["return_date"], o["stay_nights"], o["price"], o["currency"],
            o["out_airline"], o["in_airline"], o["is_mixed_airline"], o["checked_at"],
            o.get("out_dep_time"), o.get("out_arr_time"), o.get("out_duration_min"), o.get("out_stops"),
            o.get("in_dep_time"),  o.get("in_arr_time"),  o.get("in_duration_min"),  o.get("in_stops"),
        )
        for o in offers
    ]
    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO price_history
            (source, trip_type, origin, destination, destination_name,
             departure_date, return_date, stay_nights, price, currency,
             out_airline, in_airline, is_mixed_airline, checked_at,
             out_dep_time, out_arr_time, out_duration_min, out_stops,
             in_dep_time,  in_arr_time,  in_duration_min,  in_stops)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)


def make_alert_key(offer: dict) -> str:
    """
    source 제외 — 같은 노선/날짜면 소스 무관하게 동일 키 사용
    (source 포함 시 동일 딜을 두 채널에서 중복 알림하는 문제 발생)
    """
    return "|".join([
        offer["destination"],
        offer["departure_date"],
        offer["return_date"],
        offer["out_airline"],
        offer["in_airline"],
        str(int(offer["is_mixed_airline"])),
    ])


def should_notify(offer: dict) -> bool:
    """쿨다운 + 재알림 조건 판단"""
    key = make_alert_key(offer)
    cooldown_h = SEARCH_CONFIG["alert_cooldown_hours"]
    drop_krw   = SEARCH_CONFIG["alert_realert_drop_krw"]

    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_price, last_sent_at FROM alert_state WHERE alert_key = ?", (key,)
        ).fetchone()

    if row is None:
        return True  # 첫 알림

    last_price   = row["last_price"]
    last_sent_at = datetime.fromisoformat(row["last_sent_at"])
    now          = datetime.now()

    cooldown_passed = (now - last_sent_at) >= timedelta(hours=cooldown_h)
    price_dropped   = offer["price"] <= last_price - drop_krw

    return cooldown_passed or price_dropped


def record_alert(offer: dict):
    key = make_alert_key(offer)
    # datetime.now().isoformat() 사용 — should_notify의 datetime.now()와 동일 기준
    # SQLite datetime('now')는 UTC이므로 로컬 시간(KST)과 비교 시 9시간 오차 발생
    now_str = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO alert_state (alert_key, last_price, last_sent_at)
            VALUES (?, ?, ?)
            ON CONFLICT(alert_key) DO UPDATE SET
                last_price   = excluded.last_price,
                last_sent_at = excluded.last_sent_at
        """, (key, offer["price"], now_str))
