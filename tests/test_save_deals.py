"""
테스트: storage.save_deals 증분 교체 (sweep 슬라이싱 안전성)

한 run이 일부 달만 저장해도 다른 달 deal이 보존되는지 — 즉 DELETE 단위가
(source, destination, departure_date) 인지 검증한다. 이전엔 (source, destination)
단위로 지워, 슬라이싱과 결합 시 마지막 슬라이스의 달만 남아 화면이 비던 버그가 있었다.
PostgreSQL 사용 (deals TRUNCATE로 격리).
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flight_monitor.storage as storage


@pytest.fixture(autouse=True)
def clean_db():
    storage.init_db()
    with storage.get_conn() as conn:
        conn.cursor().execute("TRUNCATE deals RESTART IDENTITY")
    yield
    with storage.get_conn() as conn:
        conn.cursor().execute("TRUNCATE deals RESTART IDENTITY")


def _offer(departure_date, price, destination="TYO", source="google_flights"):
    return {
        "origin": "ICN", "destination": destination, "destination_name": "도쿄",
        "departure_date": departure_date, "return_date": departure_date,
        "stay_nights": 3, "is_mixed_airline": 0, "source": source,
        "out_airline": "KE", "in_airline": "KE",
        "out_dep_time": "09:00", "out_arr_time": "11:00", "out_duration_min": 120, "out_stops": 0,
        "in_dep_time": "12:00", "in_arr_time": "14:00", "in_duration_min": 120, "in_stops": 0,
        "out_arr_airport": "NRT", "in_dep_airport": "NRT",
        "out_url": "http://x", "in_url": "http://y",
        "out_price": price // 2, "in_price": price // 2, "price": price,
        "checked_at": datetime.now(),
    }


def _months_in_deals():
    with storage.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT LEFT(departure_date, 7) FROM deals ORDER BY 1")
        return [r[0] for r in cur.fetchall()]


def test_slice_save_preserves_other_months():
    """다른 달 슬라이스를 저장해도 기존 달 deal이 보존된다 (핵심 회귀)."""
    storage.save_deals([_offer("2026-06-15", 300000)])   # 슬라이스 1: 6월
    storage.save_deals([_offer("2026-09-15", 400000)])   # 슬라이스 2: 9월 (같은 source/dest)
    assert _months_in_deals() == ["2026-06", "2026-09"]


def test_resave_same_date_replaces_not_duplicates():
    """같은 (source,dest,날짜) 재수집은 누적이 아니라 교체된다."""
    storage.save_deals([_offer("2026-06-15", 300000)])
    storage.save_deals([_offer("2026-06-15", 250000)])
    with storage.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(min_price) FROM deals WHERE departure_date = '2026-06-15'")
        count, min_price = cur.fetchone()
    assert count == 1
    assert min_price == 250000


def test_other_destination_untouched():
    """한 목적지의 날짜 교체가 다른 목적지 deal을 건드리지 않는다."""
    storage.save_deals([_offer("2026-06-15", 300000, destination="TYO")])
    storage.save_deals([_offer("2026-06-15", 350000, destination="OSA")])
    with storage.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT destination FROM deals ORDER BY destination")
        dests = [r[0] for r in cur.fetchall()]
    assert dests == ["OSA", "TYO"]
