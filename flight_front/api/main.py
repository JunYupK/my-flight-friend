# flight_front/api/main.py
import os
import subprocess
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import flight_monitor.config  # noqa: F401 — sys.modules에 먼저 올려두기

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
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
def get_results():
    """여행지별 최저가 Top 5."""
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT * FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY destination
                        ORDER BY min_price ASC
                    ) AS rank
                FROM v_best_observed
            ) ranked
            WHERE rank <= 5
            ORDER BY destination, min_price ASC
        """)
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
