# tests/test_search_service.py
#
# search_service 순수 함수 단위 테스트 (DB 불필요)

from datetime import datetime

from flight_front.api.search_service import combine_legs, select_diverse_deals


def _deal(min_price, out_dep_time=None, in_dep_time=None):
    return {
        "min_price": min_price,
        "out_dep_time": out_dep_time,
        "in_dep_time": in_dep_time,
    }


class TestSelectDiverseDeals:
    def test_one_per_bucket_first(self):
        deals = [
            _deal(100000, "07:00", "08:00"),   # early_early
            _deal(110000, "07:30", "08:30"),   # early_early (같은 버킷)
            _deal(120000, "13:00", "18:00"),   # afternoon_evening
        ]
        result = select_diverse_deals(deals, max_count=2)
        assert len(result) == 2
        prices = {d["min_price"] for d in result}
        # 각 버킷 최저가 1건씩 우선 선택
        assert prices == {100000, 120000}

    def test_max_count_enforced(self):
        deals = [_deal(100000 + i, "07:00", "08:00") for i in range(30)]
        result = select_diverse_deals(deals, max_count=15)
        assert len(result) <= 15

    def test_no_time_deals_fill_remainder(self):
        deals = [_deal(100000, "07:00", "08:00"), _deal(90000)]
        result = select_diverse_deals(deals, max_count=15)
        assert len(result) == 2

    def test_sorted_by_min_price(self):
        deals = [
            _deal(300000, "07:00", "08:00"),
            _deal(100000, "13:00", "18:00"),
            _deal(200000, "10:00", "10:00"),
        ]
        result = select_diverse_deals(deals)
        prices = [d["min_price"] for d in result]
        assert prices == sorted(prices)

    def test_empty_input(self):
        assert select_diverse_deals([]) == []


def _out_leg(dest="NRT", airline="KE", price=100000):
    return {
        "origin": "ICN",
        "destination": dest,
        "destination_name": "도쿄",
        "source": "google_flights",
        "out_airline": airline,
        "out_dep_time": "08:00",
        "out_arr_time": "10:00",
        "out_duration_min": 120,
        "out_stops": 0,
        "out_arr_airport": dest,
        "out_url": None,
        "out_price": price,
        "last_checked_at": datetime(2026, 6, 1, 12, 0),
    }


def _in_leg(dest="NRT", airline="KE", price=120000):
    return {
        "destination": dest,
        "in_airline": airline,
        "in_dep_time": "18:00",
        "in_arr_time": "20:00",
        "in_duration_min": 120,
        "in_stops": 0,
        "in_dep_airport": dest,
        "in_url": None,
        "in_price": price,
        "last_checked_at": datetime(2026, 6, 1, 13, 0),
    }


class TestCombineLegs:
    def test_cross_product_same_destination(self):
        deals = combine_legs(
            [_out_leg(), _out_leg(price=110000)],
            [_in_leg(), _in_leg(price=130000)],
            "2026-07-01", "2026-07-04", None,
        )
        assert len(deals) == 4
        assert all(d["stay_nights"] == 3 for d in deals)

    def test_destination_mismatch_not_combined(self):
        deals = combine_legs(
            [_out_leg(dest="NRT")],
            [_in_leg(dest="KIX")],
            "2026-07-01", "2026-07-04", None,
        )
        assert deals == []

    def test_trip_type_round_trip_filters_mixed(self):
        deals = combine_legs(
            [_out_leg(airline="KE")],
            [_in_leg(airline="KE"), _in_leg(airline="7C")],
            "2026-07-01", "2026-07-04", "round_trip",
        )
        assert len(deals) == 1
        assert deals[0]["is_mixed_airline"] is False
        assert deals[0]["trip_type"] == "round_trip"

    def test_trip_type_oneway_combo_filters_same(self):
        deals = combine_legs(
            [_out_leg(airline="KE")],
            [_in_leg(airline="KE"), _in_leg(airline="7C")],
            "2026-07-01", "2026-07-04", "oneway_combo",
        )
        assert len(deals) == 1
        assert deals[0]["is_mixed_airline"] is True
        assert deals[0]["trip_type"] == "oneway_combo"

    def test_min_price_is_leg_sum_and_sorted(self):
        deals = combine_legs(
            [_out_leg(price=100000), _out_leg(price=150000)],
            [_in_leg(price=120000)],
            "2026-07-01", "2026-07-04", None,
        )
        assert [d["min_price"] for d in deals] == [220000, 270000]

    def test_last_checked_at_is_max_of_legs(self):
        deals = combine_legs(
            [_out_leg()], [_in_leg()],
            "2026-07-01", "2026-07-04", None,
        )
        assert deals[0]["last_checked_at"] == datetime(2026, 6, 1, 13, 0).isoformat()
