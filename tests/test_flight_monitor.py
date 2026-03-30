"""
테스트: storage 모듈
외부 API는 호출하지 않음. PostgreSQL DB 사용 (TRUNCATE로 격리).
"""

import os
import sys
import pytest
import psycopg2.extras
from datetime import datetime, timedelta

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flight_monitor.config import KST

import flight_monitor.storage as storage

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
        cur.execute("""
            TRUNCATE price_history, alert_state,
                     flight_legs, raw_legs, price_events
            RESTART IDENTITY CASCADE
        """)


def _make_offer(**kwargs) -> dict:
    """테스트용 offer 기본값"""
    defaults = {
        "source": "google_flights",
        "trip_type": "oneway_combo",
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
        "checked_at": datetime.now(KST).isoformat(),
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
        assert "raw_legs" in tables
        assert "price_events" in tables
        assert "flight_legs" in tables

    def test_trigger_created(self):
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT trigger_name FROM information_schema.triggers
                WHERE event_object_table = 'flight_legs'
                  AND trigger_name = 'flight_legs_price_change'
            """)
            assert cur.fetchone() is not None

    def test_flight_legs_has_best_source(self):
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'flight_legs' AND column_name = 'best_source'
            """)
            assert cur.fetchone() is not None

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
        a = _make_offer(source="google_flights")
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
        past = (datetime.now(KST) - timedelta(hours=13)).isoformat()
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


def _make_leg(**kwargs) -> dict:
    """테스트용 leg 기본값"""
    defaults = {
        "source": "google_flights",
        "origin": "ICN",
        "destination": "OSA",
        "destination_name": "오사카",
        "date": "2026-05-10",
        "direction": "out",
        "airline": "KE",
        "dep_time": "09:00",
        "arr_time": "11:30",
        "duration_min": 150,
        "stops": 0,
        "dep_airport": None,
        "arr_airport": "KIX",
        "price": 150000.0,
        "booking_url": None,
        "search_url": "https://flights.google.com/example",
        "checked_at": datetime.now(KST).isoformat(),
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# storage: save_legs (3-레이어 파이프라인)
# ---------------------------------------------------------------------------

class TestSaveLegs:
    def test_raw_legs_inserted(self):
        """save_legs 호출 시 raw_legs에 행이 삽입된다."""
        storage.save_legs([_make_leg()])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM raw_legs")
            assert cur.fetchone()[0] == 1

    def test_flight_legs_upserted(self):
        """save_legs 호출 시 flight_legs에 행이 UPSERT된다."""
        storage.save_legs([_make_leg()])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM flight_legs")
            assert cur.fetchone()[0] == 1

    def test_best_source_set_on_insert(self):
        """최초 삽입 시 best_source가 source와 동일하게 설정된다."""
        storage.save_legs([_make_leg(source="google_flights")])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT best_source FROM flight_legs")
            assert cur.fetchone()[0] == "google_flights"

    def test_upsert_keeps_lower_price(self):
        """같은 레그를 다른 가격으로 두 번 저장 시 최저가만 유지된다."""
        storage.save_legs([_make_leg(price=200000)])
        storage.save_legs([_make_leg(price=150000)])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT price FROM flight_legs")
            assert cur.fetchone()[0] == 150000

    def test_upsert_higher_price_ignored(self):
        """더 높은 가격으로 재수집해도 flight_legs 가격이 오르지 않는다."""
        storage.save_legs([_make_leg(price=150000)])
        storage.save_legs([_make_leg(price=200000)])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT price FROM flight_legs")
            assert cur.fetchone()[0] == 150000

    def test_price_drop_triggers_price_event(self):
        """가격이 하락하면 price_events에 행이 기록된다."""
        storage.save_legs([_make_leg(price=200000)])
        storage.save_legs([_make_leg(price=150000)])
        with storage.get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM price_events")
            row = cur.fetchone()
        assert row is not None
        assert row["old_price"] == 200000
        assert row["new_price"] == 150000
        assert row["new_price"] - row["old_price"] == -50000

    def test_same_price_no_price_event(self):
        """동일 가격 재수집 시 price_events에 행이 추가되지 않는다."""
        storage.save_legs([_make_leg(price=150000)])
        storage.save_legs([_make_leg(price=150000)])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM price_events")
            assert cur.fetchone()[0] == 0

    def test_price_rise_no_price_event(self):
        """더 높은 가격 수집 시 flight_legs 불변 + price_events 없음."""
        storage.save_legs([_make_leg(price=150000)])
        storage.save_legs([_make_leg(price=200000)])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM price_events")
            assert cur.fetchone()[0] == 0

    def test_different_sources_create_separate_rows(self):
        """서로 다른 source는 각각 독립 row로 저장되며 best_source는 자신의 source와 동일하다."""
        storage.save_legs([_make_leg(source="google_flights", price=200000)])
        storage.save_legs([_make_leg(source="naver", price=150000)])
        with storage.get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT source, best_source FROM flight_legs ORDER BY price")
            rows = cur.fetchall()
        assert len(rows) == 2
        assert rows[0]["source"] == "naver"
        assert rows[0]["best_source"] == "naver"
        assert rows[1]["source"] == "google_flights"
        assert rows[1]["best_source"] == "google_flights"

    def test_empty_list_no_db_touch(self):
        """빈 리스트 호출 시 DB에 아무것도 쓰지 않는다."""
        storage.save_legs([])
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM raw_legs")
            assert cur.fetchone()[0] == 0

    def test_multiple_legs_all_inserted_to_raw(self):
        """여러 레그를 한번에 저장 시 raw_legs에 모두 기록된다."""
        legs = [_make_leg(date=f"2026-05-{10+i:02d}") for i in range(3)]
        storage.save_legs(legs)
        with storage.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM raw_legs")
            assert cur.fetchone()[0] == 3
