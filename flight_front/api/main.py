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

from flight_monitor.config_db import read_config, write_config
from flight_monitor.storage import init_db, get_conn, get_airports, get_recent_runs, get_run_detail

from . import run_state

PROJECT_ROOT = Path(__file__).parent.parent.parent

app = FastAPI(title="Flight Friend Config API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


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


def _query_deals(cur, conditions: list[str], params: list) -> list[dict]:
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    cur.execute(f"""
        SELECT
            origin, destination, destination_name,
            departure_date, return_date, stay_nights,
            trip_type, source, out_airline, in_airline, is_mixed_airline,
            out_dep_time, out_arr_time, out_duration_min, out_stops,
            in_dep_time, in_arr_time, in_duration_min, in_stops,
            out_arr_airport, in_dep_airport,
            MIN(price) AS min_price,
            MAX(checked_at) AS last_checked_at,
            MAX(out_url) AS out_url,
            MAX(in_url) AS in_url,
            MIN(out_price) AS out_price,
            MIN(in_price) AS in_price
        FROM price_history
        {where_clause}
        GROUP BY
            origin, destination, destination_name,
            departure_date, return_date, stay_nights,
            trip_type, source, out_airline, in_airline, is_mixed_airline,
            out_dep_time, out_arr_time, out_duration_min, out_stops,
            in_dep_time, in_arr_time, in_duration_min, in_stops,
            out_arr_airport, in_dep_airport
        ORDER BY destination, min_price ASC
    """, params)
    return [dict(r) for r in cur.fetchall()]


@app.get("/api/results")
def get_results(
    hours: int | None = Query(None),
    month: str | None = Query(None, regex=r"^\d{4}-\d{2}$"),
    trip_type: str | None = Query(None),
):
    """여행지별 항공권 조회. 서버에서 top_deals/diverse_deals 분류."""
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            conditions: list[str] = []
            params: list = []
            if hours is not None:
                conditions.append("checked_at >= NOW() - %s::interval")
                params.append(f"{hours} hours")
            else:
                conditions.append("checked_at >= CURRENT_DATE")
            if month is not None:
                conditions.append("departure_date LIKE %s")
                params.append(f"{month}-%")
            if trip_type is not None:
                conditions.append("trip_type = %s")
                params.append(trip_type)
            rows = _query_deals(cur, conditions, params)
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

@app.get("/api/search")
def search_flights(
    departure_date: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
    return_date: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
    destination: str | None = Query(None),
    trip_type: str | None = Query(None),
    source: str | None = Query(None),
):
    """특정 출발일/귀국일의 항공권 검색."""
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            conditions: list[str] = [
                "departure_date = %s",
                "return_date = %s",
            ]
            params: list = [departure_date, return_date]
            if destination is not None:
                conditions.append("destination = %s")
                params.append(destination.upper())
            if trip_type is not None:
                conditions.append("trip_type = %s")
                params.append(trip_type)
            if source is not None:
                conditions.append("source = %s")
                params.append(source)
            rows = _query_deals(cur, conditions, params)
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
        deals = group["deals"]
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
    """가격 히스토리 조회. calendar(출발일별 최저가) / timeline(수집 시점별 추이)."""
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if mode == "timeline":
            if not departure_date:
                raise HTTPException(400, "timeline mode requires departure_date")
            if return_date:
                cur.execute("""
                    SELECT
                        DATE(checked_at)::text AS check_date,
                        source,
                        MIN(price) AS min_price
                    FROM price_history
                    WHERE destination = %s
                      AND departure_date = %s
                      AND return_date = %s
                    GROUP BY DATE(checked_at), source
                    ORDER BY check_date
                """, (destination.upper(), departure_date, return_date))
            else:
                cur.execute("""
                    SELECT
                        DATE(checked_at)::text AS check_date,
                        source,
                        MIN(price) AS min_price
                    FROM price_history
                    WHERE destination = %s
                      AND departure_date = %s
                    GROUP BY DATE(checked_at), source
                    ORDER BY check_date
                """, (destination.upper(), departure_date))
        else:
            if not month:
                raise HTTPException(400, "calendar mode requires month parameter")
            cur.execute("""
                SELECT
                    departure_date,
                    source,
                    MIN(price) AS min_price
                FROM price_history
                WHERE destination = %s
                  AND departure_date LIKE %s
                  AND (stay_nights = %s OR %s IS NULL)
                GROUP BY departure_date, source
                ORDER BY departure_date
            """, (destination.upper(), f"{month}%", stay_nights, stay_nights))

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
