# ruff: noqa: BLE001 — 일회성 spike 스크립트 (M2 계획 후 삭제)
"""Naver 항공권 내부 API 프로브 — 브라우저 없이 searchFlights 를 직접 호출한다.

2026-09-30 spike 에서 확인한 사실:
  POST https://flight-api.naver.com/flight/international/searchFlights
  응답은 SSE(text/event-stream) `data: {...}` 줄 여러 개. 마지막 줄이 누적 스냅샷
  (status.isCompleted, completedPartnerCount/requestedPartnerCount).
  쿠키·토큰 불필요. 한 번에 6~10초.

사용 (OCI worker 컨테이너 — httpx 포함):
  python naver_spike.py --dep ICN --arr FUK --date 2026-11-12
  python naver_spike.py --dep FUK --arr ICN --date 2026-11-16 --save /out/fuk_icn.json
"""

import argparse
import json
import time

import httpx

API = "https://flight-api.naver.com/flight/international/searchFlights"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def body(dep: str, arr: str, date_compact: str) -> dict:
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
                "departureDate": date_compact,
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dep", default="ICN")
    ap.add_argument("--arr", default="FUK")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--save", default=None, help="마지막 스냅샷 JSON 저장 경로")
    args = ap.parse_args()

    headers = {
        "content-type": "application/json",
        "accept": "text/event-stream",
        "origin": "https://flight.naver.com",
        "referer": "https://flight.naver.com/",
        "accept-language": "ko-KR",
        "user-agent": UA,
    }
    t0 = time.monotonic()
    chunks: list[dict] = []
    status_code = None
    error = ""
    try:
        with httpx.stream(
            "POST", API, json=body(args.dep, args.arr, args.date.replace("-", "")),
            headers=headers, timeout=60,
        ) as r:
            status_code = r.status_code
            for line in r.iter_lines():
                if line.startswith("data:"):
                    chunks.append(json.loads(line[5:]))
    except Exception as e:
        error = f"{type(e).__name__}: {e}"[:300]
    seconds = round(time.monotonic() - t0, 1)

    print(f"http {status_code}  {seconds}s  chunks {len(chunks)}  error {error or '-'}")
    if not chunks:
        return
    last = chunks[-1]
    st = last.get("status", {})
    print(
        f"completed {st.get('isCompleted')}  partners "
        f"{st.get('completedPartnerCount')}/{st.get('requestedPartnerCount')}  "
        f"itineraries {len(last.get('itineraries', []))}  fareMappings {len(last.get('fareMappings', []))}"
    )
    its = {i["itineraryId"]: i for i in last.get("itineraries", [])}
    rows = []
    for m in last.get("fareMappings", []):
        segs = its[m["itineraryIds"]]["segments"]
        a, z = segs[0], segs[-1]
        base = [f["adult"]["totalFare"] for f in m["fares"] if f["fareType"] == "A01"]
        rows.append((
            min(base) if base else None,
            min(f["adult"]["totalFare"] for f in m["fares"]),
            "/".join(s["marketingCarrier"]["airlineCode"] + s["marketingCarrier"]["flightNumber"] for s in segs),
            f"{a['departure']['airportCode']} {a['departure']['time']} → {z['arrival']['airportCode']} {z['arrival']['time']}",
            len(segs) - 1,
            len(m["fares"]),
        ))
    rows.sort(key=lambda r: r[0] or 10**9)
    print("cheapest 10 (A01 unconditional / any incl. card / flight / route / stops / fares):")
    for r in rows[:10]:
        print("  ", *r)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(last, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
