# mcp_server.py
#
# Claude Desktop용 MCP 서버.
# 3-레이어 파이프라인(flight_legs / raw_legs / price_events) 기반.
#
# 실행: python mcp_server.py (SSE transport, port 8001)

import os
from datetime import datetime

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

_DSN = os.environ["DATABASE_URL"]

mcp = FastMCP("flight-friend", host="0.0.0.0", port=8001)


def _query(sql: str, params: tuple = ()) -> list[dict]:
    conn = psycopg2.connect(_DSN)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@mcp.tool()
def get_best_deals(
    destination: str | None = None,
    month: str | None = None,
    max_stay_nights: int | None = None,
    limit: int = 10,
) -> list[dict]:
    """목적지/월별 왕복 최저가 항공권 조회.

    flight_legs 테이블에서 outbound/inbound 편도 레그를 조합해 왕복 최저가를 반환한다.

    Args:
        destination: 공항코드 (예: NRT, KIX, FUK). None이면 전체 목적지.
        month: YYYY-MM 형식 (예: 2026-05). None이면 전체 기간.
        max_stay_nights: 최대 체류 박수. None이면 제한 없음.
        limit: 반환 건수 (기본 10).
    """
    dest_filter = "AND out.destination = %s" if destination else ""
    month_filter = "AND out.date LIKE %s" if month else ""
    stay_filter = "AND (in_.date::date - out.date::date) <= %s" if max_stay_nights else ""

    params: list = []
    if destination:
        params.append(destination.upper())
    if month:
        params.append(f"{month}%")
    if max_stay_nights:
        params.append(max_stay_nights)
    params.append(limit)

    return _query(f"""
        SELECT
            out.destination,
            out.destination_name,
            out.date        AS departure_date,
            in_.date        AS return_date,
            (in_.date::date - out.date::date) AS stay_nights,
            (out.price + in_.price)           AS total_price,
            out.price                         AS out_price,
            in_.price                         AS in_price,
            out.airline                       AS out_airline,
            in_.airline                       AS in_airline,
            out.best_source                   AS out_source,
            in_.best_source                   AS in_source,
            out.dep_time                      AS out_dep_time,
            out.arr_time                      AS out_arr_time,
            in_.dep_time                      AS in_dep_time,
            in_.arr_time                      AS in_arr_time,
            out.stops                         AS out_stops,
            in_.stops                         AS in_stops,
            out.checked_at                    AS last_checked_at
        FROM (
            SELECT DISTINCT ON (destination, date, airline, dep_time)
                destination, destination_name, date, airline,
                dep_time, arr_time, stops, price, best_source, checked_at
            FROM flight_legs
            WHERE direction = 'out' {dest_filter} {month_filter}
            ORDER BY destination, date, airline, dep_time, price ASC
        ) out
        JOIN (
            SELECT DISTINCT ON (destination, date, airline, dep_time)
                destination, date, airline,
                dep_time, arr_time, stops, price, best_source
            FROM flight_legs
            WHERE direction = 'in'
            ORDER BY destination, date, airline, dep_time, price ASC
        ) in_ ON in_.destination = out.destination
             AND in_.date > out.date
             {stay_filter}
        ORDER BY total_price ASC
        LIMIT %s
    """, tuple(params))


@mcp.tool()
def get_price_history(
    destination: str,
    departure_date: str,
) -> list[dict]:
    """특정 노선 출발일의 가격 변동 이력 조회.

    DB 트리거가 자동 기록하는 price_events 테이블 기반.
    가격이 바뀔 때만 row가 생기므로 실제 변동 이력만 담긴다.

    Args:
        destination: 공항코드 (예: NRT).
        departure_date: 출발일 (YYYY-MM-DD).
    """
    dest = destination.upper()
    return _query("""
        SELECT
            changed_at::text AS changed_at,
            airline,
            source,
            old_price,
            new_price,
            (new_price - COALESCE(old_price, new_price)) AS delta,
            direction
        FROM price_events
        WHERE destination = %s
          AND date = %s
          AND direction = 'out'
        ORDER BY changed_at
    """, (dest, departure_date))


