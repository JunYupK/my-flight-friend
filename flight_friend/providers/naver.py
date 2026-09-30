# flight_friend/providers/naver.py
#
# Naver 항공권 어댑터: SSE 검색 API(POST) → LegQuote 변환 (편도).
# 스펙 §3.1·3.2·3.3·3.4. 왕복(search_roundtrip)은 _post_search/_itinerary_ok/_fares 를 재사용한다.

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import date
from urllib.parse import quote

import httpx

from flight_friend.config import NAVER_ONEWAY_TIMEOUT, NAVER_ROUNDTRIP_TIMEOUT
from flight_friend.providers.airlines import flight_key
from flight_friend.types import LegQuote, ProviderResult, RtQuote

PROVIDER = "naver"
API_URL = "https://flight-api.naver.com/flight/international/searchFlights"

_HEADERS = {
    "content-type": "application/json",
    "accept": "text/event-stream",
    "origin": "https://flight.naver.com",
    "referer": "https://flight.naver.com/",
    "accept-language": "ko-KR",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
}
_HHMM = re.compile(r"^\d{2}:\d{2}$")
_WEB = "https://flight.naver.com/flights/international"


def _compact(d: date) -> str:
    return d.strftime("%Y%m%d")


def build_search_url(dep: str, arr: str, date_: date) -> str:
    return (
        f"{_WEB}/{dep}:airport-{arr}:airport-{_compact(date_)}"
        "?adult=1&isDirect=false&fareType=Y&tripType=OW"
    )


def build_booking_url(
    dep: str, arr: str, date_: date, itinerary_id: str, fare_type: str, airline: str,
) -> str:
    selected = quote(f"1:{itinerary_id}:{fare_type}:HK:{airline}:", safe="")
    return (
        f"{_WEB}/detail/{dep}:airport-{arr}:airport-{_compact(date_)}"
        "?adult=1&isDirect=false&fareType=Y&selectType=concurrent"
        f"&selectedFlight={selected}"
    )


def _oneway_body(dep: str, arr: str, date_: date) -> dict:
    return {
        "tripType": "OW",
        "device": "pc",
        "seatClass": "Y",
        "adultCount": 1,
        "childCount": 0,
        "infantCount": 0,
        "isNonstop": False,
        "openReturnDays": 0,
        "initialRequest": True,
        "itineraries": [
            {
                "departureLocationCode": dep,
                "arrivalLocationCode": arr,
                "departureLocationType": "airport",
                "arrivalLocationType": "airport",
                "departureDate": _compact(date_),
            }
        ],
        "flightFilter": {
            "filter": {
                "airlines": [], "departureAirports": [], "arrivalAirports": [],
                "departureTime": [], "fareTypes": [], "flightDurationSeconds": [],
                "hasCardBenefit": True, "isIndividual": False, "isLowCarbonEmission": False,
                "isSameAirlines": False, "isSameDepArrAirport": False, "isTravelClub": False,
                "minFare": {}, "viaCount": [], "selectedItineraries": [],
            },
            "limit": 200,
            "skip": 0,
            "sort": {"adultMinFare": 1},
        },
    }


def _roundtrip_body(dep: str, arr: str, out_date: date, ret_date: date) -> dict:
    body = _oneway_body(dep, arr, out_date)
    body["tripType"] = "RT"
    body["itineraries"].append(
        {
            "departureLocationCode": arr,
            "arrivalLocationCode": dep,
            "departureLocationType": "airport",
            "arrivalLocationType": "airport",
            "departureDate": _compact(ret_date),
        }
    )
    return body


# --- 호출 + 상태 판정 (스펙 §3.4) ------------------------------------------


async def _post_search(
    client: httpx.AsyncClient, body: dict, timeout: float,
) -> tuple[str, dict | None, str | None]:
    """(status, 마지막 스냅샷 | None, error). 스냅샷이 있으면 status는 "ok"(임시)."""
    try:
        resp = await asyncio.wait_for(
            client.post(API_URL, json=body, headers=_HEADERS, timeout=timeout), timeout
        )
    except TimeoutError:  # 단계별 타임아웃이 아닌 전체 상한
        return "error", None, "timeout"
    except Exception as e:  # noqa: BLE001 - 네트워크/타임아웃 전부 error
        return "error", None, f"{type(e).__name__}: {e}"[:300]
    if resp.status_code in (403, 429):
        return "blocked", None, f"http {resp.status_code}"
    if resp.status_code >= 400:
        return "error", None, f"http {resp.status_code}"
    data_lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    if not data_lines:
        return "blocked", None, "non-json response"
    try:
        snapshot = json.loads(data_lines[-1][5:])
    except ValueError:
        return "blocked", None, "non-json response"
    if not isinstance(snapshot, dict):
        return "blocked", None, "non-json response"
    return "ok", snapshot, None


