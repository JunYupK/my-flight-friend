# flight_front/api/deals_cache.py
"""Deals query + Redis cache (FastAPI에 의존하지 않는 순수 데이터 레이어).

`/api/results` 핸들러와 크롤러 파이프라인 모두에서 재사용하기 위해
별도 모듈로 분리됨. 크롤링 직후 `warm_deals_cache()` 를 호출하면
월별 deals 결과를 미리 계산해 Redis에 채워둠 → 첫 사용자 cold miss 제거.
"""
import json
import os
import time
from datetime import datetime

import psycopg2.extras

from flight_monitor.storage import get_conn


# ── Cache infra ────────────────────────────────────────────

_deals_cache: dict[str, tuple[float, list]] = {}
DEALS_CACHE_TTL = 11400  # 3시간 10분 — 크롤링 주기(3h) + 크롤 소요시간 버퍼(10m)

try:
    import redis as _redis_lib
    _redis_client = _redis_lib.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379"),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    _redis_client.ping()
    print("[cache] Redis connected", flush=True)
except Exception as e:
    print(f"[cache] Redis unavailable, using in-memory fallback: {e}", flush=True)
    _redis_client = None


def _cache_get(key: str) -> list | None:
    if _redis_client is not None:
        try:
            raw = _redis_client.get(key)
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
    cached = _deals_cache.get(key)
    if cached and time.time() - cached[0] < DEALS_CACHE_TTL:
        return cached[1]
    return None


def _cache_set(key: str, value: list) -> None:
    if _redis_client is not None:
        try:
            _redis_client.setex(key, DEALS_CACHE_TTL, json.dumps(value, default=str))
            return
        except Exception:
            pass
    _deals_cache[key] = (time.time(), value)


# ── Query ─────────────────────────────────────────────────

def _query_deals(cur, hours: int | None, month: str | None,
                 source: str | None, trip_type: str | None) -> list[dict]:
    from flight_monitor.config import SEARCH_CONFIG
    stay = SEARCH_CONFIG.get("stay_durations", [3, 4, 5])
    min_stay, max_stay = min(stay), max(stay)

    join_params: list = [min_stay, max_stay]

    trip_join_extra = ""
    if trip_type == "round_trip":
        trip_join_extra = " AND o.airline = i.airline"
    elif trip_type == "oneway_combo":
        trip_join_extra = " AND o.airline IS DISTINCT FROM i.airline"

    where_conds = ["o.direction = 'out'", "i.direction = 'in'"]
    where_params: list = []

    if hours is not None:
        where_conds.append("o.checked_at >= NOW() - %s::interval")
        where_conds.append("i.checked_at >= NOW() - %s::interval")
        where_params.append(f"{hours} hours")
        where_params.append(f"{hours} hours")
    else:
        where_conds.append("o.checked_at >= CURRENT_DATE")
        where_conds.append("i.checked_at >= CURRENT_DATE")

    if month is not None:
        # date is TEXT in 'YYYY-MM-DD' — lexicographic range matches date range
        # and lets the (destination, date) partial indexes do a range scan.
        year, mon = map(int, month.split("-"))
        start_date = f"{year:04d}-{mon:02d}-01"
        if mon == 12:
            end_date = f"{year + 1:04d}-01-01"
        else:
            end_date = f"{year:04d}-{mon + 1:02d}-01"
        where_conds.append("o.date >= %s AND o.date < %s")
        where_params.extend([start_date, end_date])

    if source is not None:
        where_conds.append("o.source = %s")
        where_params.append(source)

    where_clause = " AND ".join(where_conds)

    cur.execute(f"""
        WITH ranked AS (
            SELECT
                o.origin, o.destination, o.destination_name,
                o.date AS departure_date,
                i.date AS return_date,
                (i.date::date - o.date::date) AS stay_nights,
                CASE WHEN o.airline = i.airline THEN 'round_trip' ELSE 'oneway_combo' END AS trip_type,
                o.source,
                o.airline AS out_airline, i.airline AS in_airline,
                (o.airline IS DISTINCT FROM i.airline)::int AS is_mixed_airline,
                o.dep_time AS out_dep_time, o.arr_time AS out_arr_time,
                o.duration_min AS out_duration_min, o.stops AS out_stops,
                i.dep_time AS in_dep_time, i.arr_time AS in_arr_time,
                i.duration_min AS in_duration_min, i.stops AS in_stops,
                o.arr_airport AS out_arr_airport, i.dep_airport AS in_dep_airport,
                GREATEST(o.checked_at, i.checked_at) AS last_checked_at,
                COALESCE(o.booking_url, o.search_url) AS out_url,
                COALESCE(i.booking_url, i.search_url) AS in_url,
                o.price AS out_price, i.price AS in_price,
                (o.price + i.price) AS min_price,
                ROW_NUMBER() OVER (
                    PARTITION BY o.destination
                    ORDER BY (o.price + i.price) ASC
                ) AS rn
            FROM flight_legs o
            JOIN flight_legs i
                ON o.destination = i.destination
                AND (i.date::date - o.date::date) BETWEEN %s AND %s{trip_join_extra}
            WHERE {where_clause}
        )
        SELECT
            origin, destination, destination_name, departure_date, return_date,
            stay_nights, trip_type, source,
            out_airline, in_airline, is_mixed_airline,
            out_dep_time, out_arr_time, out_duration_min, out_stops,
            in_dep_time, in_arr_time, in_duration_min, in_stops,
            out_arr_airport, in_dep_airport,
            last_checked_at, out_url, in_url,
            out_price, in_price, min_price
        FROM ranked
        WHERE rn <= 200
        ORDER BY destination, min_price ASC
    """, join_params + where_params)
    return [dict(r) for r in cur.fetchall()]