@mcp.tool()
def explain_deal(
    destination: str,
    departure_date: str,
    return_date: str,
) -> dict:
    """특정 왕복 여정의 상세 분석.

    현재 최저가, 가격 변동 이력, 소스별 가격 비교를 종합 반환한다.

    Args:
        destination: 공항코드 (예: NRT).
        departure_date: 출발일 (YYYY-MM-DD).
        return_date: 귀국일 (YYYY-MM-DD).
    """
    dest = destination.upper()

    # 현재 최저 outbound 레그들 (소스별)
    out_legs = _query("""
        SELECT source, best_source, airline, dep_time, arr_time,
               stops, price, booking_url, search_url
        FROM flight_legs
        WHERE destination = %s AND date = %s AND direction = 'out'
        ORDER BY price ASC
        LIMIT 10
    """, (dest, departure_date))

    # 현재 최저 inbound 레그들 (소스별)
    in_legs = _query("""
        SELECT source, best_source, airline, dep_time, arr_time,
               stops, price, booking_url, search_url
        FROM flight_legs
        WHERE destination = %s AND date = %s AND direction = 'in'
        ORDER BY price ASC
        LIMIT 10
    """, (dest, return_date))

    # outbound 가격 변동 이력
    price_history = _query("""
        SELECT changed_at::text, source, airline,
               old_price, new_price,
               (new_price - COALESCE(old_price, new_price)) AS delta
        FROM price_events
        WHERE destination = %s AND date = %s AND direction = 'out'
        ORDER BY changed_at DESC
        LIMIT 20
    """, (dest, departure_date))

    # 이 목적지 이번 달 평균/최저 (맥락용)
    route_ctx = _query("""
        SELECT
            MIN(price)      AS all_time_low,
            AVG(price)::int AS avg_price,
            COUNT(*)        AS leg_count
        FROM flight_legs
        WHERE destination = %s
          AND direction = 'out'
          AND date LIKE %s
    """, (dest, departure_date[:7] + "%"))

    best_total = None
    if out_legs and in_legs:
        best_total = out_legs[0]["price"] + in_legs[0]["price"]

    return {
        "best_total_price": best_total,
        "out_legs": out_legs,
        "in_legs": in_legs,
        "price_history": price_history,
        "route_context": route_ctx[0] if route_ctx else None,
    }


@mcp.tool()
def compare_sources(
    destination: str,
    departure_date: str,
) -> dict:
    """소스별(Naver vs Google Flights) 가격 비교.

    같은 출발일에 대해 소스별 최저가와 항공편 목록을 비교한다.

    Args:
        destination: 공항코드 (예: NRT, KIX).
        departure_date: 출발일 (YYYY-MM-DD).
    """
    dest = destination.upper()

    rows = _query("""
        SELECT
            source,
            COUNT(*)        AS flight_count,
            MIN(price)      AS min_price,
            AVG(price)::int AS avg_price,
            MIN(airline)    AS cheapest_airline,
            MAX(checked_at)::text AS last_updated
        FROM flight_legs
        WHERE destination = %s
          AND date = %s
          AND direction = 'out'
        GROUP BY source
        ORDER BY min_price ASC
    """, (dest, departure_date))

    detail = _query("""
        SELECT source, airline, dep_time, arr_time, stops, price
        FROM flight_legs
        WHERE destination = %s
          AND date = %s
          AND direction = 'out'
        ORDER BY source, price ASC
    """, (dest, departure_date))

    by_source: dict = {}
    for row in detail:
        src = row["source"]
        by_source.setdefault(src, []).append({
            k: v for k, v in row.items() if k != "source"
        })

    price_diff = None
    if len(rows) >= 2:
        price_diff = rows[1]["min_price"] - rows[0]["min_price"]

    return {
        "summary": rows,
        "detail_by_source": by_source,
        "cheapest_source": rows[0]["source"] if rows else None,
        "price_diff_krw": price_diff,
    }


if __name__ == "__main__":
    mcp.run(transport="sse")
