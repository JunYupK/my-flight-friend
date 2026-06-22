"""
테스트: storage.materialize_deals_for_route (DB 기준 deals 조합)

라이브 수집이 deals를 'in-memory tick 조각'이 아니라 flight_legs 전체에서 조합하는지
검증한다. sweep 슬라이싱 + skip_set은 왕복쌍의 out-leg(출발일)와 in-leg(복귀일)를 서로
다른 run에 흩어놓는데, 한 run의 메모리만으로 조합하면 그 쌍이 만나지 못해 deal이
누락됐다(근미래 deals 붕괴 버그). DB에서 합쳐 조합하면 누락이 사라진다.
PostgreSQL 사용 (deals / flight_legs TRUNCATE로 격리).
"""

import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import flight_monitor.storage as storage

# materialize는 date >= today 인 레그만 조합하므로 미래 날짜로 고정.
_DEP = (date.today() + timedelta(days=30)).isoformat()
_RET = (date.today() + timedelta(days=33)).isoformat()  # stay 3박


# save_legs는 flight_legs와 raw_legs 양쪽에 쓰므로 둘 다 정리해야 다른 테스트를
# 오염시키지 않는다. 셋업·티어다운 모두에서 비워 실행 순서와 무관하게 격리한다.
_TRUNCATE = "TRUNCATE deals, flight_legs, raw_legs RESTART IDENTITY"


@pytest.fixture(autouse=True)
def clean_db():
    storage.init_db()
    with storage.get_conn() as conn:
        conn.cursor().execute(_TRUNCATE)
    yield
    with storage.get_conn() as conn:
        conn.cursor().execute(_TRUNCATE)


def _leg(leg_date, direction, price, *, source="google_flights", destination="TYO"):
    return {
        "source": source, "origin": "ICN",
        "destination": destination, "destination_name": "도쿄",
        "date": leg_date, "direction": direction,
        "airline": "KE", "dep_time": "09:00", "arr_time": "11:00",
        "duration_min": 120, "stops": 0,
        "dep_airport": "ICN" if direction == "out" else "NRT",
        "arr_airport": "NRT" if direction == "out" else "ICN",
        "price": price, "booking_url": "http://b", "search_url": "http://s",
        "checked_at": datetime.now().isoformat(),
    }


def _deal_count(destination="TYO"):
    with storage.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM deals WHERE destination = %s", (destination,))
        return cur.fetchone()[0]


def test_combines_legs_split_across_runs():
    """out-leg와 in-leg가 서로 다른 run에 저장돼도 DB에서 합쳐 조합된다 (핵심 회귀).

    한쪽 레그만 있을 땐 deal 0건, 양쪽 레그가 모이면 deal이 생성돼야 한다.
    in-memory tick 조합이었다면 두 run 어느 쪽도 이 쌍을 만들지 못한다.
    """
    # run A: 출발편만 저장 → 아직 복귀편이 없어 조합 불가
    storage.save_legs([_leg(_DEP, "out", 150000)])
    assert storage.materialize_deals_for_route("google_flights", "TYO", "도쿄") == 0
    assert _deal_count() == 0

    # run B: 복귀편 저장 → 이제 DB에 양방향이 다 있으므로 조합 성공
    storage.save_legs([_leg(_RET, "in", 130000)])
    n = storage.materialize_deals_for_route("google_flights", "TYO", "도쿄")
    assert n >= 1
    assert _deal_count() >= 1

    with storage.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT departure_date, return_date, min_price FROM deals "
            "WHERE destination = 'TYO' ORDER BY min_price LIMIT 1"
        )
        dep, ret, price = cur.fetchone()
    assert dep == _DEP
    assert ret == _RET
    assert price == 280000  # 150000 + 130000


def test_only_touched_route_rematerialized():
    """한 노선 materialize가 다른 노선의 기존 deals를 건드리지 않는다."""
    # OSA는 이미 deals가 있다고 가정하고 직접 넣어둔다.
    storage.save_legs([_leg(_DEP, "out", 100000, destination="OSA")])
    storage.save_legs([_leg(_RET, "in", 100000, destination="OSA")])
    storage.materialize_deals_for_route("google_flights", "OSA", "오사카")
    assert _deal_count("OSA") >= 1

    # TYO만 새로 materialize → OSA deals는 그대로 보존
    storage.save_legs([_leg(_DEP, "out", 150000)])
    storage.save_legs([_leg(_RET, "in", 130000)])
    storage.materialize_deals_for_route("google_flights", "TYO", "도쿄")
    assert _deal_count("TYO") >= 1
    assert _deal_count("OSA") >= 1
