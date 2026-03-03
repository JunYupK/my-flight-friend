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
                checked_at       TEXT
            )
        """)

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

        # v_best_observed 뷰 (최저 관측 + 최근 관측)
        # destination_name을 GROUP BY에 포함 (표준 SQL 준수)
        conn.execute("""
            CREATE VIEW IF NOT EXISTS v_best_observed AS
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
                MIN(price)      AS min_price,
                MAX(checked_at) AS last_checked_at
            FROM price_history
            GROUP BY
                destination, destination_name,
                departure_date, return_date, stay_nights,
                source, out_airline, in_airline, is_mixed_airline
        """)


def save_prices(offers: list[dict]):
    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO price_history
            (source, trip_type, origin, destination, destination_name,
             departure_date, return_date, stay_nights, price, currency,
             out_airline, in_airline, is_mixed_airline, checked_at)
            VALUES
            (:source, :trip_type, :origin, :destination, :destination_name,
             :departure_date, :return_date, :stay_nights, :price, :currency,
             :out_airline, :in_airline, :is_mixed_airline, :checked_at)
        """, offers)


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
