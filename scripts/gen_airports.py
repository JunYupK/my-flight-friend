"""공항 검색 목록(flight_front/web/src/data/airports.json) 생성.

OurAirports(퍼블릭 도메인)에서 정기편·IATA 코드가 있는 공항을 후보로 뽑고,
Naver 항공 `locationDetails` GraphQL로 한국어 도시·공항·국가명을 붙인다.
Naver가 모르는 공항은 Naver 수집도 안 되므로 뺀다 (화면의 「직접 입력」으로는 가능).

사용 (네트워크 필요, 결과는 커밋):
    python scripts/gen_airports.py

출력: [[코드, 도시, 공항명, 국가, 도시 영문], ...] — 코드 순.
"""

import csv
import io
import json
import sys
import time
from pathlib import Path

import httpx

OURAIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"
NAVER_GRAPHQL = "https://flight-api.naver.com/graphql"
OUT = Path(__file__).resolve().parent.parent / "flight_front/web/src/data/airports.json"
BATCH = 300
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Referer": "https://flight.naver.com/",
    "Accept-Language": "ko-KR",
    "Content-Type": "application/json",
}
QUERY = """query locationDetails($locations: [LocationDetailInput!]!) {
  locationDetails(locations: $locations) {
    __typename
    ... on Airport { type airportCode airportName cityName cityNameEn countryName }
  }
}"""


def candidate_codes(client: httpx.Client) -> list[str]:
    resp = client.get(OURAIRPORTS_CSV, timeout=60)
    resp.raise_for_status()
    codes = {
        row["iata_code"]
        for row in csv.DictReader(io.StringIO(resp.text))
        if row["iata_code"] and row["scheduled_service"] == "yes"
    }
    return sorted(codes)


def naver_airports(client: httpx.Client, codes: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for i in range(0, len(codes), BATCH):
        body = {
            "operationName": "locationDetails",
            "variables": {"locations": [{"code": c} for c in codes[i : i + BATCH]]},
            "query": QUERY,
        }
        resp = client.post(NAVER_GRAPHQL, json=body, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        for loc in resp.json()["data"]["locationDetails"]:
            if loc.get("type") == "airport":
                rows.append(
                    [loc["airportCode"], loc["cityName"], loc["airportName"], loc["countryName"], loc["cityNameEn"]]
                )
        time.sleep(1)
    return sorted(rows)


def main() -> None:
    with httpx.Client() as client:
        codes = candidate_codes(client)
        rows = naver_airports(client, codes)
    if len(rows) < 1000:
        sys.exit(f"공항이 {len(rows)}개뿐 — Naver 응답이 바뀌었는지 확인 (기존 파일 유지)")
    OUT.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"후보 {len(codes)} → Naver 매칭 {len(rows)} → {OUT}")


if __name__ == "__main__":
    main()
