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
from .search_service import search_deals, select_diverse_deals

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
        diverse_deals = select_diverse_deals(deals[5:])
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
    """편도 레그 추출 + 실시간 조합으로 임의 박수 검색 지원."""
    try:
        deals = search_deals(departure_date, return_date,
                             destination, source, trip_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        diverse_deals = select_diverse_deals(d[5:])
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


# ── Timing Analytics ──────────────────────────────────────

@app.get("/api/timing/seasonal")
def get_timing_seasonal():
    """목적지 × 출발월 최저가 히트맵용 데이터."""
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # flight_legs 기반: UPSERT 구조라 row 수가 적고 인덱스 활용 가능.
        # 월별 최저가는 현재 수집 데이터 기준이면 충분하므로 price_history 불필요.
        cur.execute("""
            SELECT
                o.destination,
                o.destination_name,
                LEFT(o.date, 7) AS month,
                MIN(o.price + i.price)::int AS min_price
            FROM flight_legs o
            JOIN flight_legs i
              ON o.destination = i.destination
             AND i.date::date - o.date::date BETWEEN 2 AND 7
            WHERE o.direction = 'out'
              AND i.direction = 'in'
              AND o.price > 0 AND i.price > 0
            GROUP BY o.destination, o.destination_name, LEFT(o.date, 7)
            ORDER BY o.destination, month
        """)
        return [dict(r) for r in cur.fetchall()]


@app.get("/api/timing/advance")
def get_timing_advance(destination: str | None = Query(None)):
    """출발 N일 전 예약 시점별 평균가 (14일 버킷)."""
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        sql = """
            SELECT destination, destination_name,
                   (FLOOR((departure_date::date - DATE(checked_at)) / 14.0) * 14)::int AS days_before,
                   ROUND(AVG(price)::numeric, 0)::int AS avg_price,
                   MIN(price)::int AS min_price,
                   COUNT(*) AS obs_count
            FROM price_history
            WHERE trip_type IN ('round_trip', 'oneway_combo') AND price > 0
              AND departure_date ~ '^\d{4}-\d{2}-\d{2}$'
              AND departure_date::date > DATE(checked_at)
              AND (departure_date::date - DATE(checked_at)) BETWEEN 1 AND 180
        """
        params: list = []
        if destination:
            sql += " AND destination = %s"
            params.append(destination.upper())
        sql += """
            GROUP BY destination, destination_name,
                     (FLOOR((departure_date::date - DATE(checked_at)) / 14.0) * 14)::int
            HAVING COUNT(*) >= 3
            ORDER BY destination, days_before DESC
        """
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


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
