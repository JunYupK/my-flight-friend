"""
네이버 항공권 API PoC — 편도(OW) / 왕복(RT) 둘 다 테스트
실행: python poc_naver.py
"""

import json
import requests
from datetime import date, timedelta

API_URL = "https://flight-api.naver.com/flight/international/searchFlights"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://flight.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def build_payload(origin, dest, dep_date, ret_date=None, trip_type="OW"):
    """
    trip_type: "OW" (편도) 또는 "RT" (왕복)
    dep_date, ret_date: "YYYYMMDD" 형식
    """
    itineraries = [
        {
            "departureLocationCode": origin,
            "departureLocationType": "airport",
            "arrivalLocationCode": dest,
            "arrivalLocationType": "airport",
            "departureDate": dep_date,
        }
    ]
    if trip_type == "RT" and ret_date:
        itineraries.append({
            "departureLocationCode": dest,
            "departureLocationType": "airport",
            "arrivalLocationCode": origin,
            "arrivalLocationType": "airport",
            "departureDate": ret_date,
        })

    return {
        "adultCount": 1,
        "childCount": 0,
        "infantCount": 0,
        "device": "pc",
        "isNonstop": False,
        "seatClass": "Y",
        "tripType": trip_type,
        "itineraries": itineraries,
        "openReturnDays": 0,
        "flightFilter": {
            "filter": {
                "airlines": [],
                "departureAirports": [[origin], [dest]] if trip_type == "RT" else [[origin]],
                "arrivalAirports": [[dest], [origin]] if trip_type == "RT" else [[dest]],
                "departureTime": [],
                "fareTypes": [],
                "flightDurationSeconds": [],
                "hasCardBenefit": False,
                "isIndividual": False,
                "isLowCarbonEmission": False,
                "isSameAirlines": False,
                "isSameDepArrAirport": True,
                "isTravelClub": False,
                "minFare": {},
                "viaCount": [],
                "selectedItineraries": [],
            },
            "limit": 20,
            "skip": 0,
            "sort": {"adultMinFare": 1},
        },
        "initialRequest": False,
    }


def parse_sse(response):
    """SSE 스트림에서 마지막 유효 데이터 추출"""
    last_data = None
    for line in response.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            raw = line[5:].strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                if parsed.get("itineraries") and parsed.get("fareMappings"):
                    last_data = parsed
            except json.JSONDecodeError:
                pass
    return last_data


def print_results(data, trip_type):
    if not data:
        print("  → 응답 없음 (data=None)")
        return

    itineraries = data.get("itineraries", [])
    fare_mappings = data.get("fareMappings", [])
    print(f"  → itineraries: {len(itineraries)}개, fareMappings: {len(fare_mappings)}개")

    # itinerary 맵
    itin_map = {it["itineraryId"]: it for it in itineraries}

    for i, fm in enumerate(fare_mappings[:5]):  # 상위 5개만
        ids = fm.get("itineraryIds", "")
        fares = fm.get("fares", [])
        best = min((f["adult"]["totalFare"] for f in fares if f.get("adult", {}).get("totalFare")), default=0)

        parts = ids.split("-")
        segments_info = []
        for pid in parts:
            itin = itin_map.get(pid)
            if not itin:
                continue
            segs = itin.get("segments", [])
            if segs:
                first = segs[0]
                last = segs[-1]
                dep = first.get("departure", {})
                arr = last.get("arrival", {})
                airline = first.get("marketingCarrier", {}).get("airlineCode", "??")
                flight_no = first.get("marketingCarrier", {}).get("flightNumber", "")
                stops = len(segs) - 1
                duration = itin.get("duration", 0)
                segments_info.append(
                    f"{airline}{flight_no} "
                    f"{dep.get('airportCode','?')} {dep.get('time','?')[:5]} → "
                    f"{arr.get('airportCode','?')} {arr.get('time','?')[:5]} "
                    f"({duration}분, {stops}경유)"
                )

        print(f"  [{i+1}] ₩{best:,}  |  {' / '.join(segments_info)}")
        # fareMapping에서 파트너 정보
        partners = [f"{f.get('partnerCode','?')}({f['adult']['totalFare']:,})" for f in fares[:3]]
        print(f"       파트너: {', '.join(partners)}")


def test_search(origin, dest, dep_date, ret_date=None, trip_type="OW"):
    label = f"{trip_type} {origin}→{dest} {dep_date}"
    if ret_date:
        label += f" ~ {ret_date}"
    print(f"\n{'='*60}")
    print(f"[TEST] {label}")
    print(f"{'='*60}")

    payload = build_payload(origin, dest, dep_date, ret_date, trip_type)
    print(f"  payload tripType={trip_type}, itineraries={len(payload['itineraries'])}개")

    try:
        resp = requests.post(API_URL, json=payload, headers=HEADERS, stream=True, timeout=30)
        print(f"  HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"  응답: {resp.text[:500]}")
            return
        data = parse_sse(resp)
        print_results(data, trip_type)
        return data
    except Exception as e:
        print(f"  에러: {e}")
        return None


if __name__ == "__main__":
    # 2주 뒤 날짜로 테스트
    dep = (date.today() + timedelta(days=14)).strftime("%Y%m%d")
    ret = (date.today() + timedelta(days=17)).strftime("%Y%m%d")

    # --- 1) 편도 테스트 ---
    test_search("ICN", "NRT", dep, trip_type="OW")

    # --- 2) 왕복 테스트 ---
    test_search("ICN", "NRT", dep, ret, trip_type="RT")

    # --- 3) 귀국편 편도 테스트 ---
    test_search("NRT", "ICN", ret, trip_type="OW")

    print("\n✅ PoC 완료")
