# flight_friend/api/main.py
"""Router 레이어: 요청 파싱·검증, repo/views 호출, 에러 → HTTP 코드 매핑만 한다."""

import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Self

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator

from flight_friend import db, repo
from flight_friend.api import views
from flight_friend.domain.schedule import KST, cooldown_remaining
from flight_friend.types import Preferences, Trip


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.init_schema()
    yield


app = FastAPI(title="Flight Friend V2", lifespan=lifespan)


class PrefsBody(BaseModel):
    out_dep_window: tuple[str, str] | None = None
    in_dep_window: tuple[str, str] | None = None
    nonstop_only: bool = False
    include_airlines: list[str] = Field(default_factory=list)
    exclude_airlines: list[str] = Field(default_factory=list)
    max_price: int | None = None
    max_duration_min: int | None = None

    @model_validator(mode="after")
    def _windows_not_inverted(self) -> Self:
        for window in (self.out_dep_window, self.in_dep_window):
            if window is not None and window[0] > window[1]:
                raise ValueError("time window start must not be after end")
        return self

    def to_prefs(self) -> Preferences:
        return Preferences(**self.model_dump())


class TripCreate(BaseModel):
    destination: str = Field(pattern=r"^[A-Z]{3}$")
    out_date: date
    ret_date: date
    prefs: PrefsBody = Field(default_factory=PrefsBody)
    target_price: int | None = None


class TripPatch(BaseModel):
    prefs: PrefsBody | None = None
    tracking: bool | None = None
    target_price: int | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _require_trip(trip_id: int) -> Trip:
    trip = repo.get_trip(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="trip not found")
    return trip


@app.get("/healthz")
def healthz() -> JSONResponse:
    if not db.schema_ready():
        return JSONResponse({"ok": False}, status_code=503)
    return JSONResponse({"ok": True})


@app.get("/api/trips")
def list_trips() -> list[views.JsonDict]:
    return views.trip_list(_now())


@app.post("/api/trips", status_code=201)
def create_trip(body: TripCreate) -> dict[str, int]:
    today = _now().astimezone(KST).date()
    if body.ret_date <= body.out_date:
        raise HTTPException(status_code=422, detail="ret_date must be after out_date")
    if body.out_date < today:
        raise HTTPException(status_code=422, detail="out_date must not be in the past")
    trip_id = repo.create_trip(
        body.destination, body.out_date, body.ret_date, body.prefs.to_prefs(), body.target_price
    )
    return {"id": trip_id, "run_id": repo.enqueue_run(trip_id, "manual")}


@app.get("/api/trips/{trip_id}")
def get_trip(trip_id: int) -> views.JsonDict:
    return views.trip_view(_require_trip(trip_id), _now())


@app.patch("/api/trips/{trip_id}")
def patch_trip(trip_id: int, body: TripPatch) -> views.JsonDict:
    _require_trip(trip_id)
    repo.update_trip(
        trip_id,
        prefs=body.prefs.to_prefs() if body.prefs is not None else None,
        tracking=body.tracking,
        target_price=body.target_price,
        clear_target="target_price" in body.model_fields_set and body.target_price is None,
    )
    return views.trip_view(_require_trip(trip_id), _now())


@app.post("/api/trips/{trip_id}/runs", status_code=202, response_model=None)
def create_run(trip_id: int) -> dict[str, int] | JSONResponse:
    _require_trip(trip_id)
    last = repo.latest_run(trip_id)
    if last is not None and repo.has_open_run(trip_id):
        return {"run_id": last.id}
    remaining = cooldown_remaining(last.requested_at if last else None, _now())
    if remaining.total_seconds() > 0:
        return JSONResponse(
            status_code=429, content={"retry_after_seconds": math.ceil(remaining.total_seconds())}
        )
    return {"run_id": repo.enqueue_run(trip_id, "manual")}


@app.get("/api/runs/{run_id}")
def get_run(run_id: int) -> views.JsonDict:
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return views.run_view(run)


@app.get("/api/trips/{trip_id}/history")
def get_history(trip_id: int) -> list[views.JsonDict]:
    return views.history_view(_require_trip(trip_id))


@app.get("/api/admin/runs")
def admin_runs() -> list[views.JsonDict]:
    return views.admin_runs_view()


@app.get("/api/admin/providers")
def admin_providers(days: int = Query(7, ge=1, le=90)) -> list[views.JsonDict]:
    return views.admin_providers_view(days)


# ── Static (React SPA) ── API 라우트 뒤에 등록해야 우선순위 보장
_DIST = Path(__file__).resolve().parent.parent.parent / "flight_front" / "web" / "dist"


@app.get("/{path:path}", response_model=None)
def spa_fallback(path: str) -> FileResponse | JSONResponse:
    if path.startswith("api/") or not _DIST.exists():
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    file_path = (_DIST / path).resolve()
    if file_path.is_relative_to(_DIST) and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(_DIST / "index.html")
