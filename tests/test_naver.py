# tests/test_naver.py

import asyncio
import json
import os
from datetime import date
from urllib.parse import unquote

import httpx
import pytest

from flight_friend.config import NAVER_ROUNDTRIP_TIMEOUT
from flight_friend.providers import naver
from flight_friend.providers.naver import (
    API_URL,
    build_search_url,
    search_oneway,
    search_roundtrip,
)

_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "naver_oneway_icn_fuk.sse"
)
_DATE = date(2026, 11, 12)


def _body() -> str:
    with open(_FIXTURE, encoding="utf-8") as f:
        return f.read()


def _sse_response(body: str) -> httpx.Response:
    return httpx.Response(
        201, headers={"content-type": "text/event-stream"}, content=body.encode()
    )


def _run(handler, dep="ICN", arr="FUK"):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await search_oneway(c, dep, arr, _DATE)

    return asyncio.run(go())


def _fixture_result():
    return _run(lambda req: _sse_response(_body()))


def _leg(result, numbers):
    return next(leg for leg in result.legs if leg.flight_numbers == numbers)


def test_oneway_parses_final_snapshot():
    r = _fixture_result()
    assert r.status == "ok"
    assert r.error is None
    assert len(r.legs) == 8


def test_oneway_drops_codeshare():
    r = _fixture_result()
    assert all("KE 5481" not in leg.flight_numbers for leg in r.legs)


def test_oneway_leg_fields():
    leg = _fixture_result().legs[0]
    assert leg.flight_key == "2026-11-12|ICN|FUK|18:15|19:35|0|ZE"
    assert leg.flight_numbers == ["ZE 649"]
    assert leg.airline_name == "이스타항공"
    assert leg.duration_min == 80
    assert leg.price == 141947
    assert leg.cond_price == 139934
    assert leg.cond_label == "현대 M2/M3 Edition2(이용실적 충족시)"
    prices = [x.price for x in _fixture_result().legs]
    assert prices == sorted(prices)


def test_oneway_cond_only_when_cheaper():
    leg = _leg(_fixture_result(), ["7C 1407"])
    assert leg.price == 151700
    assert leg.cond_price is None
    assert leg.cond_label is None
    assert leg.cond_booking_url is None


def test_oneway_connection_and_same_fare():
    r = _fixture_result()
    leg = _leg(r, ["UO 627", "UO 600"])
    assert leg.stops == 1
    assert leg.duration_min == 845
    assert leg.price == 514758
    assert leg.cond_price is None
    assert _leg(r, ["UO 627", "UO 668"]) is not None


def test_booking_urls():
    leg = _leg(_fixture_result(), ["RS 433"])
    prefix = (
        "https://flight.naver.com/flights/international/detail/"
        "ICN:airport-FUK:airport-20261112?adult=1&isDirect=false&fareType=Y"
        "&selectType=concurrent&selectedFlight="
    )
    assert leg.booking_url.startswith(prefix)
    assert unquote(leg.booking_url).endswith("1:20261112ICNFUKRS0433:A01:HK:RS:")
    assert leg.cond_booking_url.startswith(prefix)
    assert unquote(leg.cond_booking_url).endswith("1:20261112ICNFUKRS0433:A01/B16:HK:RS:")
    expected = (
        "https://flight.naver.com/flights/international/ICN:airport-FUK:airport-20261112"
        "?adult=1&isDirect=false&fareType=Y&tripType=OW"
    )
    assert leg.search_url == build_search_url("ICN", "FUK", _DATE) == expected


def test_request_body_and_headers():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return _sse_response(_body())

    _run(handler)
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == API_URL
    body = json.loads(req.content)
    assert body["tripType"] == "OW"
    assert body["itineraries"][0] == {
        "departureLocationCode": "ICN",
        "arrivalLocationCode": "FUK",
        "departureLocationType": "airport",
        "arrivalLocationType": "airport",
        "departureDate": "20261112",
    }
    assert req.headers["accept"] == "text/event-stream"
    assert req.headers["user-agent"] == (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    )
    assert req.headers["origin"] == "https://flight.naver.com"


def _empty_completed_body() -> str:
    lines = [ln for ln in _body().splitlines() if ln.startswith("data:")]
    snap = json.loads(lines[-1][5:])
    snap["fareMappings"] = []
    return "data: " + json.dumps(snap) + "\n\n"


def _raise_timeout(req):
    raise httpx.ConnectTimeout("boom")


@pytest.mark.parametrize(
    "handler, status, error",
    [
        (lambda r: httpx.Response(403), "blocked", "http 403"),
        (lambda r: httpx.Response(429), "blocked", "http 429"),
        (
            lambda r: httpx.Response(
                200, headers={"content-type": "text/html"}, content=b"<html></html>"
            ),
            "blocked",
            "non-json response",
        ),
        (lambda r: httpx.Response(500), "error", "http 500"),
        (_raise_timeout, "error", None),
        (lambda r: _sse_response(_empty_completed_body()), "empty", None),
    ],
)
def test_status_table(handler, status, error):
    r = _run(handler)
    assert r.status == status
    assert r.legs == []
    if error is not None:
        assert r.error == error
    elif status == "error":
        assert r.error


def test_partial_stream_ok_with_partner_note():
    first = next(ln for ln in _body().splitlines() if ln.startswith("data:"))
    r = _run(lambda req: _sse_response(first + "\n\n"))
    assert r.status == "ok"
    assert len(r.legs) == 2
    assert r.error == "partners 3/20"


