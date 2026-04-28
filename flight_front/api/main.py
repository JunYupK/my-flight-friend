# flight_front/api/main.py
import os
import subprocess
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import flight_monitor.config  # noqa: F401 — sys.modules에 먼저 올려두기

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import psycopg2.extras

from flight_monitor.config_db import apply_db_config, read_config, write_config
from flight_monitor.storage import init_db, get_conn, get_airports, get_recent_runs, get_run_detail

from . import run_state
from .deals_cache import query_deals_cached

PROJECT_ROOT = Path(__file__).parent.parent.parent

app = FastAPI(title="Flight Friend Config API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_PERIODIC_WARM_INTERVAL = 3 * 60 * 60  # 3시간


def _periodic_warm_loop():
    """3시간마다 캐시 웜업. 크롤 실패로 TTL 만료 시에도 캐시를 유지."""
    import time
    from .deals_cache import warm_deals_cache
    while True:
        time.sleep(_PERIODIC_WARM_INTERVAL)
        try:
            warm_deals_cache()
        except Exception as e:
            print(f"[periodic-warm] failed: {e}", flush=True)


@app.on_event("startup")
def startup():
    init_db()
    apply_db_config()
    def _initial_warm():
        try:
            from .deals_cache import warm_deals_cache
            warm_deals_cache()
        except Exception as e:
            print(f"[startup] warm_deals_cache failed: {e}", flush=True)
    threading.Thread(target=_initial_warm, daemon=True).start()
    threading.Thread(target=_periodic_warm_loop, daemon=True).start()


class ConfigPayload(BaseModel):
    search_config: dict


@app.get("/api/config")
def get_config():
    return {"search_config": read_config()}


@app.put("/api/config")
def put_config(payload: ConfigPayload):
    write_config(payload.search_config)
    return {"ok": True}


# ── Airports ──────────────────────────────────────────────

class AirportPayload(BaseModel):
    code: str
    name: str
    tfs_out: str = ""
    tfs_in: str = ""


@app.get("/api/airports")
def list_airports():
    return get_airports()


@app.post("/api/airports")
def upsert_airport(payload: AirportPayload):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO airports (code, name, tfs_out, tfs_in)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
                name    = EXCLUDED.name,
                tfs_out = EXCLUDED.tfs_out,
                tfs_in  = EXCLUDED.tfs_in
            """,
            (payload.code.upper(), payload.name, payload.tfs_out, payload.tfs_in),
        )
    return {"ok": True}


@app.delete("/api/airports/{code}")
def delete_airport(code: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM airports WHERE code = %s", (code.upper(),))
    return {"ok": True}


# ── Run ───────────────────────────────────────────────────

def _run_collector():
    proc = subprocess.Popen(
        [sys.executable, "-u", "main.py"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    run_state.set_running(proc.pid)
    for line in proc.stdout:
        run_state.append_output(line)
    proc.wait()
    if proc.returncode == 0:
        run_state.set_done()
    else:
        run_state.set_error()


@app.post("/api/run")
def post_run():
    state = run_state.get()
    if state["status"] == "running":
        raise HTTPException(status_code=409, detail="Already running")
    t = threading.Thread(target=_run_collector, daemon=True)
    t.start()
    return {"ok": True}


@app.get("/api/run/status")
def get_status():
    return run_state.get()


@app.websocket("/ws/run")
async def ws_run(websocket: WebSocket):
    """실시간 수집 로그 스트리밍 WebSocket."""
    await websocket.accept()
    import asyncio
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_message(msg: str):
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    run_state.subscribe(on_message)
    state = run_state.get()
    if state["output"]:
        await websocket.send_text(state["output"])
    await websocket.send_text(f"__status__:{state['status']}")

    try:
        while True:
            msg = await queue.get()
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        pass
    finally:
        run_state.unsubscribe(on_message)


# ── Collection Runs ───────────────────────────────────────

@app.get("/api/collection-runs")
def list_collection_runs(limit: int = Query(20, ge=1, le=100)):
    return get_recent_runs(limit)


@app.get("/api/collection-runs/{run_id}")
def get_collection_run(run_id: int):
    run = get_run_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ── Results ───────────────────────────────────────────────

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


def _select_diverse_deals(deals: list[dict], max_count: int = 15) -> list[dict]:
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


@app.get("/api/results")
def get_results(
    hours: int | None = Query(None),
    month: str | None = Query(None, regex=r"^\d{4}-\d{2}$"),
    trip_type: str | None = Query(None),
    source: str | None = Query(None),
):
    """여행지별 항공권 조회. 서버에서 top_deals/diverse_deals 분류."""
    try:
        rows = query_deals_cached(hours, month, source, trip_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    groups: dict = {}
    for row in rows:
        dest = row["destination"]
        if dest not in groups:
            groups[dest] = {
                "destination": dest,
                "destination_name": row["destination_name"],
                "deals": [],
            }
        groups[dest]["deals"].append(row)

    result = []
    for group in groups.values():
        deals = group["deals"]  # 이미 min_price ASC 정렬됨
        top_deals = deals[:5]
        diverse_deals = _select_diverse_deals(deals[5:])
        result.append({
            "destination": group["destination"],
            "destination_name": group["destination_name"],
            "top_deals": top_deals,
            "diverse_deals": diverse_deals,
            "min_price": deals[0]["min_price"] if deals else 0,
            "total_count": len(deals),
        })

    return result


# ── Search ───────────────────────────────────────────────


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


def _combine_legs(out_legs: list[dict], in_legs: list[dict],
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


@app.get("/api/search")
def search_flights(
    departure_date: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
    return_date: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
    destination: str | None = Query(None),
    trip_type: str | None = Query(None),
    source: str | None = Query(None),
):
    """편도 레그 추출 + 실시간 조합으로 임의 박수 검색 지원."""
    try:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    deals = _combine_legs(out_legs, in_legs, departure_date, return_date,
                          trip_type)

    groups: dict = {}
    for deal in deals:
        dest = deal["destination"]
        if dest not in groups:
            groups[dest] = {
                "destination": dest,
                "destination_name": deal["destination_name"],
                "deals": [],
            }
        groups[dest]["deals"].append(deal)

    result = []
    for group in groups.values():
        d = group["deals"]
        top_deals = d[:5]
        diverse_deals = _select_diverse_deals(d[5:])
        result.append({
            "destination": group["destination"],
            "destination_name": group["destination_name"],
            "top_deals": top_deals,
            "diverse_deals": diverse_deals,
            "min_price": d[0]["min_price"] if d else 0,
            "total_count": len(d),
        })

    return result


# ── Calendar Prices ───────────────────────────────────────

@app.get("/api/calendar-prices")
def get_calendar_prices(
    destination: str = Query(...),
    from_date: str = Query(..., alias="from", regex=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", regex=r"^\d{4}-\d{2}-\d{2}$"),
):
    """캘린더 가격 오버레이용. 출발일별 최저 out_price, 귀국일별 최저 in_price."""
    dest = destination.upper()
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT date, MIN(price) AS price
            FROM flight_legs
            WHERE destination = %s AND direction = 'out'
              AND date BETWEEN %s AND %s
            GROUP BY date
        """, (dest, from_date, to_date))
        out_prices = {r["date"]: r["price"] for r in cur.fetchall()}

        cur.execute("""
            SELECT date, MIN(price) AS price
            FROM flight_legs
            WHERE destination = %s AND direction = 'in'
              AND date BETWEEN %s AND %s
            GROUP BY date
        """, (dest, from_date, to_date))
        in_prices = {r["date"]: r["price"] for r in cur.fetchall()}

    return {"out": out_prices, "in": in_prices}


