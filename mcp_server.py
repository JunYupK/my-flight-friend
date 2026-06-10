# mcp_server.py
#
# Claude Desktop용 MCP 서버.
# 3-레이어 파이프라인(flight_legs / raw_legs / price_events) 기반.
#
# 실행: python mcp_server.py (SSE transport, port 8001)

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

_DSN = os.environ["DATABASE_URL"]

mcp = FastMCP("flight-friend", host="0.0.0.0", port=8001)


def _query(sql: str, params: tuple = ()) -> list[dict]:
    try:
        conn = psycopg2.connect(_DSN)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SET TIME ZONE 'Asia/Seoul'")
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        return [{"error": str(e)}]


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
    stay_filter = "AND (in_.date::date - out.date::date) <= %s" if max_stay_nights else ""

    params: list = []
    if destination:
        params.append(destination.upper())

    month_filter = ""
    if month:
        # LIKE 대신 range 쿼리로 인덱스 활용
        import calendar
        y, m = int(month[:4]), int(month[5:7])
        last_day = calendar.monthrange(y, m)[1]
        month_start = f"{y:04d}-{m:02d}-01"
        month_end = f"{y:04d}-{m:02d}-{last_day:02d}"
        month_filter = "AND out.date >= %s AND out.date <= %s"
        params.extend([month_start, month_end])

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
            out.checked_at::text              AS last_checked_at
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
    direction: str = "both",
) -> list[dict]:
    """특정 노선 출발일의 가격 변동 이력 조회.

    DB 트리거가 자동 기록하는 price_events 테이블 기반.
    가격이 바뀔 때만 row가 생기므로 실제 변동 이력만 담긴다.

    Args:
        destination: 공항코드 (예: NRT).
        departure_date: 출발일 (YYYY-MM-DD).
        direction: 'out'(출발편), 'in'(귀국편), 'both'(전체, 기본값).
    """
    dest = destination.upper()
    dir_filter = "" if direction == "both" else "AND direction = %s"
    params = [dest, departure_date]
    if direction != "both":
        params.append(direction)

    return _query(f"""
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
          {dir_filter}
        ORDER BY changed_at
    """, tuple(params))


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

    out_legs = _query("""
        SELECT source, best_source, airline, dep_time, arr_time,
               stops, price, booking_url, search_url
        FROM flight_legs
        WHERE destination = %s AND date = %s AND direction = 'out'
        ORDER BY price ASC
        LIMIT 10
    """, (dest, departure_date))

    in_legs = _query("""
        SELECT source, best_source, airline, dep_time, arr_time,
               stops, price, booking_url, search_url
        FROM flight_legs
        WHERE destination = %s AND date = %s AND direction = 'in'
        ORDER BY price ASC
        LIMIT 10
    """, (dest, return_date))

    price_history = _query("""
        SELECT changed_at::text, source, airline,
               old_price, new_price,
               (new_price - COALESCE(old_price, new_price)) AS delta,
               direction
        FROM price_events
        WHERE destination = %s AND date = %s
        ORDER BY changed_at DESC
        LIMIT 20
    """, (dest, departure_date))

    # LIKE 대신 range 쿼리
    month_start = departure_date[:7] + "-01"
    import calendar as _cal
    y, m = int(departure_date[:4]), int(departure_date[5:7])
    month_end = f"{y:04d}-{m:02d}-{_cal.monthrange(y, m)[1]:02d}"

    route_ctx = _query("""
        SELECT
            MIN(price)      AS all_time_low,
            AVG(price)::int AS avg_price,
            COUNT(*)        AS leg_count
        FROM flight_legs
        WHERE destination = %s
          AND direction = 'out'
          AND date >= %s AND date <= %s
    """, (dest, month_start, month_end))

    best_total = None
    if out_legs and in_legs and "error" not in out_legs[0]:
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


