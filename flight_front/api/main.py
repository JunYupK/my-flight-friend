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
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import psycopg2.extras

from flight_monitor.config_db import read_config, write_config
from flight_monitor.storage import init_db, get_conn, get_airports

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


# ── Results ───────────────────────────────────────────────

@app.get("/api/results")
def get_results(hours: int | None = Query(None)):
    """여행지별 최저가 Top 5."""
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if hours is not None:
            cutoff = f"{hours} hours"
        else:
            cutoff = None
        cur.execute("""
            SELECT * FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY destination
                        ORDER BY min_price ASC
                    ) AS rank
                FROM (
                    SELECT
                        origin, destination, destination_name,
                        departure_date, return_date, stay_nights,
                        source, out_airline, in_airline, is_mixed_airline,
                        out_dep_time, out_arr_time, out_duration_min, out_stops,
                        in_dep_time, in_arr_time, in_duration_min, in_stops,
                        out_arr_airport, in_dep_airport,
                        MIN(price) AS min_price,
                        MAX(checked_at) AS last_checked_at,
                        MAX(out_url) AS out_url,
                        MAX(in_url) AS in_url
                    FROM price_history
                    WHERE (%s IS NULL OR checked_at >= NOW() - %s::interval)
                    GROUP BY
                        origin, destination, destination_name,
                        departure_date, return_date, stay_nights,
                        source, out_airline, in_airline, is_mixed_airline,
                        out_dep_time, out_arr_time, out_duration_min, out_stops,
                        in_dep_time, in_arr_time, in_duration_min, in_stops,
                        out_arr_airport, in_dep_airport
                ) sub
            ) ranked
            WHERE rank <= 5
            ORDER BY destination, min_price ASC
        """, (cutoff, cutoff))
        rows = cur.fetchall()

    groups: dict = {}
    for row in rows:
        dest = row["destination"]
        if dest not in groups:
            groups[dest] = {
                "destination": dest,
                "destination_name": row["destination_name"],
                "deals": [],
            }
        groups[dest]["deals"].append(dict(row))

    return list(groups.values())


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
            if not departure_date or not return_date:
                raise HTTPException(400, "timeline mode requires departure_date and return_date")
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
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="static")