# ── Price History ─────────────────────────────────────────

@app.get("/api/price-history")
def get_price_history(
    destination: str = Query(...),
    mode: str = Query("calendar"),
    month: str | None = Query(None),
    stay_nights: int | None = Query(None),
    departure_date: str | None = Query(None),
    return_date: str | None = Query(None),
):
    """가격 히스토리 조회. calendar(출발일별 최저가) / timeline(가격 변동 이력)."""
    dest = destination.upper()
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if mode == "timeline":
            if not departure_date:
                raise HTTPException(400, "timeline mode requires departure_date")
            cur.execute("""
                SELECT
                    DATE(collected_at)::text AS check_date,
                    source,
                    MIN(price) AS min_price
                FROM raw_legs
                WHERE destination = %s
                  AND date = %s
                  AND direction = 'out'
                GROUP BY DATE(collected_at), source
                ORDER BY DATE(collected_at)
            """, (dest, departure_date))
        else:
            if not month:
                raise HTTPException(400, "calendar mode requires month parameter")
            cur.execute("""
                SELECT
                    date AS departure_date,
                    best_source AS source,
                    price AS min_price
                FROM flight_legs
                WHERE destination = %s
                  AND direction = 'out'
                  AND date LIKE %s
                ORDER BY date
            """, (dest, f"{month}%"))

        return {"mode": mode, "data": [dict(r) for r in cur.fetchall()]}


# ── Static (React SPA) ────────────────────────────────────
# API 라우트가 모두 등록된 뒤에 마운트해야 우선순위 보장
_DIST = PROJECT_ROOT / "flight_front" / "web" / "dist"
if _DIST.exists():
    # SPA fallback: 클라이언트 라우트(/deals, /trends 등)에서 새로고침 시 index.html 반환
    @app.get("/{path:path}")
    def spa_fallback(path: str):
        file_path = (_DIST / path).resolve()
        if file_path.is_relative_to(_DIST) and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_DIST / "index.html")
