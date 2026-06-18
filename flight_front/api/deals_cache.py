# flight_front/api/deals_cache.py
"""Deals query + Redis cache (FastAPI에 의존하지 않는 순수 데이터 레이어).

`/api/results` 핸들러와 크롤러 파이프라인 모두에서 재사용하기 위해
별도 모듈로 분리됨. 크롤링 직후 `warm_deals_cache()` 를 호출하면
월별 deals 결과를 미리 계산해 Redis에 채워둠 → 첫 사용자 cold miss 제거.
"""
import json
import os
import time
from pathlib import Path

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


def _cache_get(key: str):
    if _redis_client is not None:
        try:
            raw = _redis_client.get(key)
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
    cached = _deals_cache.get(key)
    if cached and time.time() < cached[0]:  # cached[0] = 만료 시각(absolute)
        return cached[1]
    return None


def _cache_set(key: str, value, ttl: int = DEALS_CACHE_TTL) -> None:
    if _redis_client is not None:
        try:
            _redis_client.setex(key, ttl, json.dumps(value, default=str))
            return
        except Exception:
            pass
    _deals_cache[key] = (time.time() + ttl, value)


# ── Query ─────────────────────────────────────────────────

def query_deals(hours, month, source, trip_type) -> list[dict]:
    """deals 사전계산 테이블에서 목적지별 top-200 조회.

    수집 시 save_deals()가 채운 materialized 테이블을 단순 인덱스 조회로 읽는다.
    (기존: flight_legs out×in 카테시안 조인 + Redis 버전 캐시 → cold miss 유발)
    """
    where_conds: list[str] = []
    params: list = []

    if month is not None:
        # departure_date는 'YYYY-MM-DD' TEXT — 사전식 범위가 날짜 범위와 일치.
        year, mon = map(int, month.split("-"))
        start_date = f"{year:04d}-{mon:02d}-01"
        if mon == 12:
            end_date = f"{year + 1:04d}-01-01"
        else:
            end_date = f"{year:04d}-{mon + 1:02d}-01"
        where_conds.append("departure_date >= %s AND departure_date < %s")
        params.extend([start_date, end_date])

    if source is not None:
        where_conds.append("source = %s")
        params.append(source)

    if trip_type is not None:
        where_conds.append("trip_type = %s")
        params.append(trip_type)

    if hours is not None:
        # 호출자가 명시적으로 신선도 윈도우를 요구한 경우에만 좁게 필터.
        where_conds.append("last_checked_at >= NOW() - %s::interval")
        params.append(f"{hours} hours")
    else:
        # 기본: 하드 신선도 컷오프 없음. 수집이 며칠 실패해도 화면이 비지 않도록
        # 보유한 최신 deal을 그대로 보여주고, 오래됨 여부는 UI가 last_checked_at으로
        # 표기한다. 14일 안전망은 노선 제거 등으로 갱신이 끊긴 좀비 행만 배제한다.
        where_conds.append("last_checked_at >= NOW() - INTERVAL '14 days'")

    where_clause = " AND ".join(where_conds)

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(f"""
            WITH ranked AS (
                SELECT
                    origin, destination, destination_name,
                    departure_date, return_date, stay_nights, trip_type,
                    source, source AS out_source, source AS in_source,
                    out_airline, in_airline, is_mixed_airline,
                    out_dep_time, out_arr_time, out_duration_min, out_stops,
                    in_dep_time, in_arr_time, in_duration_min, in_stops,
                    out_arr_airport, in_dep_airport,
                    last_checked_at, out_url, in_url,
                    out_price, in_price, min_price,
                    ROW_NUMBER() OVER (
                        PARTITION BY destination
                        ORDER BY min_price ASC
                    ) AS rn
                FROM deals
                WHERE {where_clause}
            )
            SELECT
                origin, destination, destination_name, departure_date, return_date,
                stay_nights, trip_type, source,
                out_source, in_source,
                out_airline, in_airline, is_mixed_airline,
                out_dep_time, out_arr_time, out_duration_min, out_stops,
                in_dep_time, in_arr_time, in_duration_min, in_stops,
                out_arr_airport, in_dep_airport,
                last_checked_at, out_url, in_url,
                out_price, in_price, min_price
            FROM ranked
            WHERE rn <= 200
            ORDER BY destination, min_price ASC
        """, params)
        return [dict(r) for r in cur.fetchall()]


# ── Timing analytics query (moved from main.py, cached) ──

def _query_timing_seasonal(cur) -> list[dict]:
    cur.execute("""
        SELECT
            o.destination,
            o.destination_name,
            LEFT(o.date, 7) AS month,
            MIN(o.price + i.price)::int AS min_price
        FROM flight_legs o
        JOIN flight_legs i
          ON o.destination = i.destination
         AND i.date > o.date
         AND i.date <= to_char(o.date::date + 7, 'YYYY-MM-DD')
         AND i.date >= to_char(o.date::date + 2, 'YYYY-MM-DD')
        WHERE o.direction = 'out'
          AND i.direction = 'in'
          AND o.price > 0 AND i.price > 0
          AND o.date >= to_char(NOW() - INTERVAL '12 months', 'YYYY-MM-DD')
        GROUP BY o.destination, o.destination_name, LEFT(o.date, 7)
        ORDER BY o.destination, month
    """)
    return [dict(r) for r in cur.fetchall()]