def test_flight_number_not_numeric():
    lines = _body().splitlines()
    idx = max(i for i, ln in enumerate(lines) if ln.startswith("data:"))
    snap = json.loads(lines[idx][5:])
    itin = next(i for i in snap["itineraries"] if i["itineraryId"].endswith("RS0433"))
    itin["segments"][0]["marketingCarrier"]["flightNumber"] = "0080A"
    itin["segments"][0]["operatingCarrier"]["flightNumber"] = "0080A"
    lines[idx] = "data: " + json.dumps(snap)
    r = _run(lambda req: _sse_response("\n".join(lines)))
    assert any(
        leg.flight_numbers[0].endswith(" 80A") for leg in r.legs
    ), [leg.flight_numbers for leg in r.legs]


def test_module_constants():
    assert naver.PROVIDER == "naver"


# --- 왕복 ------------------------------------------------------------------

_RT_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "naver_roundtrip_icn_fuk.sse"
)
_RET = date(2026, 11, 16)


def _rt_body() -> str:
    with open(_RT_FIXTURE, encoding="utf-8") as f:
        return f.read()


def _run_rt(handler):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await search_roundtrip(c, "ICN", "FUK", _DATE, _RET)

    return asyncio.run(go())


def _rt_result():
    return _run_rt(lambda req: _sse_response(_rt_body()))


def test_roundtrip_parses_pairs():
    r = _rt_result()
    assert r.status == "ok"
    assert r.legs == []
    assert len(r.rts) == 4
    prices = [x.total_price for x in r.rts]
    assert prices == sorted(prices)


def test_roundtrip_fields():
    r = _rt_result()
    first = r.rts[0]
    assert first.airline_iata == "RS"
    assert first.total_price == 311165
    assert first.cond_total_price == 299000
    assert first.cond_label == "하나카드(이용실적 충족시)"
    rs = first
    assert rs.total_price == 311165
    assert rs.cond_total_price == 299000
    assert rs.cond_label == "하나카드(이용실적 충족시)"


def test_roundtrip_request_body():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return _sse_response(_rt_body())

    _run_rt(handler)
    body = json.loads(seen[0].content)
    assert body["tripType"] == "RT"
    assert len(body["itineraries"]) == 2
    assert body["itineraries"][0]["departureDate"] == "20261112"
    assert body["itineraries"][1] == {
        "departureLocationCode": "FUK",
        "arrivalLocationCode": "ICN",
        "departureLocationType": "airport",
        "arrivalLocationType": "airport",
        "departureDate": "20261116",
    }
    assert seen[0].extensions["timeout"]["read"] == NAVER_ROUNDTRIP_TIMEOUT


def test_roundtrip_excludes_mixed_airline_pair_and_codeshare():
    r = _rt_result()
    assert all(x.airline_iata != "TW" or x.total_price != 303485 for x in r.rts)
    keys = [x.out_flight_key for x in r.rts]
    assert "2026-11-12|ICN|FUK|17:50|19:20|0|TW" not in keys


def _snapshot(body: str) -> tuple[list[str], int, dict]:
    lines = body.splitlines()
    idx = max(i for i, ln in enumerate(lines) if ln.startswith("data:"))
    return lines, idx, json.loads(lines[idx][5:])


def _body_with(mutate) -> str:
    lines, idx, snap = _snapshot(_body())
    mutate(snap)
    lines[idx] = "data: " + json.dumps(snap)
    return "\n".join(lines)


def test_malformed_itinerary_skipped_not_fatal():
    def mutate(snap):
        itin = next(i for i in snap["itineraries"] if i["itineraryId"].endswith("RS0433"))
        del itin["segments"][0]["marketingCarrier"]

    r = _run(lambda req: _sse_response(_body_with(mutate)))
    assert r.status == "ok"
    assert len(r.legs) == 7
    assert all(not leg.flight_numbers[0].startswith("RS 433") for leg in r.legs)


def test_malformed_flight_number_skipped():
    def mutate(snap):
        itin = next(i for i in snap["itineraries"] if i["itineraryId"].endswith("RS0433"))
        del itin["segments"][0]["marketingCarrier"]["flightNumber"]

    r = _run(lambda req: _sse_response(_body_with(mutate)))
    assert r.status == "ok" and len(r.legs) == 7


def test_same_flight_key_keeps_lowest_price():
    def mutate(snap):
        fm = snap["fareMappings"][0]
        dup = json.loads(json.dumps(fm))
        for fare in dup["fares"]:
            fare["adult"]["totalFare"] = int(fare["adult"]["totalFare"]) + 50_000
        dup["sameFareMappings"] = []
        snap["fareMappings"].append(dup)

    base = _fixture_result()
    r = _run(lambda req: _sse_response(_body_with(mutate)))
    assert len(r.legs) == len(base.legs)
    assert [leg.price for leg in r.legs] == [leg.price for leg in base.legs]


def test_candidate_without_a01_fare_dropped():
    def mutate(snap):
        for fm in snap["fareMappings"]:
            fm["fares"] = [f for f in fm["fares"] if f.get("fareType") != "A01"]
            fm["sameFareMappings"] = []

    r = _run(lambda req: _sse_response(_body_with(mutate)))
    assert r.status == "empty" and r.legs == []


def test_total_timeout_covers_stalled_body(monkeypatch):
    monkeypatch.setattr(naver, "NAVER_ONEWAY_TIMEOUT", 0.05)

    async def stall(req: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return _sse_response(_body())

    r = _run(stall)
    assert r.status == "error"
    assert r.error == "timeout"