def _partner_note(snapshot: dict) -> str | None:
    st = snapshot.get("status") or {}
    if st.get("isCompleted") is False:
        return f"partners {st.get('completedPartnerCount')}/{st.get('requestedPartnerCount')}"
    return None


# --- 파싱 부품 ------------------------------------------------------------


def _hhmm(raw: object) -> str | None:
    if not isinstance(raw, str) or len(raw) != 4:
        return None
    text = f"{raw[:2]}:{raw[2:]}"
    return text if _HHMM.match(text) else None


def _itinerary_ok(segments: list[dict], dep: str, arr: str) -> bool:
    """코드셰어 제외, 출발·도착 공항 일치, 시각 HHMM 형식 검증."""
    if not segments:
        return False
    for seg in segments:
        if not isinstance(seg, dict):
            return False
        mk = (seg.get("marketingCarrier") or {}).get("airlineCode")
        number = (seg.get("marketingCarrier") or {}).get("flightNumber")
        if not mk or number is None or not str(number).strip():
            return False
        op = (seg.get("operatingCarrier") or {}).get("airlineCode")
        if op and op != mk:
            return False
        for side in ("departure", "arrival"):
            if _hhmm((seg.get(side) or {}).get("time")) is None:
                return False
    if segments[0]["departure"].get("airportCode") != dep:
        return False
    return segments[-1]["arrival"].get("airportCode") == arr


def _fares(
    fares: list[dict], fare_type_map: dict,
) -> tuple[int | None, int | None, str | None, str | None]:
    """(A01 최저, 더 싼 조건부 최저 | None, 조건 라벨, 조건 fareType)."""
    base: int | None = None
    cond: tuple[int, str] | None = None
    for fare in fares or []:
        ft = fare.get("fareType") or ""
        try:
            total = int((fare.get("adult") or {})["totalFare"])
        except (KeyError, TypeError, ValueError):
            continue
        if ft == "A01":
            if base is None or total < base:
                base = total
        elif ft.startswith("A01/") and (cond is None or total < cond[0]):
            cond = (total, ft)
    if base is None or cond is None or cond[0] >= base:
        return base, None, None, None
    name = (fare_type_map.get(cond[1]) or {}).get("name")
    label = name.removeprefix("성인/") if isinstance(name, str) and name else cond[1]
    return base, cond[0], label, cond[1]


def _flight_no(seg: dict) -> str:
    mk = seg["marketingCarrier"]
    return f"{mk['airlineCode']} {str(mk['flightNumber']).lstrip('0') or '0'}"


def _candidates(snapshot: dict):
    """fareMappings와 sameFareMappings를 평탄화: (itineraryIds, fares)."""
    for fm in snapshot.get("fareMappings") or []:
        yield fm.get("itineraryIds"), fm.get("fares")
        for same in fm.get("sameFareMappings") or []:
            yield same.get("itineraryIds"), same.get("fares")


def _snapshot_to_legs(snapshot: dict, dep: str, arr: str, date_: date) -> list[LegQuote]:
    status = snapshot.get("status") or {}
    airline_names = status.get("airlinesCodeMap") or {}
    fare_type_map = status.get("fareTypesCodeMap") or {}
    itineraries = {
        it["itineraryId"]: it
        for it in snapshot.get("itineraries") or []
        if isinstance(it, dict) and "itineraryId" in it
    }
    search_url = build_search_url(dep, arr, date_)
    best: dict[str, LegQuote] = {}
    for itinerary_id, fares in _candidates(snapshot):
        it = itineraries.get(itinerary_id)
        if it is None:
            continue
        segments = it.get("segments") or []
        if not _itinerary_ok(segments, dep, arr):
            continue
        price, cond_price, cond_label, cond_type = _fares(fares, fare_type_map)
        if price is None:
            continue
        airline = segments[0]["marketingCarrier"]["airlineCode"]
        stops = len(segments) - 1 + sum(len(s.get("hiddenStops") or []) for s in segments)
        dep_time = _hhmm(segments[0]["departure"]["time"])
        arr_time = _hhmm(segments[-1]["arrival"]["time"])
        key = flight_key(date_, dep, arr, dep_time, arr_time, stops, airline)
        existing = best.get(key)
        if existing is not None and existing.price <= price:
            continue
        duration = it.get("duration")
        best[key] = LegQuote(
            flight_key=key,
            airline_iata=airline,
            airline_name=airline_names.get(airline) or airline,
            flight_numbers=[_flight_no(s) for s in segments],
            dep_airport=dep,
            arr_airport=arr,
            dep_time=dep_time,
            arr_time=arr_time,
            duration_min=duration // 60 if isinstance(duration, int) else None,
            stops=stops,
            price=price,
            booking_url=build_booking_url(dep, arr, date_, itinerary_id, "A01", airline),
            search_url=search_url,
            cond_price=cond_price,
            cond_label=cond_label,
            cond_booking_url=(
                build_booking_url(dep, arr, date_, itinerary_id, cond_type, airline)
                if cond_type
                else None
            ),
        )
    return sorted(best.values(), key=lambda leg: leg.price)


