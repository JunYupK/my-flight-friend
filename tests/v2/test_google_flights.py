# tests/v2/test_google_flights.py

import asyncio
import base64
import os
import sys
from datetime import date

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flight_friend.providers.google_flights import (
    build_oneway_url,
    build_roundtrip_url,
    cards_to_legs,
    parse_cards,
    search_oneway,
)

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "gf_cards.html")


def _decode_tfs(url: str) -> bytes:
    tfs = url.split("tfs=", 1)[1].split("&", 1)[0]
    padded = tfs + "=" * (-len(tfs) % 4)
    return base64.urlsafe_b64decode(padded)


def test_oneway_url_structure():
    url = build_oneway_url("ICN", "FUK", date(2026, 10, 21))
    tfs = url.split("tfs=", 1)[1].split("&", 1)[0]
    assert tfs.startswith("CBwQAh")
    assert "curr=KRW" in url
    assert "hl=ko" in url

    raw = _decode_tfs(url)
    assert b"2026-10-21" in raw
    assert b"ICN" in raw
    assert b"FUK" in raw
    assert b"\x98\x01\x02" in raw  # field19 (trip type) = 2 (oneway)


def test_roundtrip_url_has_two_legs_and_trip_1():
    url = build_roundtrip_url("ICN", "FUK", date(2026, 10, 21), date(2026, 10, 25))
    raw = _decode_tfs(url)

    assert b"2026-10-21" in raw
    assert b"2026-10-25" in raw
    assert raw.count(b"ICN") == 2  # outbound dep + return arr
    assert raw.count(b"FUK") == 2  # outbound arr + return dep
    assert b"\x98\x01\x01" in raw  # field19 (trip type) = 1 (roundtrip)


def test_parse_cards_from_fixture():
    with open(_FIXTURE, encoding="utf-8") as f:
        html = f.read()
    cards = parse_cards(html)

    assert len(cards) == 4  # 3건 + LJ 271 중복 1건
    prices = sorted(c["price"] for c in cards)
    assert prices == [116700, 118900, 129800, 129800]
    assert all(c["dep_airport"] == "ICN" and c["arr_airport"] == "FUK" for c in cards)


def test_dedupe_same_flight():
    with open(_FIXTURE, encoding="utf-8") as f:
        html = f.read()
    cards = parse_cards(html)

    legs = cards_to_legs(cards, date(2026, 10, 21), "ICN", "FUK", "https://example.com")

    # 4장 카드 중 진에어(LJ 271) 2장은 동일 flight_key → 1건으로 합쳐져 총 3건
    assert len(legs) == 3
    lj_legs = [leg for leg in legs if leg.airline_iata == "LJ"]
    assert len(lj_legs) == 1
    assert lj_legs[0].price == 129800


def test_legs_sorted_by_price_and_airline_from_flight_number():
    with open(_FIXTURE, encoding="utf-8") as f:
        html = f.read()
    cards = parse_cards(html)

    legs = cards_to_legs(cards, date(2026, 10, 21), "ICN", "FUK", "https://example.com")

    assert [leg.price for leg in legs] == sorted(leg.price for leg in legs)
    by_iata = {leg.airline_iata: leg for leg in legs}
    assert by_iata["RS"].price == 116700
    assert by_iata["7C"].price == 118900
    assert by_iata["LJ"].price == 129800
    assert by_iata["RS"].flight_numbers == ["RS 727"]


class _FakeResult:
    def __init__(self, success: bool, html: str | None = None, error_message: str | None = None):
        self.success = success
        self.html = html
        self.error_message = error_message


class _FakeCrawler:
    def __init__(self, result=None, exc: Exception | None = None):
        self._result = result
        self._exc = exc

    async def arun(self, *, url: str, config: object):
        if self._exc is not None:
            raise self._exc
        return self._result


def test_status_mapping():
    with open(_FIXTURE, encoding="utf-8") as f:
        fixture_html = f.read()

    # 카드 있음 → ok
    crawler_ok = _FakeCrawler(_FakeResult(success=True, html=fixture_html))
    result_ok = asyncio.run(
        search_oneway(crawler_ok, "ICN", "FUK", date(2026, 10, 21), config=object())
    )
    assert result_ok.status == "ok"
    assert len(result_ok.legs) == 3

    # 카드 0 + "unusual traffic" → blocked
    crawler_blocked = _FakeCrawler(
        _FakeResult(success=True, html="<html>unusual traffic detected</html>")
    )
    result_blocked = asyncio.run(
        search_oneway(crawler_blocked, "ICN", "FUK", date(2026, 10, 21), config=object())
    )
    assert result_blocked.status == "blocked"

    # 카드 0 + "captcha"만 (정상 페이지에도 존재) → empty (차단으로 오판 금지)
    crawler_empty = _FakeCrawler(
        _FakeResult(success=True, html="<html>...captcha...</html>")
    )
    result_empty = asyncio.run(
        search_oneway(crawler_empty, "ICN", "FUK", date(2026, 10, 21), config=object())
    )
    assert result_empty.status == "empty"

    # 예외 → error, 메시지 보존
    crawler_error = _FakeCrawler(exc=RuntimeError("boom"))
    result_error = asyncio.run(
        search_oneway(crawler_error, "ICN", "FUK", date(2026, 10, 21), config=object())
    )
    assert result_error.status == "error"
    assert result_error.error == "boom"
