"""
테스트: deals_cache._query_timing_advance
raw_legs 기반 예약 타이밍(advance) 집계 쿼리 회귀 테스트. PostgreSQL 사용 (TRUNCATE로 격리).
"""

import os
import sys
import pytest
import psycopg2.extras
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flight_monitor.storage as storage
from flight_front.api.deals_cache import _query_timing_advance


@pytest.fixture(autouse=True)
def clean_db():
    storage.init_db()
    yield
    with storage.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            TRUNCATE price_history, alert_state,
                     flight_legs, raw_legs, price_events
            RESTART IDENTITY CASCADE
        """)


def _insert_raw_leg(cur, destination, date, direction, price, collected_at,
                    source="google_flights", destination_name="나리타"):
    cur.execute("""
        INSERT INTO raw_legs
        (source, origin, destination, destination_name, date, direction, price, collected_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (source, "ICN", destination, destination_name, date, direction, price, collected_at))


class TestQueryTimingAdvance:
    def test_buckets_by_days_before_departure(self):
        departure = datetime.now() + timedelta(days=40)
        return_date = departure + timedelta(days=4)

        with storage.get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            for snap_offset, price_out, price_in in [
                (40, 200000, 150000), (20, 180000, 140000), (5, 250000, 200000),
            ]:
                collected_at = departure - timedelta(days=snap_offset)
                for source, bump in [("google_flights", 0), ("naver", 10000)]:
                    _insert_raw_leg(cur, "NRT", departure.strftime("%Y-%m-%d"), "out",
                                    price_out + bump, collected_at, source=source)
                    _insert_raw_leg(cur, "NRT", return_date.strftime("%Y-%m-%d"), "in",
                                    price_in + bump, collected_at, source=source)
            conn.commit()

            result = _query_timing_advance(cur, None)

        buckets = {r["days_before"]: r for r in result}
        assert set(buckets) == {0, 14, 28}
        assert buckets[28]["min_price"] == 350000
        assert buckets[28]["obs_count"] == 4
        assert buckets[0]["min_price"] == 450000

    def test_destination_filter(self):
        departure = datetime.now() + timedelta(days=10)
        return_date = departure + timedelta(days=3)
        collected_at = departure - timedelta(days=5)

        with storage.get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            for dest in ["NRT", "OSA"]:
                for source in ["google_flights", "naver", "skyscanner"]:
                    _insert_raw_leg(cur, dest, departure.strftime("%Y-%m-%d"), "out",
                                    100000, collected_at, source=source)
                    _insert_raw_leg(cur, dest, return_date.strftime("%Y-%m-%d"), "in",
                                    80000, collected_at, source=source)
            conn.commit()

            result_all = _query_timing_advance(cur, None)
            result_nrt = _query_timing_advance(cur, "NRT")
            result_none = _query_timing_advance(cur, "ICN")

        assert {r["destination"] for r in result_all} == {"NRT", "OSA"}
        assert {r["destination"] for r in result_nrt} == {"NRT"}
        assert result_none == []

    def test_requires_at_least_three_observations(self):
        departure = datetime.now() + timedelta(days=10)
        return_date = departure + timedelta(days=3)
        collected_at = departure - timedelta(days=5)

        with storage.get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            _insert_raw_leg(cur, "NRT", departure.strftime("%Y-%m-%d"), "out", 100000, collected_at)
            _insert_raw_leg(cur, "NRT", return_date.strftime("%Y-%m-%d"), "in", 80000, collected_at)
            conn.commit()

            result = _query_timing_advance(cur, None)

        assert result == []
