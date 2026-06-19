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
from .deals_cache import query_deals, query_timing_seasonal_cached, query_timing_advance_cached, _cache_get, _cache_set
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
    # 장기 수집 run과 배포가 겹치면 init_db의 DDL이 collector의 쓰기 락 뒤에서 막힐 수
    # 있다. init_db는 lock_timeout으로 빨리 포기하므로, 그 실패가 startup(=헬스체크)을
    # 막지 않게 삼킨다. 스키마는 이미 존재하므로 진행해도 안전하다.
    try:
        init_db()
    except Exception as e:
        print(f"[startup] init_db skipped (likely lock contention): {e}", flush=True)
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


@app.get("/api/monitor/coverage")
def get_monitor_coverage(days: int = Query(14, ge=1, le=90)):
    """크론 실행 차수별 × 목적지별 × 월별 수집 현황.

    raw_legs.collected_at이 해당 run의 [started_at, finished_at] 윈도우에 속한다는
    사실만으로 별도 스키마 변경 없이 run × destination × month breakdown을 만든다.
    """
    cache_key = f"monitor:coverage:{days}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT cr.id AS run_id, cr.started_at, cr.status AS run_status,
                   rl.destination, rl.destination_name, rl.source,
                   LEFT(rl.date, 7) AS month,
                   COUNT(*) AS legs
            FROM collection_runs cr
            JOIN raw_legs rl
              ON rl.collected_at BETWEEN cr.started_at AND COALESCE(cr.finished_at, NOW())
            WHERE cr.started_at >= NOW() - (%s || ' days')::interval
            GROUP BY cr.id, cr.started_at, cr.status, rl.destination, rl.destination_name, rl.source, month
            ORDER BY cr.started_at DESC
        """, (days,))
        rows = [dict(r) for r in cur.fetchall()]

    by_destination_month: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["destination"], r["month"])
        entry = by_destination_month.get(key)
        if entry is None or r["started_at"] > entry["last_run_at"]:
            by_destination_month[key] = {
                "destination": r["destination"],
                "destination_name": r["destination_name"],
                "month": r["month"],
                "last_run_at": r["started_at"],
                "legs": r["legs"],
            }
        elif r["started_at"] == entry["last_run_at"]:
            entry["legs"] += r["legs"]

    result = {
        "by_destination_month": sorted(
            by_destination_month.values(), key=lambda d: (d["destination"], d["month"])
        ),
        "by_run": rows,
    }
    _cache_set(cache_key, result, ttl=300)  # 5분 — 과거 run 집계는 거의 불변
    return result


@app.get("/api/monitor/system")
def get_system_stats():
    """OCI 호스트의 CPU/메모리/디스크 사용률.

    app 컨테이너에서 psutil로 읽는다. CPU·메모리는 컨테이너에서도 호스트 /proc을
    그대로 반영한다(메모리 cgroup 제한 없음). 디스크는 docker-compose에서 호스트
    루트를 /hostfs로 마운트했을 때 그 경로의 사용률을, 마운트가 없으면 컨테이너 '/'를
    조회한다(이 경우 호스트 실사용량과 다를 수 있음).
    """
    try:
        import psutil
    except Exception as e:  # 이미지에 psutil 미설치 등
        raise HTTPException(status_code=503, detail=f"psutil unavailable: {e}")

    cpu_percent = psutil.cpu_percent(interval=0.3)
    vm = psutil.virtual_memory()

    disk_path = "/hostfs" if os.path.exists("/hostfs") else "/"
    du = psutil.disk_usage(disk_path)

    try:
        load1, load5, load15 = os.getloadavg()
    except OSError:
        load1 = load5 = load15 = 0.0

    return {
        "cpu": {
            "percent": round(cpu_percent, 1),
            "cores": psutil.cpu_count(),
            "load1": round(load1, 2),
            "load5": round(load5, 2),
            "load15": round(load15, 2),
        },
        "memory": {
            "total": vm.total,
            "used": vm.used,
            "available": vm.available,
            "percent": vm.percent,
        },
        "disk": {
            "total": du.total,
            "used": du.used,
            "free": du.free,
            "percent": du.percent,
            "host": disk_path == "/hostfs",
        },
    }


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
        rows = query_deals(hours, month, source, trip_type)
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

    # timeline은 raw_legs를 collected_at별로 GROUP BY하는 무거운 쿼리 → 캐시.
    # calendar는 flight_legs 인덱스 조회라 빠름 → 캐시 불필요.
    cache_key = None
    if mode == "timeline" and departure_date:
        cache_key = f"price-history:timeline:{dest}:{departure_date}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

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

        result = {"mode": mode, "data": [dict(r) for r in cur.fetchall()]}

    if cache_key is not None:
        _cache_set(cache_key, result, ttl=3600)  # 1시간
    return result


# ── Timing Analytics ──────────────────────────────────────

@app.get("/api/timing/seasonal")
def get_timing_seasonal():
    """목적지 × 출발월 최저가 히트맵용 데이터. 크롤 직후에만 바뀌므로 버전 기반 캐시 사용."""
    return query_timing_seasonal_cached()


@app.get("/api/timing/advance")
def get_timing_advance(destination: str | None = Query(None)):
    """출발 N일 전 예약 시점별 평균가 (14일 버킷). 크롤 직후에만 바뀌므로 버전 기반 캐시 사용."""
    return query_timing_advance_cached(destination)


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