def query_deals_cached(hours, month, source, trip_type) -> list[dict]:
    version = _current_version()
    key = f"deals:v{version}:{hours}:{month}:{source}:{trip_type}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        result = _query_deals(cur, hours, month, source, trip_type)
    _cache_set(key, result)
    return result


# ── Version (atomic invalidation) ─────────────────────────
# 캐시 키에 글로벌 버전을 prefix 로 붙여서, 크롤 성공 시 INCR 한 번으로
# 네임스페이스 전체를 원자적으로 무효화한다. 이전 버전 키는 TTL 로 자연 소멸.
# Redis 가 없으면 version = 0 고정 (단일 네임스페이스처럼 동작).

_VERSION_KEY = "deals:version"


def _current_version() -> int:
    if _redis_client is None:
        return 0
    try:
        v = _redis_client.get(_VERSION_KEY)
        return int(v) if v else 0
    except Exception:
        return 0


def bump_deals_version() -> int:
    """크롤이 데이터를 저장한 직후 호출. Redis 네임스페이스 전체를 즉시 무효화.
    Redis 없으면 0 반환(no-op)."""
    if _redis_client is None:
        return 0
    try:
        return int(_redis_client.incr(_VERSION_KEY))
    except Exception as e:
        print(f"[cache] version bump failed: {e}", flush=True)
        return 0


# ── Warm-up ───────────────────────────────────────────────

def _upcoming_months(count: int) -> list[str]:
    """오늘부터 `count` 개월치 'YYYY-MM' 리스트 (현재 월 포함)."""
    now = datetime.now()
    year, mon = now.year, now.month
    months = []
    for _ in range(count):
        months.append(f"{year:04d}-{mon:02d}")
        mon += 1
        if mon > 12:
            mon = 1
            year += 1
    return months


def warm_deals_cache() -> dict:
    """크롤링 직후 호출. 향후 N개월 deals 결과를 미리 계산해 Redis에 저장.

    1차 범위: `(hours=None, month=YYYY-MM, source=None, trip_type=None)` 조합만
    미리 채움 (캐시 키 폭발 방지). 향후 trip_type 분리 등 확장 여지 있음.

    Returns: {"warmed": int, "failed": int, "elapsed_sec": float}
    """
    started = time.time()

    if _redis_client is None:
        stats = {"warmed": 0, "failed": 0, "reason": "redis unavailable"}
        print(f"[warmup] skipped: {stats}", flush=True)
        return stats

    from flight_monitor.config import SEARCH_CONFIG
    months = _upcoming_months(SEARCH_CONFIG.get("search_range_months", 12))
    version = _current_version()
    print(f"[warmup] start: v{version}, {len(months)} months {months[0]}..{months[-1]}", flush=True)

    warmed = 0
    failed = 0
    for m in months:
        try:
            query_deals_cached(hours=None, month=m, source=None, trip_type=None)
            warmed += 1
        except Exception as e:
            failed += 1
            print(f"[warmup] month={m} failed: {e}", flush=True)

    elapsed = round(time.time() - started, 2)
    stats = {"warmed": warmed, "failed": failed, "elapsed_sec": elapsed}
    print(f"[warmup] done: {stats}", flush=True)
    return stats
