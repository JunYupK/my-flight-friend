"""
테스트: storage, collector_lcc 내부 함수
외부 API(Amadeus, Naver)는 호출하지 않음. PostgreSQL DB 사용 (TRUNCATE로 격리).
"""

import os
import sys
import pytest
import psycopg2.extras
from datetime import datetime, timedelta
from unittest.mock import patch

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flight_monitor.storage as storage
from flight_monitor.collector_lcc import (
    _index_topk_by_date,
    _combine_roundtrips,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_db():
    """각 테스트마다 테이블을 초기화. init_db()로 테이블 보장 후 TRUNCATE."""
    storage.init_db()
    yield
    with storage.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("TRUNCATE price_history, alert_state RESTART IDENTITY CASCADE")


def _make_offer(**kwargs) -> dict:
    """테스트용 offer 기본값"""
    defaults = {
        "source": "amadeus",
        "trip_type": "round_trip",
        "origin": "ICN",
        "destination": "OSA",
        "destination_name": "오사카 (간사이/이타미)",
        "departure_date": "2026-05-10",
        "return_date": "2026-05-17",
        "stay_nights": 7,
        "price": 250000.0,
        "currency": "KRW",
        "out_airline": "KE",
        "in_airline": "KE",
        "is_mixed_airline": False,
        "checked_at": datetime.now().isoformat(),
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# storage: init_db
# ---------------------------------------------------------------------------

class TestInitDb:
    def test_tables_created(self):
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)
            tables = {r[0] for r in cur.fetchall()}
        assert "price_history" in tables
        assert "alert_state" in tables

    def test_view_created(self):
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT table_name FROM information_schema.views
                WHERE table_schema = 'public'
            """)
            views = {r[0] for r in cur.fetchall()}
        assert "v_best_observed" in views

    def test_init_idempotent(self):
        """두 번 호출해도 에러 없음"""
        storage.init_db()
        storage.init_db()


# ---------------------------------------------------------------------------
# storage: save_prices
# ---------------------------------------------------------------------------

class TestSavePrices:
    def test_basic_insert(self):
        storage.save_prices([_make_offer()])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM price_history")
            count = cur.fetchone()[0]
        assert count == 1

    def test_multiple_insert(self):
        offers = [_make_offer(price=200000 + i * 1000) for i in range(5)]
        storage.save_prices(offers)
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM price_history")
            count = cur.fetchone()[0]
        assert count == 5

    def test_price_stored_correctly(self):
        storage.save_prices([_make_offer(price=199999.0)])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT price FROM price_history")
            row = cur.fetchone()
        assert row[0] == 199999.0

    def test_is_mixed_airline_stored_as_int(self):
        storage.save_prices([_make_offer(is_mixed_airline=True)])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT is_mixed_airline FROM price_history")
            row = cur.fetchone()
        assert row[0] == 1


# ---------------------------------------------------------------------------
# storage: make_alert_key
# ---------------------------------------------------------------------------

class TestMakeAlertKey:
    def test_same_offer_same_key(self):
        offer = _make_offer()
        assert storage.make_alert_key(offer) == storage.make_alert_key(offer)

    def test_different_source_same_key(self):
        """source가 달라도 동일 키 — 중복 알림 방지"""
        a = _make_offer(source="amadeus")
        b = _make_offer(source="naver_graphql")
        assert storage.make_alert_key(a) == storage.make_alert_key(b)

    def test_different_destination_different_key(self):
        a = _make_offer(destination="OSA")
        b = _make_offer(destination="TYO")
        assert storage.make_alert_key(a) != storage.make_alert_key(b)

    def test_different_dates_different_key(self):
        a = _make_offer(departure_date="2026-05-10")
        b = _make_offer(departure_date="2026-05-11")
        assert storage.make_alert_key(a) != storage.make_alert_key(b)

    def test_different_mixed_flag_different_key(self):
        a = _make_offer(is_mixed_airline=False)
        b = _make_offer(is_mixed_airline=True)
        assert storage.make_alert_key(a) != storage.make_alert_key(b)


# ---------------------------------------------------------------------------
# storage: should_notify / record_alert
# ---------------------------------------------------------------------------

class TestShouldNotify:
    def test_first_alert_always_notifies(self):
        assert storage.should_notify(_make_offer()) is True

    def test_after_record_cooldown_blocks(self):
        offer = _make_offer(price=250000)
        storage.record_alert(offer)
        # 쿨다운 내 동일 가격 → 알림 차단
        assert storage.should_notify(offer) is False

    def test_price_drop_triggers_realert(self):
        offer = _make_offer(price=250000)
        storage.record_alert(offer)
        # 15000원 초과 하락 → 쿨다운 내에도 재알림
        cheaper = _make_offer(price=234999)
        assert storage.should_notify(cheaper) is True

    def test_price_drop_exact_threshold_triggers(self):
        offer = _make_offer(price=250000)
        storage.record_alert(offer)
        # 정확히 15000원 하락 (250000 - 15000 = 235000) → 조건: price <= last - drop
        exactly_threshold = _make_offer(price=235000)
        assert storage.should_notify(exactly_threshold) is True

    def test_price_drop_insufficient_does_not_trigger(self):
        offer = _make_offer(price=250000)
        storage.record_alert(offer)
        # 14999원 하락 — 역치 미달
        barely_dropped = _make_offer(price=235001)
        assert storage.should_notify(barely_dropped) is False

    def test_cooldown_passed_triggers_realert(self):
        offer = _make_offer(price=250000)
        storage.record_alert(offer)
        # last_sent_at을 13시간 전으로 조작 (쿨다운 12시간 초과)
        past = (datetime.now() - timedelta(hours=13)).isoformat()
        key = storage.make_alert_key(offer)
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE alert_state SET last_sent_at = %s WHERE alert_key = %s",
                (past, key),
            )
        assert storage.should_notify(offer) is True

    def test_record_alert_updates_price(self):
        offer_high = _make_offer(price=300000)
        storage.record_alert(offer_high)
        offer_low = _make_offer(price=200000)
        storage.record_alert(offer_low)  # 업데이트
        key = storage.make_alert_key(offer_low)
        with storage.get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT last_price FROM alert_state WHERE alert_key = %s", (key,)
            )
            row = cur.fetchone()
        assert row["last_price"] == 200000


# ---------------------------------------------------------------------------
# collector_lcc: _index_topk_by_date
# ---------------------------------------------------------------------------

class TestIndexTopkByDate:
    def _flight(self, date, price, airline="KE"):
        return {"date": date, "airline": airline, "price": price, "dep_time": "", "arr_time": ""}

    def test_returns_sorted_topk(self):
        flights = [
            self._flight("2026-05-01", 50000),
            self._flight("2026-05-01", 30000),
            self._flight("2026-05-01", 40000),
            self._flight("2026-05-01", 20000),
            self._flight("2026-05-01", 10000),
            self._flight("2026-05-01", 60000),  # 6번째 — k=5이면 제외
        ]
        result = _index_topk_by_date(flights, k=5)
        assert len(result["2026-05-01"]) == 5
        prices = [f["price"] for f in result["2026-05-01"]]
        assert prices == sorted(prices)
        assert 60000 not in prices

    def test_groups_by_date(self):
        flights = [
            self._flight("2026-05-01", 10000),
            self._flight("2026-05-02", 20000),
            self._flight("2026-05-02", 15000),
        ]
        result = _index_topk_by_date(flights, k=5)
        assert "2026-05-01" in result
        assert "2026-05-02" in result
        assert len(result["2026-05-01"]) == 1
        assert len(result["2026-05-02"]) == 2

    def test_empty_input(self):
        assert _index_topk_by_date([], k=5) == {}


# ---------------------------------------------------------------------------
# collector_lcc: _combine_roundtrips
# ---------------------------------------------------------------------------

class TestCombineRoundtrips:
    def _flight(self, date, price, airline="KE"):
        return {"date": date, "airline": airline, "price": price, "dep_time": "", "arr_time": ""}

    def test_basic_combination(self):
        out = [self._flight("2026-05-01", 100000)]
        # stay_durations = [3, 5, 7] → ret_date = 05-04, 05-06, 05-08
        ret = [self._flight("2026-05-04", 90000)]  # stay 3박
        results = _combine_roundtrips(out, ret)
        assert len(results) == 1
        assert results[0]["price"] == 190000
        assert results[0]["stay_nights"] == 3

    def test_no_matching_return(self):
        out = [self._flight("2026-05-01", 100000)]
        ret = [self._flight("2026-05-10", 90000)]  # 어떤 stay도 매칭 안 됨
        results = _combine_roundtrips(out, ret)
        assert results == []

    def test_mixed_airline_included_when_allowed(self):
        out = [self._flight("2026-05-01", 100000, airline="KE")]
        ret = [self._flight("2026-05-06", 90000, airline="OZ")]  # stay 5박
        results = _combine_roundtrips(out, ret)
        assert any(r["is_mixed_airline"] for r in results)

    def test_mixed_airline_blocked_when_not_allowed(self):
        with patch("flight_monitor.collector_lcc.SEARCH_CONFIG", {
            **__import__("flight_monitor.config", fromlist=["SEARCH_CONFIG"]).SEARCH_CONFIG,
            "allow_mixed_airline": False,
            "lcc_topk_per_date": 5,
        }):
            out = [self._flight("2026-05-01", 100000, airline="KE")]
            ret = [self._flight("2026-05-06", 90000, airline="OZ")]
            results = _combine_roundtrips(out, ret)
            assert all(not r["is_mixed_airline"] for r in results)

    def test_result_sorted_by_price(self):
        out = [
            self._flight("2026-05-01", 200000),
            self._flight("2026-05-02", 100000),
        ]
        ret = [
            self._flight("2026-05-04", 100000),  # 05-01 + 3박
            self._flight("2026-05-05", 80000),   # 05-02 + 3박
        ]
        results = _combine_roundtrips(out, ret)
        prices = [r["price"] for r in results]
        assert prices == sorted(prices)

    def test_source_is_naver_graphql(self):
        out = [self._flight("2026-05-01", 100000)]
        ret = [self._flight("2026-05-04", 90000)]
        results = _combine_roundtrips(out, ret)
        assert all(r["source"] == "naver_graphql" for r in results)
