# flight_monitor/storage.py

import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from flight_monitor.config import KST

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from .config import ORIGIN, SEARCH_CONFIG
from .offer_utils import combine_roundtrips

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

        # 배포가 장기 수집 run과 겹치면 collector가 flight_legs/deals 등에 계속 쓰기
        # 락(ROW EXCLUSIVE)을 잡고 있어, init_db의 DDL(CREATE INDEX=SHARE, ALTER=
        # ACCESS EXCLUSIVE)이 그 뒤에서 무한 대기 → app startup이 영구 hang → 헬스체크
        # 실패로 배포가 깨진다. 락을 빨리 못 잡으면 포기하게 해 startup을 막지 않는다.
        # (이미 프로비저닝된 DB에선 아래 DDL이 전부 IF [NOT] EXISTS no-op이라 스킵해도
        #  안전하고, 신규 DB는 collector가 없어 경합 자체가 없다.) SET LOCAL이라 이 트랜잭션
        # 한정으로만 적용된다.
        cur.execute("SET LOCAL lock_timeout = '10s'")

        # ALTER COLUMN checked_at가 뷰 의존성으로 실패하지 않도록 먼저 drop
        cur.execute("DROP VIEW IF EXISTS v_best_observed")

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
        # advance 쿼리: destination + trip_type 필터 후 departure_date/checked_at 집계
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_advance
            ON price_history(destination, trip_type, departure_date, checked_at)
            WHERE price > 0
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
            cur.execute(f"ALTER TABLE price_history ADD COLUMN IF NOT EXISTS {col} {col_type}")

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

        # ── flight_legs: 편도 항공편 개별 저장 ──
        cur.execute("""
            CREATE TABLE IF NOT EXISTS flight_legs (
                id               SERIAL PRIMARY KEY,
                source           TEXT NOT NULL,
                origin           TEXT NOT NULL,
                destination      TEXT NOT NULL,
                destination_name TEXT,
                date             TEXT NOT NULL,
                direction        TEXT NOT NULL,
                airline          TEXT,
                dep_time         TEXT,
                arr_time         TEXT,
                duration_min     INTEGER,
                stops            INTEGER,
                dep_airport      TEXT,
                arr_airport      TEXT,
                price            REAL NOT NULL,
                booking_url      TEXT,
                search_url       TEXT,
                checked_at       TIMESTAMP NOT NULL
            )
        """)
        # source를 unique key에 포함 — source별 독립 row 유지, 추후 source 필터링 지원
        # 기존 인덱스 drop 후 재생성 (IF NOT EXISTS는 컬럼 변경 시 재생성 안 함)
        cur.execute("DROP INDEX IF EXISTS uq_flight_legs_identity")
        cur.execute("""
            CREATE UNIQUE INDEX uq_flight_legs_identity
            ON flight_legs (
                source, origin, destination, date, direction,
                COALESCE(airline, ''), COALESCE(dep_time, ''),
                COALESCE(arr_time, ''), COALESCE(stops, -1)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_flight_legs_out
            ON flight_legs (destination, date) WHERE direction = 'out'
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_flight_legs_in
            ON flight_legs (destination, date) WHERE direction = 'in'
        """)
        # deals 쿼리용: checked_at 필터 + destination/date 조인
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_flight_legs_out_checked
            ON flight_legs (checked_at, destination, date) WHERE direction = 'out'
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_flight_legs_in_checked
            ON flight_legs (checked_at, destination, date) WHERE direction = 'in'
        """)

        # flight_legs에 best_source 컬럼 추가 (없을 때만)
        cur.execute("ALTER TABLE flight_legs ADD COLUMN IF NOT EXISTS best_source TEXT")

        # ── raw_legs: 수집 원본 로그 (append-only) ──
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw_legs (
                id               SERIAL PRIMARY KEY,
                source           TEXT NOT NULL,
                origin           TEXT NOT NULL,
                destination      TEXT NOT NULL,
                destination_name TEXT,
                date             TEXT NOT NULL,
                direction        TEXT NOT NULL,
                airline          TEXT,
                dep_time         TEXT,
                arr_time         TEXT,
                duration_min     INTEGER,
                stops            INTEGER,
                dep_airport      TEXT,
                arr_airport      TEXT,
                price            REAL NOT NULL,
                currency         TEXT DEFAULT 'KRW',
                booking_url      TEXT,
                search_url       TEXT,
                extra            JSONB,
                collected_at     TIMESTAMP NOT NULL
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_raw_legs_dest_date
            ON raw_legs (destination, date, direction)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_raw_legs_collected_at
            ON raw_legs (collected_at)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_raw_legs_source
            ON raw_legs (source, destination, date, direction)
        """)

        # ── deals: 왕복 조합 사전계산(materialized) — /api/results 읽기 최적화 ──
        # 수집 시 combine_roundtrips()로 이미 만든 왕복 offer를 그대로 저장.
        # 읽기 경로가 flight_legs 카테시안 조인을 매번 돌리던 비용을 제거한다.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id               SERIAL PRIMARY KEY,
                origin           TEXT NOT NULL,
                destination      TEXT NOT NULL,
                destination_name TEXT,
                departure_date   TEXT NOT NULL,
                return_date      TEXT NOT NULL,
                stay_nights      INTEGER,
                trip_type        TEXT,
                source           TEXT NOT NULL,
                out_airline      TEXT,
                in_airline       TEXT,
                is_mixed_airline INTEGER,
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
                in_price         REAL,
                min_price        REAL NOT NULL,
                last_checked_at  TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_deals_dest_dep_price
            ON deals (destination, departure_date, min_price)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_deals_source_dest
            ON deals (source, destination)
        """)

        # ── price_events: 가격 변동 이력 (event-sourced) ──
        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_events (
                id           SERIAL PRIMARY KEY,
                destination  TEXT NOT NULL,
                date         TEXT NOT NULL,
                direction    TEXT NOT NULL,
                airline      TEXT,
                dep_time     TEXT,
                source       TEXT NOT NULL,
                old_price    REAL,
                new_price    REAL NOT NULL,
                changed_at   TIMESTAMP NOT NULL
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_events_dest_date
            ON price_events (destination, date, direction)
        """)

        # 기존 배포: price_events.delta 컬럼 제거 (delta는 쿼리 시 new_price - old_price로 계산)
        cur.execute("ALTER TABLE price_events DROP COLUMN IF EXISTS delta")

        # ── flight_legs 가격 변동 감지 트리거 ──
        cur.execute("""
            CREATE OR REPLACE FUNCTION record_price_change() RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.price <> OLD.price THEN
                    INSERT INTO price_events
                        (destination, date, direction, airline, dep_time,
                         source, old_price, new_price, changed_at)
                    VALUES
                        (NEW.destination, NEW.date, NEW.direction,
                         NEW.airline, NEW.dep_time,
                         COALESCE(NEW.best_source, NEW.source),
                         OLD.price, NEW.price,
                         NEW.checked_at);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        cur.execute("DROP TRIGGER IF EXISTS flight_legs_price_change ON flight_legs")
        cur.execute("""
            CREATE TRIGGER flight_legs_price_change
            AFTER UPDATE ON flight_legs
            FOR EACH ROW
            EXECUTE FUNCTION record_price_change()
        """)

        # 기존 테이블에서 fsc_count 컬럼 제거 (있을 때만)
        cur.execute("ALTER TABLE collection_runs DROP COLUMN IF EXISTS fsc_count")

        # naver_count 컬럼 추가 (있을 때만 스킵)
        cur.execute("""
            ALTER TABLE collection_runs
            ADD COLUMN IF NOT EXISTS naver_count INTEGER DEFAULT 0
        """)

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


def save_legs(legs: list[dict]):
    """편도 항공편 저장 파이프라인.

    raw_legs  : 수집 원본 전량 INSERT (append-only 로그)
    flight_legs: 소스별 최저가 UPSERT — 가격 하락 시 DB 트리거가 price_events에 기록
    """
    if not legs:
        return

    raw_rows = [
        (
            lg["source"], lg["origin"], lg["destination"], lg.get("destination_name"),
            lg["date"], lg["direction"],
            lg.get("airline"), lg.get("dep_time"), lg.get("arr_time"),
            lg.get("duration_min"), lg.get("stops"),
            lg.get("dep_airport"), lg.get("arr_airport"),
            lg["price"], lg.get("currency", "KRW"),
            lg.get("booking_url"), lg.get("search_url"),
            json.dumps(lg["extra"]) if lg.get("extra") else None,
            lg["checked_at"],
        )
        for lg in legs
    ]

    flight_rows = [
        (
            lg["source"], lg["origin"], lg["destination"], lg.get("destination_name"),
            lg["date"], lg["direction"],
            lg.get("airline"), lg.get("dep_time"), lg.get("arr_time"),
            lg.get("duration_min"), lg.get("stops"),
            lg.get("dep_airport"), lg.get("arr_airport"),
            lg["price"],
            lg.get("booking_url"), lg.get("search_url"),
            lg["source"],
            lg["checked_at"],
        )
        for lg in legs
    ]

    with get_conn() as conn:
        cur = conn.cursor()

        # Layer 1: 원본 로그
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO raw_legs
            (source, origin, destination, destination_name,
             date, direction,
             airline, dep_time, arr_time, duration_min, stops,
             dep_airport, arr_airport,
             price, currency, booking_url, search_url, extra,
             collected_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, raw_rows)

        # Layer 2: 현재 상태 (트리거가 가격 하락 시 price_events 기록)
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO flight_legs
            (source, origin, destination, destination_name,
             date, direction,
             airline, dep_time, arr_time, duration_min, stops,
             dep_airport, arr_airport,
             price, booking_url, search_url,
             best_source, checked_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, origin, destination, date, direction,
                         COALESCE(airline, ''), COALESCE(dep_time, ''),
                         COALESCE(arr_time, ''), COALESCE(stops, -1))
            DO UPDATE SET
                price       = LEAST(EXCLUDED.price, flight_legs.price),
                best_source = CASE WHEN EXCLUDED.price < flight_legs.price
                                   THEN EXCLUDED.source
                                   ELSE flight_legs.best_source END,
                booking_url = COALESCE(EXCLUDED.booking_url, flight_legs.booking_url),
                search_url  = COALESCE(EXCLUDED.search_url, flight_legs.search_url),
                checked_at  = EXCLUDED.checked_at
        """, flight_rows)



