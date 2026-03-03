# flight_monitor/collector_amadeus.py

from amadeus import Client, ResponseError
from datetime import datetime, timedelta
import os
from .config import ORIGIN, JAPAN_AIRPORTS, SEARCH_CONFIG

amadeus = Client(
    client_id=os.environ["AMADEUS_CLIENT_ID"],
    client_secret=os.environ["AMADEUS_CLIENT_SECRET"],
)


def fetch_fsc_offers() -> list[dict]:
    results = []
    today = datetime.now()
    request_count = 0
    max_requests = SEARCH_CONFIG["amadeus_max_requests_per_run"]

    for airport_code, airport_name in JAPAN_AIRPORTS.items():
        for days_ahead in range(7, SEARCH_CONFIG["departure_date_range_days"], 21):
            departure = today + timedelta(days=days_ahead)
            dep_str = departure.strftime("%Y-%m-%d")

            for stay in SEARCH_CONFIG["stay_durations"]:
                # 한도 초과 시 조기 종료
                if request_count >= max_requests:
                    print(f"[Amadeus] 요청 한도 도달({max_requests}회), 수집 조기 종료")
                    return results

                ret_str = (departure + timedelta(days=stay)).strftime("%Y-%m-%d")

                try:
                    response = amadeus.shopping.flight_offers_search.get(
                        originLocationCode=ORIGIN,
                        destinationLocationCode=airport_code,
                        departureDate=dep_str,
                        returnDate=ret_str,
                        adults=SEARCH_CONFIG["adults"],
                        currencyCode=SEARCH_CONFIG["currency"],
                        nonStop=SEARCH_CONFIG["nonStop"],
                        max=3,
                    )
                    request_count += 1

                    if not response.data:
                        continue

                    cheapest = min(response.data, key=lambda x: float(x["price"]["grandTotal"]))
                    airline = cheapest["validatingAirlineCodes"][0]
                    if airline not in ["KE", "OZ"]:
                        continue

                    results.append({
                        "source": "amadeus",
                        "trip_type": "round_trip",
                        "origin": ORIGIN,
                        "destination": airport_code,
                        "destination_name": airport_name,
                        "departure_date": dep_str,
                        "return_date": ret_str,
                        "stay_nights": stay,
                        "price": float(cheapest["price"]["grandTotal"]),
                        "currency": SEARCH_CONFIG["currency"],
                        "out_airline": airline,
                        "in_airline": airline,
                        "is_mixed_airline": False,
                        "checked_at": datetime.now().isoformat(),
                    })

                except ResponseError as e:
                    print(f"[Amadeus ERROR] {airport_code} {dep_str}~{ret_str}: {e}")
                    request_count += 1  # 실패도 카운트

    print(f"[Amadeus] 총 {request_count}회 요청 완료")
    return results