@mcp.tool()
def get_calendar_prices(
    destination: str,
    month: str,
    direction: str = "out",
) -> list[dict]:
    """월별 날짜별 최저가 달력 조회.

    특정 목적지의 해당 월 날짜별 최저가를 반환한다.
    "5월에 언제 가장 싸?" 같은 질문에 활용.

    Args:
        destination: 공항코드 (예: NRT, KIX, FUK).
        month: YYYY-MM 형식 (예: 2026-05).
        direction: 'out'(출발편, 기본값) 또는 'in'(귀국편).
    """
    import calendar as _cal
    dest = destination.upper()
    y, m = int(month[:4]), int(month[5:7])
    last_day = _cal.monthrange(y, m)[1]
    month_start = f"{y:04d}-{m:02d}-01"
    month_end = f"{y:04d}-{m:02d}-{last_day:02d}"

    return _query("""
        SELECT
            date,
            MIN(price)::int     AS min_price,
            MIN(airline)        AS cheapest_airline,
            COUNT(DISTINCT airline) AS airline_count
        FROM flight_legs
        WHERE destination = %s
          AND direction = %s
          AND date >= %s AND date <= %s
        GROUP BY date
        ORDER BY date
    """, (dest, direction, month_start, month_end))


@mcp.tool()
def get_recent_deals(
    hours: int = 24,
    destination: str | None = None,
    max_price_krw: int | None = None,
    limit: int = 20,
) -> list[dict]:
    """최근 수집된 딜 중 조건에 맞는 항공권 조회.

    "최근에 싸게 뜬 거 있어?" 같은 질문에 활용.
    checked_at 기준으로 최근 N시간 내 수집된 데이터만 반환한다.

    Args:
        hours: 최근 몇 시간 내 수집 데이터 (기본 24시간).
        destination: 공항코드 필터 (예: NRT). None이면 전체.
        max_price_krw: 왕복 총액 상한 (원). None이면 제한 없음.
        limit: 반환 건수 (기본 20).
    """
    dest_filter = "AND o.destination = %s" if destination else ""
    price_filter = "AND (o.price + i.price) <= %s" if max_price_krw else ""

    params: list = [f"{hours} hours", f"{hours} hours"]
    if destination:
        params.append(destination.upper())
    if max_price_krw:
        params.append(max_price_krw)
    params.append(limit)

    return _query(f"""
        SELECT
            o.destination,
            o.destination_name,
            o.date              AS departure_date,
            i.date              AS return_date,
            (i.date::date - o.date::date) AS stay_nights,
            o.airline           AS out_airline,
            i.airline           AS in_airline,
            o.source,
            o.price             AS out_price,
            i.price             AS in_price,
            (o.price + i.price) AS total_price,
            o.dep_time          AS out_dep_time,
            i.dep_time          AS in_dep_time,
            o.stops             AS out_stops,
            i.stops             AS in_stops,
            GREATEST(o.checked_at, i.checked_at)::text AS last_checked_at
        FROM flight_legs o
        JOIN flight_legs i
          ON o.destination = i.destination
         AND i.date::date - o.date::date BETWEEN 2 AND 7
        WHERE o.direction = 'out'
          AND i.direction = 'in'
          AND o.checked_at >= NOW() - %s::interval
          AND i.checked_at >= NOW() - %s::interval
          {dest_filter}
          {price_filter}
        ORDER BY total_price ASC
        LIMIT %s
    """, tuple(params))


@mcp.tool()
def find_cheapest_month(
    destination: str | None = None,
) -> list[dict]:
    """목적지별 월별 최저가 비교.

    "도쿄 올해 언제 가장 싸?" 같은 질문에 활용.
    오늘 이후 날짜만 대상으로 월별 최저/평균가를 반환한다.

    Args:
        destination: 공항코드 (예: NRT). None이면 전체 목적지.
    """
    dest_filter = "AND destination = %s" if destination else ""
    params: list = []
    if destination:
        params.append(destination.upper())

    return _query(f"""
        SELECT
            destination,
            destination_name,
            LEFT(date, 7)       AS month,
            MIN(price)::int     AS min_price,
            AVG(price)::int     AS avg_price,
            COUNT(*)            AS leg_count
        FROM flight_legs
        WHERE direction = 'out'
          AND price > 0
          AND date >= to_char(CURRENT_DATE, 'YYYY-MM-DD')
          {dest_filter}
        GROUP BY destination, destination_name, LEFT(date, 7)
        ORDER BY destination, min_price ASC
    """, tuple(params))


if __name__ == "__main__":
    mcp.run(transport="sse")
