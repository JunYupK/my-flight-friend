# tests/test_offer_utils.py
#
# combine_roundtrips() 순수 단위 테스트 (DB 불필요)

from flight_monitor.offer_utils import combine_roundtrips

REQUIRED_OFFER_KEYS = {
    "source", "trip_type", "origin", "destination", "destination_name",
    "departure_date", "return_date", "stay_nights", "price", "currency",
    "out_airline", "in_airline", "is_mixed_airline", "checked_at",
    "out_url", "in_url", "out_price", "in_price",
}


def _leg(date, price, airline="KE", **extra):
    return {"date": date, "price": price, "airline": airline, **extra}


def _combine(outs, ins, **kwargs):
    defaults = dict(
        source="google_flights", origin="ICN",
        destination="NRT", destination_name="도쿄/나리타",
        stay_durations=[3], topk=5,
    )
    defaults.update(kwargs)
    return combine_roundtrips(outs, ins, **defaults)


class TestCombineRoundtrips:
    def test_basic_pairing_by_stay_duration(self):
        offers = _combine(
            [_leg("2026-07-01", 100000)],
            [_leg("2026-07-04", 120000)],
            stay_durations=[3],
        )
        assert len(offers) == 1
        o = offers[0]
        assert o["departure_date"] == "2026-07-01"
        assert o["return_date"] == "2026-07-04"
        assert o["stay_nights"] == 3
        assert o["price"] == 220000
        assert o["out_price"] == 100000
        assert o["in_price"] == 120000

    def test_no_matching_return_date(self):
        offers = _combine(
            [_leg("2026-07-01", 100000)],
            [_leg("2026-07-10", 120000)],
            stay_durations=[3, 4, 5],
        )
        assert offers == []

    def test_required_offer_keys_present(self):
        offers = _combine(
            [_leg("2026-07-01", 100000)],
            [_leg("2026-07-04", 120000)],
        )
        assert REQUIRED_OFFER_KEYS <= set(offers[0].keys())
        assert offers[0]["trip_type"] == "oneway_combo"
        assert offers[0]["currency"] == "KRW"

    def test_topk_truncation_per_date(self):
        outs = [_leg("2026-07-01", 100000 + i * 1000) for i in range(10)]
        ins = [_leg("2026-07-04", 120000)]
        offers = _combine(outs, ins, topk=3)
        # 출발편 10개 중 최저가 3개만 조합에 사용
        assert len(offers) == 3
        assert [o["out_price"] for o in offers] == [100000, 101000, 102000]

    def test_sorted_by_total_price(self):
        outs = [_leg("2026-07-01", 150000), _leg("2026-07-01", 100000)]
        ins = [_leg("2026-07-04", 130000), _leg("2026-07-04", 110000)]
        offers = _combine(outs, ins)
        prices = [o["price"] for o in offers]
        assert prices == sorted(prices)

    def test_mixed_airline_flag(self):
        offers = _combine(
            [_leg("2026-07-01", 100000, airline="KE")],
            [_leg("2026-07-04", 120000, airline="7C")],
        )
        assert offers[0]["is_mixed_airline"] is True
        assert offers[0]["out_airline"] == "KE"
        assert offers[0]["in_airline"] == "7C"

    def test_same_airline_not_mixed(self):
        offers = _combine(
            [_leg("2026-07-01", 100000, airline="KE")],
            [_leg("2026-07-04", 120000, airline="KE")],
        )
        assert offers[0]["is_mixed_airline"] is False

    def test_empty_airline_not_mixed(self):
        offers = _combine(
            [_leg("2026-07-01", 100000, airline="")],
            [_leg("2026-07-04", 120000, airline="KE")],
        )
        assert offers[0]["is_mixed_airline"] is False

    def test_allow_mixed_airline_false_filters(self):
        outs = [_leg("2026-07-01", 100000, airline="KE")]
        ins = [
            _leg("2026-07-04", 110000, airline="7C"),
            _leg("2026-07-04", 120000, airline="KE"),
        ]
        offers = _combine(outs, ins, allow_mixed_airline=False)
        assert len(offers) == 1
        assert offers[0]["in_airline"] == "KE"

    def test_booking_url_fallback_to_search_url(self):
        offers = _combine(
            [_leg("2026-07-01", 100000, booking_url="https://booking", search_url="https://search-out")],
            [_leg("2026-07-04", 120000, search_url="https://search-in")],
        )
        assert offers[0]["out_url"] == "https://booking"
        assert offers[0]["in_url"] == "https://search-in"

    def test_url_none_when_absent(self):
        offers = _combine(
            [_leg("2026-07-01", 100000)],
            [_leg("2026-07-04", 120000)],
        )
        assert offers[0]["out_url"] is None
        assert offers[0]["in_url"] is None

    def test_multiple_stay_durations(self):
        outs = [_leg("2026-07-01", 100000)]
        ins = [_leg("2026-07-04", 120000), _leg("2026-07-06", 90000)]
        offers = _combine(outs, ins, stay_durations=[3, 5])
        assert {o["stay_nights"] for o in offers} == {3, 5}
        assert len(offers) == 2

    def test_source_passthrough(self):
        offers = _combine(
            [_leg("2026-07-01", 100000)],
            [_leg("2026-07-04", 120000)],
            source="naver",
        )
        assert offers[0]["source"] == "naver"