async def search_oneway(
    client: httpx.AsyncClient, dep: str, arr: str, date_: date,
) -> ProviderResult:
    t0 = time.perf_counter()
    status, snapshot, error = await _post_search(
        client, _oneway_body(dep, arr, date_), NAVER_ONEWAY_TIMEOUT,
    )
    if snapshot is None:
        return ProviderResult(status, [], [], error, time.perf_counter() - t0)  # type: ignore[arg-type]
    legs = _snapshot_to_legs(snapshot, dep, arr, date_)
    seconds = time.perf_counter() - t0
    if not legs:
        return ProviderResult("empty", [], [], None, seconds)
    return ProviderResult("ok", legs, [], _partner_note(snapshot), seconds)


def _snapshot_to_rts(snapshot: dict, dep: str, arr: str, out_date: date) -> list[RtQuote]:
    status = snapshot.get("status") or {}
    fare_type_map = status.get("fareTypesCodeMap") or {}
    itineraries = {
        it["itineraryId"]: it
        for it in snapshot.get("itineraries") or []
        if isinstance(it, dict) and "itineraryId" in it
    }
    rts: list[RtQuote] = []
    for pair_id, fares in _candidates(snapshot):
        parts = pair_id.split("-") if isinstance(pair_id, str) else []
        if len(parts) != 2:
            continue
        out_it, in_it = itineraries.get(parts[0]), itineraries.get(parts[1])
        if out_it is None or in_it is None:
            continue
        out_segs = out_it.get("segments") or []
        in_segs = in_it.get("segments") or []
        if not _itinerary_ok(out_segs, dep, arr):
            continue
        if not _itinerary_ok(in_segs, arr, dep):
            continue
        # "이 항공사 왕복" 조합만: 오는편 첫 구간 항공사가 가는편과 다르면 제외.
        if in_segs[0]["marketingCarrier"]["airlineCode"] != out_segs[0]["marketingCarrier"]["airlineCode"]:
            continue
        price, cond_price, cond_label, _ = _fares(fares, fare_type_map)
        if price is None:
            continue
        airline = out_segs[0]["marketingCarrier"]["airlineCode"]
        stops = len(out_segs) - 1 + sum(len(s.get("hiddenStops") or []) for s in out_segs)
        key = flight_key(
            out_date, dep, arr,
            _hhmm(out_segs[0]["departure"]["time"]),
            _hhmm(out_segs[-1]["arrival"]["time"]),
            stops, airline,
        )
        rts.append(RtQuote(airline, key, price, cond_price, cond_label))
    return sorted(rts, key=lambda rt: rt.total_price)


async def search_roundtrip(
    client: httpx.AsyncClient, dep: str, arr: str, out_date: date, ret_date: date,
) -> ProviderResult:
    t0 = time.perf_counter()
    status, snapshot, error = await _post_search(
        client, _roundtrip_body(dep, arr, out_date, ret_date), NAVER_ROUNDTRIP_TIMEOUT,
    )
    if snapshot is None:
        return ProviderResult(status, [], [], error, time.perf_counter() - t0)  # type: ignore[arg-type]
    rts = _snapshot_to_rts(snapshot, dep, arr, out_date)
    seconds = time.perf_counter() - t0
    if not rts:
        return ProviderResult("empty", [], [], None, seconds)
    return ProviderResult("ok", [], rts, _partner_note(snapshot), seconds)
