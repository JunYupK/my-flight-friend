# flight_front/api/search_service.py
#
# 검색/딜 선별 Service 레이어.
# Router(main.py)에 있던 비즈니스 로직 이동 (AGENTS.md §2, §11).

import psycopg2.extras

from flight_monitor.storage import get_conn


def _normalize_time(t: str | None) -> str:
    if not t:
        return "??:??"
    return t.strip()


def _extract_hour(t: str | None) -> int | None:
    norm = _normalize_time(t)
    if norm == "??:??":
        return None
    try:
        return int(norm.split(":")[0])
    except (ValueError, IndexError):
        return None


def _time_bucket(hour: int | None) -> str:
    if hour is None:
        return "unknown"
    if hour < 9:
        return "early"
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    return "evening"


def select_diverse_deals(deals: list[dict], max_count: int = 15) -> list[dict]:
    """시간대 버킷별 대표 딜 선별. Results.tsx selectDiverseDeals의 서버 버전."""
    bucket_map: dict[str, list[dict]] = {}
    no_time: list[dict] = []

    for deal in deals:
        out_h = _extract_hour(deal.get("out_dep_time"))
        in_h = _extract_hour(deal.get("in_dep_time"))
        if out_h is None and in_h is None:
            no_time.append(deal)
            continue
        key = f"{_time_bucket(out_h)}_{_time_bucket(in_h)}"
        bucket_map.setdefault(key, []).append(deal)

    result: list[dict] = []
    seen: set[int] = set()

    # 각 버킷에서 최저가 1건씩
    for bucket in bucket_map.values():
        for d in bucket:
            idx = id(d)
            if idx not in seen:
                seen.add(idx)
                result.append(d)
                break

    # 부족하면 추가
    if len(result) < max_count:
        for bucket in bucket_map.values():
            if len(result) >= max_count:
                break
            for d in bucket:
                idx = id(d)
                if idx not in seen:
                    seen.add(idx)
                    result.append(d)
                    break

    for d in no_time:
        if len(result) >= max_count:
            break
        result.append(d)

    result.sort(key=lambda x: x["min_price"])
    return result


def _query_outbound_legs(cur, departure_date: str,
                         extra_conds: list[str], extra_params: list) -> list[dict]:
    """departure_date 기준 출발 레그 조회 (flight_legs 테이블)."""
    conditions = ["date = %s", "direction = 'out'"]
    params: list = [departure_date]
    conditions.extend(extra_conds)
    params.extend(extra_params)
    where = "WHERE " + " AND ".join(conditions)
    cur.execute(f"""
        SELECT destination, destination_name, origin, source,
               airline AS out_airline,
               dep_time AS out_dep_time,
               arr_time AS out_arr_time,
               duration_min AS out_duration_min,
               stops AS out_stops,
               arr_airport AS out_arr_airport,
               COALESCE(booking_url, search_url) AS out_url,
               price AS out_price,
               checked_at AS last_checked_at
        FROM flight_legs {where}
    """, params)
    return [dict(r) for r in cur.fetchall()]


def _query_inbound_legs(cur, return_date: str,
                        extra_conds: list[str], extra_params: list) -> list[dict]:
    """return_date 기준 귀국 레그 조회 (flight_legs 테이블)."""
    conditions = ["date = %s", "direction = 'in'"]
    params: list = [return_date]
    conditions.extend(extra_conds)
    params.extend(extra_params)
    where = "WHERE " + " AND ".join(conditions)
    cur.execute(f"""
        SELECT destination, destination_name, origin, source,
               airline AS in_airline,
               dep_time AS in_dep_time,
               arr_time AS in_arr_time,
               duration_min AS in_duration_min,
               stops AS in_stops,
               dep_airport AS in_dep_airport,
               COALESCE(booking_url, search_url) AS in_url,
               price AS in_price,
               checked_at AS last_checked_at
        FROM flight_legs {where}
    """, params)
    return [dict(r) for r in cur.fetchall()]


def combine_legs(out_legs: list[dict], in_legs: list[dict],
                 departure_date: str, return_date: str,
                 trip_type_filter: str | None) -> list[dict]:
    """출발 × 귀국 레그 cross-product → 왕복 조합 생성."""
    from datetime import datetime
    stay_nights = (datetime.strptime(return_date, "%Y-%m-%d")
                   - datetime.strptime(departure_date, "%Y-%m-%d")).days

    in_by_dest: dict[str, list[dict]] = {}
    for leg in in_legs:
        in_by_dest.setdefault(leg["destination"], []).append(leg)

    deals: list[dict] = []
    for out in out_legs:
        dest = out["destination"]
        for inb in in_by_dest.get(dest, []):
            is_mixed = (out["out_airline"] or "") != (inb["in_airline"] or "")
            if trip_type_filter == "round_trip" and is_mixed:
                continue
            if trip_type_filter == "oneway_combo" and not is_mixed:
                continue

            deals.append({
                "origin": out["origin"],
                "destination": dest,
                "destination_name": out["destination_name"],
                "departure_date": departure_date,
                "return_date": return_date,
                "stay_nights": stay_nights,
                "trip_type": "oneway_combo" if is_mixed else "round_trip",
                "source": out["source"],
                "out_airline": out["out_airline"],
                "in_airline": inb["in_airline"],
                "is_mixed_airline": is_mixed,
                "out_dep_time": out["out_dep_time"],
                "out_arr_time": out["out_arr_time"],
                "out_duration_min": out["out_duration_min"],
                "out_stops": out["out_stops"],
                "in_dep_time": inb["in_dep_time"],
                "in_arr_time": inb["in_arr_time"],
                "in_duration_min": inb["in_duration_min"],
                "in_stops": inb["in_stops"],
                "out_arr_airport": out["out_arr_airport"],
                "in_dep_airport": inb["in_dep_airport"],
                "out_url": out["out_url"],
                "in_url": inb["in_url"],
                "out_price": out["out_price"],
                "in_price": inb["in_price"],
                "min_price": out["out_price"] + inb["in_price"],
                "last_checked_at": max(out["last_checked_at"],
                                       inb["last_checked_at"]).isoformat(),
            })

    deals.sort(key=lambda d: d["min_price"])
    return deals


def search_deals(departure_date: str, return_date: str,
                 destination: str | None, source: str | None,
                 trip_type: str | None) -> list[dict]:
    """편도 레그 조회 + 실시간 조합. /api/search 본체."""
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        extra_conds: list[str] = []
        extra_params: list = []
        if destination is not None:
            extra_conds.append("destination = %s")
            extra_params.append(destination.upper())
        if source is not None:
            extra_conds.append("source = %s")
            extra_params.append(source)

        out_legs = _query_outbound_legs(cur, departure_date,
                                        extra_conds, extra_params)
        in_legs = _query_inbound_legs(cur, return_date,
                                      extra_conds, extra_params)

    return combine_legs(out_legs, in_legs, departure_date, return_date,
                        trip_type)