def load_legs_for_combine(
    source: str, destination: str, since: str | None = None
) -> tuple[list[dict], list[dict]]:
    """flight_legs(단일 진실원)에서 (source, destination)의 since(기본 오늘) 이후 편도
    레그를 읽어 (out_flights, in_flights)로 반환.

    라이브 수집이 deals를 'in-memory tick 조각'이 아니라 DB 전체에서 조합하도록 한다.
    sweep 슬라이싱 + skip_set은 왕복쌍의 out-leg(출발일)와 in-leg(복귀일=D+3/4/5)를
    서로 다른 run에 흩어놓는데, 한 run의 메모리만으로 조합하면 그 쌍이 만나지 못해
    deal이 누락됐다. DB에서 전체를 읽어 조합하면 누락이 사라진다.
    """
    since = since or date.today().isoformat()
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT date, direction, airline, dep_time, arr_time,
                   duration_min, stops, dep_airport, arr_airport,
                   price, booking_url, search_url
            FROM flight_legs
            WHERE source = %s AND destination = %s AND date >= %s
            ORDER BY date, direction, price
        """, (source, destination, since))
        legs = [dict(r) for r in cur.fetchall()]
    out_flights = [leg for leg in legs if leg["direction"] == "out"]
    in_flights  = [leg for leg in legs if leg["direction"] == "in"]
    return out_flights, in_flights


def materialize_deals_for_route(
    source: str, destination: str, destination_name: str | None = None
) -> int:
    """(source, destination)의 미래 deals를 flight_legs 전체에서 재조합해 저장.

    노선별 수집 완료 콜백(on_route_done)으로 호출된다. repopulate 스크립트와 동일하게
    DB를 기준으로 조합하므로, 슬라이싱·skip_set·부분 실패로 레그가 여러 run에 흩어져도
    deals가 flight_legs와 항상 일치한다. 저장된 offer 수를 반환한다.
    """
    out_flights, in_flights = load_legs_for_combine(source, destination)
    if not out_flights or not in_flights:
        return 0
    offers = combine_roundtrips(
        out_flights, in_flights,
        source=source, origin=ORIGIN,
        destination=destination, destination_name=destination_name or destination,
        stay_durations=SEARCH_CONFIG["stay_durations"],
        topk=SEARCH_CONFIG["topk_per_date"],
    )
    if offers:
        save_deals(offers)
    return len(offers)


def save_deals(offers: list[dict]):
    """왕복 조합 offer를 deals 테이블에 사전계산 저장 (읽기 최적화).

    offers에 등장한 (source, destination, departure_date)만 DELETE 후 INSERT → 원자 교체.
    sweep 슬라이싱으로 한 run이 일부 달만 수집해도, 이번에 재수집한 출발일만 교체하고
    다른 달의 deal은 보존한다 → deals가 하루 cron 주기에 걸쳐 전체 기간을 누적한다.
    (이전엔 (source, destination) 단위로 지워, 슬라이싱과 결합 시 마지막 슬라이스의
    달만 남아 가까운 달 화면이 비던 버그가 있었다.) 출발일별 topk 절단은 호출 전
    combine_roundtrips가 이미 적용하므로 여기서 별도 상한은 두지 않는다.
    """
    if not offers:
        return

    # 이번에 재수집한 (source, destination, departure_date) — 이 날짜들만 교체한다.
    keys = sorted({(o["source"], o["destination"], o["departure_date"]) for o in offers})

    rows = [
        (
            o["origin"], o["destination"], o.get("destination_name"),
            o["departure_date"], o["return_date"], o["stay_nights"],
            "oneway_combo" if o["is_mixed_airline"] else "round_trip",
            o["source"],
            o.get("out_airline"), o.get("in_airline"), int(o["is_mixed_airline"]),
            o.get("out_dep_time"), o.get("out_arr_time"), o.get("out_duration_min"), o.get("out_stops"),
            o.get("in_dep_time"), o.get("in_arr_time"), o.get("in_duration_min"), o.get("in_stops"),
            o.get("out_arr_airport"), o.get("in_dep_airport"),
            o.get("out_url"), o.get("in_url"),
            o.get("out_price"), o.get("in_price"), o["price"],
            o["checked_at"],
        )
        for o in offers
    ]

    with get_conn() as conn:
        cur = conn.cursor()
        # offers에 등장한 (source, destination, departure_date)만 교체. 슬라이스가
        # 건드리지 않은 다른 달은 보존한다.
        psycopg2.extras.execute_values(
            cur,
            "DELETE FROM deals USING (VALUES %s) AS t(source, destination, departure_date) "
            "WHERE deals.source = t.source AND deals.destination = t.destination "
            "AND deals.departure_date = t.departure_date",
            keys,
        )
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO deals
            (origin, destination, destination_name,
             departure_date, return_date, stay_nights,
             trip_type, source,
             out_airline, in_airline, is_mixed_airline,
             out_dep_time, out_arr_time, out_duration_min, out_stops,
             in_dep_time, in_arr_time, in_duration_min, in_stops,
             out_arr_airport, in_dep_airport,
             out_url, in_url,
             out_price, in_price, min_price,
             last_checked_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, rows)


def cleanup_old_data():
    """raw_legs 90일 보존 + deals 과거/만료 행 정리.

    save_deals가 (source,destination,departure_date) 단위로만 교체하므로, 출발일이
    지나 더는 재수집되지 않는 deal 행이 잔류한다. 출발일이 지났거나 14일 넘게 갱신
    안 된 deal(노선 제거 등)을 정리해 테이블 증가를 막는다.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM raw_legs WHERE collected_at < NOW() - INTERVAL '90 days'")
        deleted = cur.rowcount
        cur.execute("""
            DELETE FROM deals
            WHERE departure_date < to_char(NOW(), 'YYYY-MM-DD')
               OR last_checked_at < NOW() - INTERVAL '14 days'
        """)
        return deleted


