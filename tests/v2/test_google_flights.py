# tests/v2/test_google_flights.py

import asyncio
import base64
import os
import sys
from datetime import date

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flight_friend.providers import google_flights
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


def test_status_mapping(monkeypatch):
    # crawl4ai 없이 상태 분기(ok/blocked/empty/error)만 검증: 컨트롤러 재정에 따라
    # _default_config()를 fake config를 반환하는 함수로 monkeypatch해 crawl4ai import를
    # 우회한다. search_oneway 자체의 공개 시그니처(crawler, dep, arr, date_)는 그대로.
    monkeypatch.setattr(google_flights, "_default_config", lambda: object())

    with open(_FIXTURE, encoding="utf-8") as f:
        fixture_html = f.read()

    # 카드 있음 → ok
    crawler_ok = _FakeCrawler(_FakeResult(success=True, html=fixture_html))
    result_ok = asyncio.run(search_oneway(crawler_ok, "ICN", "FUK", date(2026, 10, 21)))
    assert result_ok.status == "ok"
    assert len(result_ok.legs) == 3

    # 카드 0 + "unusual traffic" → blocked
    crawler_blocked = _FakeCrawler(
        _FakeResult(success=True, html="<html>unusual traffic detected</html>")
    )
    result_blocked = asyncio.run(search_oneway(crawler_blocked, "ICN", "FUK", date(2026, 10, 21)))
    assert result_blocked.status == "blocked"

    # 카드 0 + "captcha"만 (정상 페이지에도 존재) → empty (차단으로 오판 금지)
    crawler_empty = _FakeCrawler(
        _FakeResult(success=True, html="<html>...captcha...</html>")
    )
    result_empty = asyncio.run(search_oneway(crawler_empty, "ICN", "FUK", date(2026, 10, 21)))
    assert result_empty.status == "empty"

    # 예외 → error, 메시지 보존
    crawler_error = _FakeCrawler(exc=RuntimeError("boom"))
    result_error = asyncio.run(search_oneway(crawler_error, "ICN", "FUK", date(2026, 10, 21)))
    assert result_error.status == "error"
    assert result_error.error == "boom"


def test_search_oneway_errors_when_crawl4ai_missing():
    # 테스트 venv엔 crawl4ai가 없으므로 monkeypatch 없이 실행하면 _default_config()의
    # 실제 import 경로(ImportError → None)를 그대로 타 "crawl4ai not installed"가 나온다.
    crawler = _FakeCrawler(_FakeResult(success=True, html=""))
    result = asyncio.run(search_oneway(crawler, "ICN", "FUK", date(2026, 10, 21)))
    assert result.status == "error"
    assert result.error == "crawl4ai not installed"
    assert result.seconds == 0.0


def _search_with(monkeypatch, result: _FakeResult):
    monkeypatch.setattr(google_flights, "_default_config", lambda: object())
    return asyncio.run(search_oneway(_FakeCrawler(result), "ICN", "FUK", date(2026, 10, 21)))


def test_wait_timeout_with_block_html_is_blocked(monkeypatch) -> None:
    result = _search_with(
        monkeypatch,
        _FakeResult(
            success=False,
            html="<html>unusual traffic from your network</html>",
            error_message="Page.wait_for_function: Timeout 15000ms exceeded",
        ),
    )
    assert result.status == "blocked"
    assert result.error is None


def test_wait_timeout_with_empty_html_is_empty(monkeypatch) -> None:
    result = _search_with(
        monkeypatch,
        _FakeResult(success=False, html="", error_message="Wait condition failed: Timeout after 15000ms"),
    )
    assert result.status == "empty"


def test_navigation_error_stays_error(monkeypatch) -> None:
    result = _search_with(
        monkeypatch,
        _FakeResult(success=False, html=None, error_message="Page.goto: net::ERR_CONNECTION_RESET"),
    )
    assert result.status == "error"
    assert result.error == "Page.goto: net::ERR_CONNECTION_RESET"


def test_wait_for_js_covers_cards_block_and_no_results() -> None:
    js = google_flights._WAIT_FOR_JS
    assert "li.pIav2d" in js and "unusual traffic" in js and "innerText" in js


def _card(**overrides: object) -> dict:
    card: dict = {
        "price": 100000, "dep_time": "08:00", "arr_time": "10:00", "stops": 0,
        "airline": "KE", "dep_airport": "ICN", "arr_airport": "FUK", "flight_numbers": ["KE 1"],
    }
    card.update(overrides)
    return card


def test_malformed_times_are_skipped() -> None:
    cards = [_card(dep_time="8:00"), _card(arr_time="오전 10:00"), _card(dep_time=None), _card()]
    legs = cards_to_legs(cards, date(2026, 10, 21), "ICN", "FUK", "u")
    assert len(legs) == 1
    assert len(google_flights.cards_to_rts(cards, date(2026, 10, 21), "ICN", "FUK")) == 1


def test_cards_with_other_airports_are_dropped() -> None:
    cards = [_card(dep_airport="GMP"), _card(arr_airport="NRT"), _card(dep_airport=None, arr_airport=None)]
    assert len(cards_to_legs(cards, date(2026, 10, 21), "ICN", "FUK", "u")) == 1
    assert len(google_flights.cards_to_rts(cards, date(2026, 10, 21), "ICN", "FUK")) == 1
