"""
테스트: storage, collector_lcc 내부 함수, mcp_server
외부 API(Amadeus, Naver)는 호출하지 않음. DB는 tmp 경로 사용.
"""

import os
import sys
import sqlite3
import tempfile
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flight_monitor.storage as storage
from flight_monitor.collector_lcc import (
    _index_topk_by_date,
    _combine_roundtrips,
)
from flight_monitor import mcp_server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """각 테스트마다 격리된 임시 DB를 사용.
    get_conn()은 런타임에 storage.DB_PATH를 참조하므로
    storage.DB_PATH 하나만 패치하면 mcp_server도 동일 경로 사용.
    """
    db_file = str(tmp_path / "test_flights.db")
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    storage.init_db()
    return db_file


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
    def test_tables_created(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "price_history" in tables
        assert "alert_state" in tables

    def test_view_created(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        views = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()}
        conn.close()
        assert "v_best_observed" in views

    def test_init_idempotent(self):
        """두 번 호출해도 에러 없음"""
        storage.init_db()
        storage.init_db()


# ---------------------------------------------------------------------------
# storage: save_prices
# ---------------------------------------------------------------------------

class TestSavePrices:
    def test_basic_insert(self, tmp_db):
        offer = _make_offer()
        storage.save_prices([offer])
        conn = sqlite3.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        conn.close()
        assert count == 1

    def test_multiple_insert(self, tmp_db):
        offers = [_make_offer(price=200000 + i * 1000) for i in range(5)]
        storage.save_prices(offers)
        conn = sqlite3.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        conn.close()
        assert count == 5

    def test_price_stored_correctly(self, tmp_db):
        storage.save_prices([_make_offer(price=199999.0)])
        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT price FROM price_history").fetchone()
        conn.close()
        assert row[0] == 199999.0

    def test_is_mixed_airline_stored_as_int(self, tmp_db):
        storage.save_prices([_make_offer(is_mixed_airline=True)])
        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT is_mixed_airline FROM price_history").fetchone()
        conn.close()
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
            conn.execute(
                "UPDATE alert_state SET last_sent_at = ? WHERE alert_key = ?",
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
            row = conn.execute(
                "SELECT last_price FROM alert_state WHERE alert_key = ?", (key,)
            ).fetchone()
        assert row[0] == 200000


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


# ---------------------------------------------------------------------------
# mcp_server: get_best_deals
# ---------------------------------------------------------------------------

class TestGetBestDeals:
    def _insert_offers(self, offers):
        storage.save_prices(offers)

    def test_returns_top_n(self):
        offers = [
            _make_offer(destination="OSA", departure_date=f"2026-05-{10+i:02d}",
                        return_date=f"2026-05-{17+i:02d}", price=(200000 + i * 10000))
            for i in range(5)
        ]
        self._insert_offers(offers)
        result = mcp_server.get_best_deals(limit=3)
        assert len(result) == 3
        prices = [r["min_price"] for r in result]
        assert prices == sorted(prices)

    def test_filter_by_destination(self):
        self._insert_offers([
            _make_offer(destination="OSA", price=200000),
            _make_offer(destination="TYO", departure_date="2026-05-15",
                        return_date="2026-05-22", price=180000),
        ])
        result = mcp_server.get_best_deals(destination="OSA")
        assert all(r["destination_name"] == "오사카 (간사이/이타미)" for r in result)
        assert len(result) == 1

    def test_filter_by_month(self):
        self._insert_offers([
            _make_offer(departure_date="2026-05-10", return_date="2026-05-17", price=200000),
            _make_offer(departure_date="2026-06-10", return_date="2026-06-17", price=180000),
        ])
        result = mcp_server.get_best_deals(month="2026-05")
        assert len(result) == 1
        assert result[0]["departure_date"] == "2026-05-10"

    def test_filter_by_stay_nights(self):
        self._insert_offers([
            _make_offer(stay_nights=3, return_date="2026-05-13", price=200000),
            _make_offer(stay_nights=7, return_date="2026-05-17", price=220000),
        ])
        result = mcp_server.get_best_deals(stay_nights=3)
        assert len(result) == 1
        assert result[0]["stay_nights"] == 3

    def test_empty_db_returns_empty_list(self):
        assert mcp_server.get_best_deals() == []


# ---------------------------------------------------------------------------
# mcp_server: get_price_history
# ---------------------------------------------------------------------------

class TestGetPriceHistory:
    def test_returns_sorted_by_date(self):
        storage.save_prices([
            _make_offer(departure_date="2026-05-15", return_date="2026-05-22", price=250000),
            _make_offer(departure_date="2026-05-10", return_date="2026-05-17", price=200000),
        ])
        result = mcp_server.get_price_history(destination="OSA", month="2026-05")
        dates = [r["departure_date"] for r in result]
        assert dates == sorted(dates)

    def test_filters_by_destination_and_month(self):
        storage.save_prices([
            _make_offer(destination="OSA", departure_date="2026-05-10",
                        return_date="2026-05-17", price=200000),
            _make_offer(destination="TYO", departure_date="2026-05-10",
                        return_date="2026-05-17", price=180000),
        ])
        result = mcp_server.get_price_history(destination="OSA", month="2026-05")
        assert len(result) == 1

    def test_empty_returns_empty_list(self):
        assert mcp_server.get_price_history(destination="OSA", month="2026-05") == []


# ---------------------------------------------------------------------------
# mcp_server: explain_deal
# ---------------------------------------------------------------------------

class TestExplainDeal:
    def test_returns_best_price(self):
        storage.save_prices([
            _make_offer(price=300000, source="amadeus"),
            _make_offer(price=200000, source="naver_graphql"),
        ])
        result = mcp_server.explain_deal(
            destination="OSA",
            departure_date="2026-05-10",
            return_date="2026-05-17",
        )
        assert result["best_price"] == 200000

    def test_missing_deal_returns_error(self):
        result = mcp_server.explain_deal(
            destination="OSA",
            departure_date="2026-05-10",
            return_date="2026-05-17",
        )
        assert "error" in result

    def test_mixed_airline_note(self):
        storage.save_prices([
            _make_offer(out_airline="KE", in_airline="OZ", is_mixed_airline=True, price=200000),
        ])
        result = mcp_server.explain_deal("OSA", "2026-05-10", "2026-05-17")
        assert result["is_mixed_airline"] is True
        assert len(result["notes"]) > 0

    def test_by_source_breakdown(self):
        storage.save_prices([
            _make_offer(price=300000, source="amadeus"),
            _make_offer(price=200000, source="naver_graphql"),
        ])
        result = mcp_server.explain_deal("OSA", "2026-05-10", "2026-05-17")
        assert "amadeus" in result["by_source"]
        assert "naver_graphql" in result["by_source"]
