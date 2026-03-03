# flight_monitor/mcp_server.py
# MCP Tool 3개: get_best_deals / get_price_history / explain_deal
# 로컬 모드: Claude Desktop + 로컬 실행
# 원격 모드: 별도 호스팅 필요

from .storage import get_conn


def get_best_deals(
    destination: str | None = None,   # "OSA", "TYO" 등 (없으면 전체)
    month: str | None = None,          # "2026-05" 형식
    stay_nights: int | None = None,    # 3, 5, 7 등
    limit: int = 10,                   # 반환 건수
) -> list[dict]:
    """
    관측된 최저가 딜 Top-N 반환.
    v_best_observed 뷰를 조회.
    반환 필드: destination_name, departure_date, return_date, stay_nights,
               out_airline, in_airline, is_mixed_airline, min_price, last_checked_at
    """
    conditions = []
    params = []

    if destination:
        conditions.append("destination = ?")
        params.append(destination)
    if month:
        conditions.append("strftime('%Y-%m', departure_date) = ?")
        params.append(month)
    if stay_nights is not None:
        conditions.append("stay_nights = ?")
        params.append(stay_nights)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT destination_name, departure_date, return_date, stay_nights,
                   out_airline, in_airline, is_mixed_airline, min_price, last_checked_at
            FROM v_best_observed
            {where}
            ORDER BY min_price ASC
            LIMIT ?
        """, params).fetchall()

    return [dict(r) for r in rows]


def get_price_history(
    destination: str,                  # 필수
    month: str,                        # "2026-05" 형식, 필수
    stay_nights: int | None = None,
) -> list[dict]:
    """
    특정 노선의 날짜별 최저가 추세 반환.
    반환 필드: departure_date, min_price, out_airline, in_airline, last_checked_at
    """
    conditions = [
        "destination = ?",
        "strftime('%Y-%m', departure_date) = ?",
    ]
    params = [destination, month]

    if stay_nights is not None:
        conditions.append("stay_nights = ?")
        params.append(stay_nights)

    where = "WHERE " + " AND ".join(conditions)

    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT departure_date, min_price, out_airline, in_airline, last_checked_at
            FROM v_best_observed
            {where}
            ORDER BY departure_date ASC
        """, params).fetchall()

    return [dict(r) for r in rows]


def explain_deal(
    destination: str,
    departure_date: str,               # "2026-05-03" 형식
    return_date: str,
) -> dict:
    """
    특정 딜의 상세 정보 반환.
    반환 필드: 혼합항공 여부, 신선도(last_checked_at), 주의사항 요약,
               소스별 최저가 비교 (amadeus vs naver_graphql)
    """
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT source, out_airline, in_airline, is_mixed_airline,
                   MIN(price) AS min_price, MAX(checked_at) AS last_checked_at
            FROM price_history
            WHERE destination = ?
              AND departure_date = ?
              AND return_date = ?
            GROUP BY source, out_airline, in_airline, is_mixed_airline
            ORDER BY min_price ASC
        """, (destination, departure_date, return_date)).fetchall()

    if not rows:
        return {"error": "딜 정보 없음"}

    by_source = {}
    for r in rows:
        src = r["source"]
        if src not in by_source or r["min_price"] < by_source[src]["min_price"]:
            by_source[src] = dict(r)

    best = min(rows, key=lambda r: r["min_price"])
    notes = []
    if best["is_mixed_airline"]:
        notes.append("다른 항공사 조합 — 개별 예약 필요")

    return {
        "destination": destination,
        "departure_date": departure_date,
        "return_date": return_date,
        "best_price": best["min_price"],
        "out_airline": best["out_airline"],
        "in_airline": best["in_airline"],
        "is_mixed_airline": bool(best["is_mixed_airline"]),
        "last_checked_at": best["last_checked_at"],
        "notes": notes,
        "by_source": by_source,
    }