def get_collected_today(source: str) -> set[tuple[str, str, str]]:
    """오늘(KST) 이미 수집한 (destination, date, direction) 집합 반환.

    raw_legs를 기준으로 조회. 동일 날짜 재실행 시 이미 수집된 URL을 스킵하는 데 사용.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT destination, date, direction
            FROM raw_legs
            WHERE source = %s
              AND collected_at >= CURRENT_DATE
            """,
            (source,),
        )
        return {(row[0], row[1], row[2]) for row in cur.fetchall()}


def make_alert_key(offer: dict) -> str:
    # 목적지 × 출발월 단위로 집약 — 날짜·항공사 조합마다 알림이 폭주하던 문제 해결.
    # 같은 목적지·같은 달의 최저가가 갱신될 때만 알림.
    month = offer["departure_date"][:7]
    return f"{offer['destination']}|{month}"


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
        # 좀비 run 청소: 프로세스 강제 종료(OOM/컨테이너 재시작)로 finish가 안 불려
        # 'running'에 박제된 row를 error로 마감. 모니터링 화면·평균 소요시간 왜곡 방지.
        cur.execute("""
            UPDATE collection_runs
            SET status       = 'error',
                finished_at  = NOW(),
                error_log    = 'Orphaned: process crashed or was killed',
                duration_sec = EXTRACT(EPOCH FROM (NOW() - started_at))
            WHERE status = 'running'
              AND started_at < NOW() - INTERVAL '1 hour'
        """)
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
    naver_count: int = 0,
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
                naver_count  = %s,
                total_saved  = %s,
                alerts_sent  = %s,
                error_log    = %s,
                duration_sec = EXTRACT(EPOCH FROM (%s::timestamptz - started_at))
            WHERE id = %s
        """, (datetime.now(KST), status, google_count, naver_count, total_saved, alerts_sent, error_log, datetime.now(KST), run_id))


def get_recent_runs(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, started_at, finished_at, status,
                   google_count, COALESCE(naver_count, 0) AS naver_count,
                   total_saved, alerts_sent,
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


def get_deals_coverage() -> dict:
    """deals 테이블 진단: 목적지×월별 deal 수 + flight_legs 방향별 레그 수 +
    flight_legs엔 있으나 deals엔 없는 목적지 목록을 반환한다.

    수집 데이터가 deals에 제대로 반영됐는지(크롤 부분실패 vs 조합 실패) 구분하는
    진단용. 모두 출발일이 오늘 이후인 행만 대상으로 한다.
    """
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT destination, destination_name,
                   LEFT(departure_date, 7) AS month,
                   COUNT(*) AS deal_count,
                   MIN(min_price) AS best_price,
                   MAX(last_checked_at) AS last_updated
            FROM deals
            WHERE departure_date >= to_char(NOW(), 'YYYY-MM-DD')
            GROUP BY destination, destination_name, month
            ORDER BY destination, month
        """)
        deals_rows = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT destination, destination_name, direction,
                   COUNT(DISTINCT date) AS distinct_dates,
                   COUNT(*) AS total_legs
            FROM flight_legs
            WHERE date >= to_char(NOW(), 'YYYY-MM-DD')
            GROUP BY destination, destination_name, direction
            ORDER BY destination, direction
        """)
        legs_rows = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT DISTINCT fl.destination, fl.destination_name
            FROM flight_legs fl
            WHERE fl.date >= to_char(NOW(), 'YYYY-MM-DD')
              AND fl.destination NOT IN (
                  SELECT DISTINCT destination FROM deals
                  WHERE departure_date >= to_char(NOW(), 'YYYY-MM-DD')
              )
            ORDER BY fl.destination
        """)
        missing_rows = [dict(r) for r in cur.fetchall()]

    return {
        "deals_by_dest_month": deals_rows,
        "legs_by_dest_direction": legs_rows,
        "missing_from_deals": missing_rows,
    }
