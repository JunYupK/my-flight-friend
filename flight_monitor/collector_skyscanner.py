# flight_monitor/collector_skyscanner.py

import os
import time
import calendar
import requests
from .config import ORIGIN, JAPAN_AIRPORTS, SEARCH_CONFIG
from .offer_utils import combine_roundtrips

RAPIDAPI_HOST = "skyscanner-skyscanner-flight-search-v1.p.rapidapi.com"
BROWSE_QUOTES_URL = (
    f"https://{RAPIDAPI_HOST}/apiservices/browsequotes/v1.0"
    "/KR/KRW/ko-KR/{origin}-sky/{destination}-sky/{date}"
)


def _fetch_quotes(session, origin, destination, date_str):
    """편도 최저가 quote 조회. date_str: YYYY-MM-DD"""
    url = BROWSE_QUOTES_URL.format(
        origin=origin, destination=destination, date=date_str
    )

    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Skyscanner ERROR] {origin}-{destination} {date_str}: {e}")
        return []

    carriers = {c["CarrierId"]: c["Name"] for c in data.get("Carriers", [])}

    results = []
    for q in data.get("Quotes", []):
        leg = q.get("OutboundLeg")
        if not leg:
            continue
        carrier_ids = leg.get("CarrierIds", [])
        airline = carriers.get(carrier_ids[0], "Unknown") if carrier_ids else "Unknown"
        dep_date = leg.get("DepartureDate", "")[:10]  # "2026-05-01T00:00:00"
        if not dep_date:
            continue
        results.append({
            "date": dep_date,
            "airline": airline,
            "price": int(q.get("MinPrice", 0)),
            "direct": q.get("Direct", False),
        })

    return results


def fetch_skyscanner_offers() -> list[dict]:
    if not os.environ.get("RAPIDAPI_KEY"):
        print("[Skyscanner] RAPIDAPI_KEY 환경변수 없음, 건너뜀")
        return []

    session = requests.Session()
    session.headers.update({
        "X-RapidAPI-Key": os.environ["RAPIDAPI_KEY"],
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    })
    all_results = []
    request_count = 0

    # search_months 미설정 시 수집 스킵 (KeyError 방지)
    search_months = SEARCH_CONFIG.get("search_months", [])
    if not search_months:
        print("[Skyscanner] SEARCH_CONFIG['search_months'] 미설정, 건너뜀")
        return []

    for month_str in search_months:
        year, month = map(int, month_str.split("-"))
        days_in_month = calendar.monthrange(year, month)[1]
        max_days = SEARCH_CONFIG.get("lcc_max_days")
        search_days = min(max_days, days_in_month) if max_days else days_in_month

        for airport_code, airport_name in JAPAN_AIRPORTS.items():
            out_flights, in_flights = [], []

            for day in range(1, search_days + 1):
                date_str = f"{year}-{month:02d}-{day:02d}"

                out_flights += _fetch_quotes(session, ORIGIN, airport_code, date_str)
                request_count += 1
                time.sleep(SEARCH_CONFIG["request_delay"])

                in_flights += _fetch_quotes(session, airport_code, ORIGIN, date_str)
                request_count += 1
                time.sleep(SEARCH_CONFIG["request_delay"])

            offers = combine_roundtrips(
                out_flights, in_flights,
                source="skyscanner", origin=ORIGIN,
                destination=airport_code, destination_name=airport_name,
                stay_durations=SEARCH_CONFIG["stay_durations"],
                topk=SEARCH_CONFIG.get("lcc_topk_per_date", SEARCH_CONFIG["topk_per_date"]),
                allow_mixed_airline=SEARCH_CONFIG["allow_mixed_airline"],
            )
            all_results.extend(offers)
            print(f"[Skyscanner] {airport_name}({airport_code}) {month_str}: {len(offers)}건")

    print(f"[Skyscanner] 총 {request_count}회 요청, {len(all_results)}건 수집 완료")
    return all_results
