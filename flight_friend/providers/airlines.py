# flight_friend/providers/airlines.py
#
# 항공사 표기(한글/영문/리브랜딩) → IATA 코드 정규화, 항공편 식별키 생성.
# 실패는 항상 "다른 항공편으로 취급"(중복) 쪽으로 기울어야 한다 — 오매칭 금지.

from __future__ import annotations

import re
from datetime import date

# 항공사 표기 → IATA 코드 매핑.
# 비교 시 키/입력 모두 소문자화 + 공백 전부 제거 후 조회한다.
_AIRLINE_IATA: dict[str, str] = {
    # V1 (커밋 d8e0422의 flight_monitor/collector_google_flights.py) 전체 이전
    "대한항공": "KE", "아시아나항공": "OZ",
    "진에어": "LJ", "제주항공": "7C", "티웨이항공": "TW",
    "에어서울": "RS", "에어부산": "BX", "이스타항공": "ZE",
    "일본항공": "JL", "전일본공수": "NH", "ANA": "NH",
    "피치항공": "MM", "Peach": "MM", "피치": "MM",
    "집에어": "ZG", "ZIPAIR": "ZG", "Zipair": "ZG",
    "스프링재팬": "IJ", "Spring Japan": "IJ",
    "중국동방항공": "MU", "중국남방항공": "CZ",
    "에어재팬": "NQ", "Air Japan": "NQ",
    "스타플라이어": "7G", "스카이마크": "BC",
    "배틀스타": "AD",
    # 스펙 §13 실측 표기 차이
    "스쿳항공": "TR", "스쿠트항공": "TR",
    "필리핀항공": "PR", "필리핀 항공": "PR",
    "Trinity Airways": "TW",
    "말레이항공": "MH", "말레이시아 항공": "MH",
    "홍콩 익스프레스항공": "UO", "홍콩익스프레스": "UO",
    "세부퍼시픽": "5J", "세부 퍼시픽 에어": "5J",
    "홍콩항공": "HX", "홍콩 항공": "HX",
    "Batik Air": "OD", "바틱에어말레이시아": "OD",
    "샤먼항공": "MF", "하문항공": "MF",
    "동방항공": "MU",
    "Aero K Airlines": "RF", "에어로케이": "RF",
    "Sun PhuQuoc Airways": "9G", "선 푸꾸옥 항공": "9G",
}

_NORMALIZED_AIRLINE_IATA: dict[str, str] = {
    "".join(name.lower().split()): iata for name, iata in _AIRLINE_IATA.items()
}

_FLIGHT_NUMBER_CARRIER_RE = re.compile(r"^[0-9A-Za-z]{2}$")


def normalize_airline(name: str) -> str | None:
    """항공사 표기(한글/영문/리브랜딩)를 IATA 코드로 정규화. 모르면 None."""
    key = "".join(name.lower().split())
    return _NORMALIZED_AIRLINE_IATA.get(key)


def airline_iata(name: str, flight_numbers: list[str]) -> str:
    """편명이 있으면 첫 편명의 항공사 코드, 없으면 이름 정규화, 그것도 없으면 "?" + 이름."""
    if flight_numbers:
        carrier = flight_numbers[0].split(" ", 1)[0]
        if _FLIGHT_NUMBER_CARRIER_RE.match(carrier):
            return carrier
    normalized = normalize_airline(name)
    if normalized is not None:
        return normalized
    return "?" + "".join(name.split())


def flight_key(
    date_: date,
    dep_airport: str,
    arr_airport: str,
    dep_time: str,
    arr_time: str,
    stops: int | None,
    airline: str,
) -> str:
    """편도 항공편 식별키. stops가 None이면 "?"."""
    stops_str = "?" if stops is None else str(stops)
    return f"{date_.isoformat()}|{dep_airport}|{arr_airport}|{dep_time}|{arr_time}|{stops_str}|{airline}"
