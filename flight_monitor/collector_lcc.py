# flight_monitor/collector_lcc.py

import requests
import time
import calendar
from collections import defaultdict
from datetime import datetime, timedelta
from .config import ORIGIN, JAPAN_AIRPORTS, SEARCH_CONFIG, KST

GRAPHQL_URL = "https://airline-api.naver.com/graphql"
NLOG_URL    = "https://nlog.naver.com/n"

GRAPHQL_QUERY = """
query getInternationalList(
    $trip: InternationalList_TripType!,
    $itinerary: [InternationalList_itinerary]!,
    $adult: Int = 1, $child: Int = 0, $infant: Int = 0,
    $fareType: InternationalList_CabinClass!,
    $where: InternationalList_DeviceType = pc,
    $isDirect: Boolean = false, $stayLength: String,
    $galileoKey: String, $galileoFlag: Boolean = true,
    $travelBizKey: String, $travelBizFlag: Boolean = true
) {
    internationalList(input: {
        trip: $trip, itinerary: $itinerary,
        person: {adult: $adult, child: $child, infant: $infant},
        fareType: $fareType, where: $where, isDirect: $isDirect,
        stayLength: $stayLength,
        galileoKey: $galileoKey, galileoFlag: $galileoFlag,
        travelBizKey: $travelBizKey, travelBizFlag: $travelBizFlag
    }) {
        galileoKey galileoFlag travelBizKey travelBizFlag
        totalResCnt resCnt
        results { airlines schedules fares }
    }
}
"""


def _get_session() -> requests.Session:
    session = requests.Session()
    session.post(
        NLOG_URL,
        headers={
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://flight.naver.com",
            "referer": "https://flight.naver.com/",
        },
        json={
            "corp": "naver", "svc": "travel",
            "evts": [{
                "page_url": "https://flight.naver.com/",
                "type": "pageview",
                "page_sti": "search_flights",
                "evt_ts": int(datetime.now(KST).timestamp() * 1000),
            }]
        },
    )
    return session


def _query_flights(session, dep_airport, arr_airport, date_str) -> list[dict]:
    """특정 날짜 편도 항공편 전체 조회 (페이지네이션 처리)"""
    results = []
    galileo_key, galileo_flag = "", True
    travel_biz_key, travel_biz_flag = "", True

    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://flight.naver.com",
        "referer": f"https://flight.naver.com/flights/international/{dep_airport}-{arr_airport}-{date_str}?adult=1&fareType=Y",
    }

    while galileo_flag or travel_biz_flag:
        payload = {
            "query": GRAPHQL_QUERY,
            "variables": {
                "trip": "OW",
                "itinerary": [{"departureAirport": dep_airport, "arrivalAirport": arr_airport, "departureDate": date_str}],
                "adult": SEARCH_CONFIG["adults"],
                "child": 0, "infant": 0,
                "fareType": "Y", "where": "pc", "isDirect": False, "stayLength": "",
                "galileoKey": galileo_key, "galileoFlag": galileo_flag,
                "travelBizKey": travel_biz_key, "travelBizFlag": travel_biz_flag,
            }
        }
        try:
            resp = session.post(GRAPHQL_URL, headers=headers, json=payload, timeout=10)
            data = resp.json()["data"]["internationalList"]
        except Exception as e:
            print(f"[Naver ERROR] {dep_airport}-{arr_airport} {date_str}: {e}")
            break

        for item in data.get("results", []):
            try:
                airline = item["airlines"][0] if item.get("airlines") else ""
                fare    = item["fares"][0]["fare"] if item.get("fares") else 0
                sched   = item["schedules"][0][0] if item.get("schedules") else {}
                results.append({
                    "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                    "airline": airline,
                    "price": int(fare),
                    "dep_time": sched.get("departureTime", ""),
                    "arr_time": sched.get("arrivalTime", ""),
                })
            except Exception:
                continue

        galileo_key     = data.get("galileoKey", "")
        galileo_flag    = data.get("galileoFlag", False)
        travel_biz_key  = data.get("travelBizKey", "")
        travel_biz_flag = data.get("travelBizFlag", False)

        time.sleep(SEARCH_CONFIG["request_delay"])

    return results


def _index_topk_by_date(flights: list[dict], k: int) -> dict[str, list[dict]]:
    by_date = defaultdict(list)
    for f in flights:
        by_date[f["date"]].append(f)
    return {d: sorted(fs, key=lambda x: x["price"])[:k] for d, fs in by_date.items()}


def _combine_roundtrips(out_flights, in_flights) -> list[dict]:
    topk = SEARCH_CONFIG["lcc_topk_per_date"]
    out_idx = _index_topk_by_date(out_flights, topk)
    in_idx  = _index_topk_by_date(in_flights,  topk)

    results = []
    for dep_date, outs in out_idx.items():
        dep_dt = datetime.strptime(dep_date, "%Y-%m-%d")
        for stay in SEARCH_CONFIG["stay_durations"]:
            ret_date = (dep_dt + timedelta(days=stay)).strftime("%Y-%m-%d")
            ins = in_idx.get(ret_date)
            if not ins:
                continue
            for out in outs:
                for ret in ins:
                    is_mixed = out["airline"] != ret["airline"]
                    if is_mixed and not SEARCH_CONFIG["allow_mixed_airline"]:
                        continue
                    results.append({
                        "source": "naver_graphql",
                        "trip_type": "round_trip",
                        "origin": ORIGIN,
                        "departure_date": dep_date,
                        "return_date": ret_date,
                        "stay_nights": stay,
                        "price": out["price"] + ret["price"],
                        "currency": "KRW",
                        "out_airline": out["airline"],
                        "in_airline": ret["airline"],
                        "is_mixed_airline": is_mixed,
                        "out_price": out["price"],
                        "in_price": ret["price"],
                        "checked_at": datetime.now(KST).isoformat(),
                    })

    results.sort(key=lambda x: x["price"])
    return results


def fetch_lcc_offers_for_route(session, airport_code, airport_name, year, month) -> list[dict]:
    days_in_month = calendar.monthrange(year, month)[1]
    out_flights, in_flights = [], []

    for day in range(1, days_in_month + 1):
        date_str = f"{year}{month:02d}{day:02d}"
        out_flights += _query_flights(session, ORIGIN, airport_code, date_str)
        in_flights  += _query_flights(session, airport_code, ORIGIN, date_str)

    offers = _combine_roundtrips(out_flights, in_flights)
    for o in offers:
        o["destination"] = airport_code
        o["destination_name"] = airport_name
    return offers


def fetch_lcc_offers() -> list[dict]:
    session = _get_session()
    all_results = []
    for month_str in SEARCH_CONFIG["search_months"]:
        year, month = map(int, month_str.split("-"))
        for airport_code, airport_name in JAPAN_AIRPORTS.items():
            offers = fetch_lcc_offers_for_route(session, airport_code, airport_name, year, month)
            all_results.extend(offers)
    return all_results
