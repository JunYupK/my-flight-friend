# tests/v2/test_airlines.py

import os
import sys
from datetime import date

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flight_friend.providers.airlines import airline_iata, flight_key, normalize_airline

_VARIANT_PAIRS = [
    ("스쿳항공", "스쿠트항공", "TR"),
    ("필리핀항공", "필리핀 항공", "PR"),
    ("Trinity Airways", "티웨이항공", "TW"),
    ("말레이항공", "말레이시아 항공", "MH"),
    ("홍콩 익스프레스항공", "홍콩익스프레스", "UO"),
    ("세부퍼시픽", "세부 퍼시픽 에어", "5J"),
    ("홍콩항공", "홍콩 항공", "HX"),
    ("Batik Air", "바틱에어말레이시아", "OD"),
    ("샤먼항공", "하문항공", "MF"),
    ("동방항공", "중국동방항공", "MU"),
    ("Aero K Airlines", "에어로케이", "RF"),
    ("Sun PhuQuoc Airways", "선 푸꾸옥 항공", "9G"),
]


def test_normalize_variants():
    for name_a, name_b, iata in _VARIANT_PAIRS:
        assert normalize_airline(name_a) == iata
        assert normalize_airline(name_b) == iata


def test_normalize_unknown_returns_none():
    assert normalize_airline("한 에어 시스템") is None
    assert normalize_airline("존재하지않는항공사") is None


def test_airline_from_flight_number_wins():
    assert airline_iata("아무이름", ["LJ 357"]) == "LJ"


def test_airline_iata_falls_back_to_name_when_no_flight_number():
    assert airline_iata("대한항공", []) == "KE"


def test_airline_iata_falls_back_to_unknown_marker():
    assert airline_iata("존재하지않는항공사", []) == "?존재하지않는항공사"


def test_flight_key_without_flight_number():
    key_a = flight_key(date(2026, 10, 21), "ICN", "FUK", "14:25", "16:00", 0, "?항공사A")
    key_b = flight_key(date(2026, 10, 21), "ICN", "FUK", "14:25", "16:00", 0, "?항공사B")

    assert key_a.endswith("?항공사A")
    assert key_b.endswith("?항공사B")
    assert key_a != key_b


def test_flight_key_format():
    key = flight_key(date(2026, 10, 21), "ICN", "FUK", "14:25", "16:00", 0, "RS")
    assert key == "2026-10-21|ICN|FUK|14:25|16:00|0|RS"


def test_flight_key_stops_none_becomes_question_mark():
    key = flight_key(date(2026, 10, 21), "ICN", "FUK", "14:25", "16:00", None, "RS")
    assert key == "2026-10-21|ICN|FUK|14:25|16:00|?|RS"