def _query_timing_advance(cur, destination: str | None) -> list[dict]:
    """raw_legs의 out/in 레그를 같은 크롤 회차(collected_at ±1시간) 기준으로 묶어
    왕복 조합 가격을 근사한다. price_history는 2026-04-03 이후 신규 데이터가 없어 사용하지 않음."""
    sql = """
        SELECT o.destination, o.destination_name,
               (FLOOR((o.date::date - DATE(o.collected_at)) / 14.0) * 14)::int AS days_before,
               ROUND(AVG(o.price + i.price)::numeric, 0)::int AS avg_price,
               MIN(o.price + i.price)::int AS min_price,
               COUNT(*) AS obs_count
        FROM raw_legs o
        JOIN raw_legs i
          ON o.destination = i.destination
         AND i.direction = 'in'
         AND i.date > o.date
         AND i.date <= to_char(o.date::date + 7, 'YYYY-MM-DD')
         AND i.date >= to_char(o.date::date + 2, 'YYYY-MM-DD')
         AND i.collected_at BETWEEN o.collected_at - INTERVAL '1 hour' AND o.collected_at + INTERVAL '1 hour'
        WHERE o.direction = 'out'
          AND o.price > 0 AND i.price > 0
          AND o.date::date > DATE(o.collected_at)
          AND (o.date::date - DATE(o.collected_at)) BETWEEN 1 AND 180
          AND o.collected_at >= NOW() - INTERVAL '90 days'
    """
    params: list = []
    if destination:
        sql += " AND o.destination = %s"
        params.append(destination.upper())
    sql += """
        GROUP BY o.destination, o.destination_name,
                 (FLOOR((o.date::date - DATE(o.collected_at)) / 14.0) * 14)::int
        HAVING COUNT(*) >= 3
        ORDER BY o.destination, days_before DESC
    """
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def query_timing_seasonal_cached() -> list[dict]:
    version = _current_version()
    key = f"timing:v{version}:seasonal"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        result = _query_timing_seasonal(cur)
    _cache_set(key, result)
    return result


def query_timing_advance_cached(destination: str | None) -> list[dict]:
    version = _current_version()
    key = f"timing:v{version}:advance:{destination}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        result = _query_timing_advance(cur, destination)
    _cache_set(key, result)
    return result


# ── Version (atomic invalidation) ─────────────────────────
# 캐시 키에 글로벌 버전을 prefix 로 붙여서, 크롤 성공 시 INCR 한 번으로
# 네임스페이스 전체를 원자적으로 무효화한다. 이전 버전 키는 TTL 로 자연 소멸.
# Redis 가 없으면 version = 0 고정 (단일 네임스페이스처럼 동작).

_VERSION_KEY = "deals:version"
_VERSION_FILE = Path("/tmp/deals_version")


def _current_version() -> int:
    if _redis_client is None:
        try:
            return int(_VERSION_FILE.read_text().strip())
        except Exception:
            return 0
    try:
        v = _redis_client.get(_VERSION_KEY)
        return int(v) if v else 0
    except Exception:
        return 0


def bump_deals_version() -> int:
    """크롤이 데이터를 저장한 직후 호출. Redis 네임스페이스 전체를 즉시 무효화."""
    if _redis_client is None:
        v = _current_version() + 1
        try:
            _VERSION_FILE.write_text(str(v))
        except Exception as e:
            print(f"[cache] version file write failed: {e}", flush=True)
        return v
    try:
        return int(_redis_client.incr(_VERSION_KEY))
    except Exception as e:
        print(f"[cache] version bump failed: {e}", flush=True)
        return 0


# ── Warm-up ───────────────────────────────────────────────

def warm_deals_cache() -> dict:
    """크롤링 직후 호출. timing 분석 캐시(seasonal/advance)를 미리 계산해 Redis에 저장.

    deals는 save_deals()가 채우는 materialized 테이블을 직접 조회하므로 더 이상
    웜업이 필요 없다. 여기서는 timing 엔드포인트 cold miss만 제거한다.

    Returns: {"warmed": int, "failed": int, "elapsed_sec": float}
    """
    started = time.time()

    if _redis_client is None:
        stats = {"warmed": 0, "failed": 0, "reason": "redis unavailable"}
        print(f"[warmup] skipped: {stats}", flush=True)
        return stats

    version = _current_version()
    print(f"[warmup] start: v{version}, timing caches", flush=True)

    warmed = 0
    failed = 0
    try:
        seasonal = query_timing_seasonal_cached()
        warmed += 1
        destinations = {d["destination"] for d in seasonal}
        for dest in [None, *destinations]:
            query_timing_advance_cached(dest)
            warmed += 1
    except Exception as e:
        failed += 1
        print(f"[warmup] timing failed: {e}", flush=True)

    elapsed = round(time.time() - started, 2)
    stats = {"warmed": warmed, "failed": failed, "elapsed_sec": elapsed}
    print(f"[warmup] done: {stats}", flush=True)
    return stats
