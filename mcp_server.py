# mcp_server.py
#
# Claude Desktop용 MCP 서버.
# 항공권 최저가 조회, 가격 추이, 딜 상세 설명 기능 제공.
#
# 실행: python mcp_server.py (stdio transport)

import os
from datetime import datetime

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

_DSN = os.environ["DATABASE_URL"]

mcp = FastMCP("flight-friend")


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
    limit: int = 10,
) -> list[dict]:
    """목적지/월별 최저가 항공권 조회.

    Args:
        destination: 공항코드 (예: NRT, KIX). None이면 전체.
        month: YYYY-MM 형식 (예: 2026-05). None이면 전체.
        limit: 반환 건수 (기본 10).
    """
    conditions = []
    params: list = []

    if destination:
        conditions.append("destination = %s")
        params.append(destination.upper())
    if month:
        conditions.append("departure_date LIKE %s")
        params.append(f"{month}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    return _query(f"""
        SELECT destination, destination_name, departure_date, return_date,
               stay_nights, min_price, source, out_airline, in_airline,
               last_checked_at
        FROM v_best_observed
        {where}
        ORDER BY min_price ASC
        LIMIT %s
    """, tuple(params))


@mcp.tool()
def get_price_history(
    destination: str,
    departure_date: str | None = None,
    return_date: str | None = None,
    month: str | None = None,
) -> list[dict]:
    """특정 노선의 가격 추이 조회.

    Args:
        destination: 공항코드 (예: NRT).
        departure_date: 출발일 (YYYY-MM-DD). return_date와 함께 사용하면 특정 여정의 수집 시점별 추이.
        return_date: 귀국일 (YYYY-MM-DD).
        month: YYYY-MM 형식. 해당 월 출발일별 최저가 요약.
    """
    dest = destination.upper()

    if departure_date and return_date:
        return _query("""
            SELECT DATE(checked_at)::text AS check_date, source,
                   MIN(price) AS min_price
            FROM price_history
            WHERE destination = %s AND departure_date = %s AND return_date = %s
            GROUP BY DATE(checked_at), source
            ORDER BY check_date
        """, (dest, departure_date, return_date))

    if month:
        return _query("""
            SELECT departure_date, source, MIN(price) AS min_price
            FROM price_history
            WHERE destination = %s AND departure_date LIKE %s
            GROUP BY departure_date, source
            ORDER BY departure_date
        """, (dest, f"{month}%"))

    return _query("""
        SELECT departure_date, return_date, source, MIN(price) AS min_price
        FROM price_history
        WHERE destination = %s
        GROUP BY departure_date, return_date, source
        ORDER BY min_price ASC
        LIMIT 20
    """, (dest,))


@mcp.tool()
def explain_deal(
    destination: str,
    departure_date: str,
    return_date: str,
) -> dict:
    """특정 여정의 상세 정보 및 과거 대비 분석.

    Args:
        destination: 공항코드 (예: NRT).
        departure_date: 출발일 (YYYY-MM-DD).
        return_date: 귀국일 (YYYY-MM-DD).
    """
    dest = destination.upper()

    current = _query("""
        SELECT * FROM v_best_observed
        WHERE destination = %s AND departure_date = %s AND return_date = %s
        ORDER BY min_price ASC
        LIMIT 5
    """, (dest, departure_date, return_date))

    history = _query("""
        SELECT DATE(checked_at)::text AS check_date,
               MIN(price) AS min_price, MAX(price) AS max_price,
               COUNT(*) AS observations
        FROM price_history
        WHERE destination = %s AND departure_date = %s AND return_date = %s
        GROUP BY DATE(checked_at)
        ORDER BY check_date
    """, (dest, departure_date, return_date))

    route_avg = _query("""
        SELECT AVG(price)::int AS avg_price, MIN(price) AS all_time_low,
               COUNT(*) AS total_observations
        FROM price_history
        WHERE destination = %s AND LEFT(departure_date, 7) = LEFT(%s, 7)
    """, (dest, departure_date))

    return {
        "current_best": current,
        "price_history": history,
        "route_context": route_avg[0] if route_avg else None,
    }


if __name__ == "__main__":
    mcp.run()
