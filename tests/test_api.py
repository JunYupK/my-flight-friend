# tests/test_api.py

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest
from fastapi.testclient import TestClient

from flight_friend import db, repo
from flight_friend.api import main as api_main
from flight_friend.api.main import app
from flight_friend.types import LegQuote, Preferences, ProviderResult, RtQuote

client = TestClient(app)

TODAY = datetime.now(UTC).date()
OUT = TODAY + timedelta(days=90)
RET = OUT + timedelta(days=3)


def quote(key: str, price: int, dep: str = "08:00", stops: int = 0) -> LegQuote:
    return LegQuote(
        flight_key=key,
        airline_iata="KE",
        airline_name="Korean Air",
        flight_numbers=[key],
        dep_airport="ICN",
        arr_airport="FUK",
        dep_time=dep,
        arr_time="10:00",
        duration_min=120,
        stops=stops,
        price=price,
        booking_url=f"https://x/{key}",
        search_url=None,
    )


def result(legs: list[LegQuote], status: Literal["ok", "empty", "blocked", "error"] = "ok") -> ProviderResult:
    return ProviderResult(status=status, legs=legs, rts=[], error=None, seconds=0.1)


def make_trip(prefs: Preferences | None = None) -> int:
    return repo.create_trip("FUK", OUT, RET, prefs or Preferences())


def add_run(
    trip_id: int,
    out_legs: list[LegQuote],
    in_legs: list[LegQuote],
    observed_at: datetime,
    provider: str = "google_flights",
) -> int:
    run_id = repo.enqueue_run(trip_id, "manual")
    repo.save_snapshot(run_id, trip_id, provider, "oneway", "out", OUT, result(out_legs), observed_at)
    repo.save_snapshot(run_id, trip_id, provider, "oneway", "in", RET, result(in_legs), observed_at)
    return run_id


def body(**over: object) -> dict[str, object]:
    base: dict[str, object] = {"destination": "FUK", "out_date": OUT.isoformat(), "ret_date": RET.isoformat()}
    base.update(over)
    return base


def test_create_trip_enqueues_manual_run() -> None:
    r = client.post("/api/trips", json=body(target_price=150000))
    assert r.status_code == 201
    data = r.json()
    trip = repo.get_trip(data["id"])
    assert trip is not None and trip.target_price == 150000 and trip.prefs == Preferences()
    run = repo.get_run(data["run_id"])
    assert run is not None and run.trigger == "manual" and run.status == "queued"


def test_create_trip_accepts_prefs() -> None:
    prefs = Preferences(out_dep_window=("06:00", "12:00"), nonstop_only=True, max_price=200000)
    r = client.post("/api/trips", json=body(prefs=dict(prefs.to_dict())))
    assert r.status_code == 201
    trip = repo.get_trip(r.json()["id"])
    assert trip is not None and trip.prefs == prefs


def test_create_trip_validation_422() -> None:
    assert client.post("/api/trips", json=body(ret_date=OUT.isoformat())).status_code == 422
    assert client.post("/api/trips", json=body(ret_date=(OUT - timedelta(days=1)).isoformat())).status_code == 422
    past = (TODAY - timedelta(days=5)).isoformat()
    assert client.post("/api/trips", json=body(out_date=past, ret_date=OUT.isoformat())).status_code == 422
    assert client.post("/api/trips", json=body(destination="fuk")).status_code == 422
    assert client.post("/api/trips", json=body(destination="FUKU")).status_code == 422
    assert repo.list_trips() == []


def test_trip_view_shape() -> None:
    trip_id = make_trip(Preferences(nonstop_only=True))
    now = datetime.now(UTC)
    add_run(
        trip_id,
        [quote("A", 80000), quote("B", 60000, stops=1)],
        [quote("C", 90000)],
        now,
    )
    r = client.get(f"/api/trips/{trip_id}")
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {
        "trip", "run", "providers", "stats", "legs", "candidates", "near_miss", "rt_reference", "window_minutes",
    }
    assert set(d["run"]) == {"id", "status", "requested_at"}
    assert d["trip"]["id"] == trip_id and d["trip"]["destination"] == "FUK"
    assert d["window_minutes"] == 720
    assert set(d["stats"]) == {"current", "start", "start_day", "low", "low_day", "median", "days", "comparable"}
    assert d["stats"]["current"] == 170000
    assert set(d["legs"]) == {"out", "in"}
    by_key = {m["flight_key"]: m for m in d["legs"]["out"]}
    assert set(by_key["A"]) == {
        "flight_key", "dep_time", "arr_time", "airline_name", "airline_iata", "flight_numbers", "stops",
        "duration_min", "dep_airport", "arr_airport", "best_price", "best_provider", "in_condition",
        "violations", "prices", "best_cond",
    }
    assert by_key["A"]["in_condition"] is True and by_key["A"]["violations"] == []
    assert by_key["B"]["in_condition"] is False and by_key["B"]["violations"] == ["nonstop"]
    assert set(by_key["A"]["prices"][0]) == {
        "provider", "price", "observed_at", "booking_url", "stale", "cond_price", "cond_label", "cond_booking_url",
    }
    assert len(d["candidates"]) == 1
    assert {k: d["candidates"][0][k] for k in ("out_flight_key", "in_flight_key", "price")} == {
        "out_flight_key": "A", "in_flight_key": "C", "price": 170000,
    }
    assert isinstance(d["candidates"][0]["stay_min"], int)
    assert set(d["near_miss"]) == {"direction", "flight_key", "violated", "combo_price", "saving"}
    assert d["near_miss"]["flight_key"] == "B" and d["near_miss"]["violated"] == "nonstop"
    assert d["providers"][0]["provider"] == "google_flights" and d["providers"][0]["status"] == "ok"
    assert d["providers"][0]["last_ok_at"] is not None
    assert d["rt_reference"] == []


def test_trip_view_exposes_cond_fields() -> None:
    trip_id = make_trip()
    now = datetime.now(UTC)
    add_run(trip_id, [quote("A", 80000)], [quote("C", 90000)], now)
    naver_out = quote("A", 82000)
    naver_out.cond_price = 75000
    naver_out.cond_label = "카드할인"
    add_run(trip_id, [naver_out], [quote("C", 91000)], now, provider="naver")
    run_id = repo.enqueue_run(trip_id, "manual")
    rts = [RtQuote("KE", "A", 320000), RtQuote("KE", "A", 330000, cond_total_price=300000, cond_label="카드할인")]
    repo.save_snapshot(
        run_id, trip_id, "naver", "roundtrip", None, OUT,
        ProviderResult(status="ok", legs=[], rts=rts, error=None, seconds=0.1), now,
    )
    d = client.get(f"/api/trips/{trip_id}").json()
    a = next(m for m in d["legs"]["out"] if m["flight_key"] == "A")
    assert a["best_cond"] is None or set(a["best_cond"]) == {"price", "label", "provider", "booking_url"}
    assert a["best_cond"] is not None and a["best_cond"]["price"] == 75000
    assert all({"cond_price", "cond_label", "cond_booking_url"} <= set(p) for p in a["prices"])
    ref = d["rt_reference"][0]
    assert ref["rt_provider"] == "naver" and ref["rt_min"] == 320000
    assert ref["cond_rt_min"] == 300000 and ref["cond_label"] == "카드할인"


def test_trip_view_all_stale() -> None:
    trip_id = make_trip()
    old = datetime.now(UTC) - timedelta(days=3)
    add_run(trip_id, [quote("A", 80000)], [quote("C", 90000)], old)
    r = client.get(f"/api/trips/{trip_id}")
    assert r.status_code == 200
    d = r.json()
    assert d["stats"]["current"] is None
    for direction in ("out", "in"):
        for m in d["legs"][direction]:
            assert m["best_price"] is None and m["in_condition"] is False
            assert all(p["stale"] for p in m["prices"])
    assert d["candidates"] == []


def test_trip_view_without_snapshots() -> None:
    trip_id = make_trip()
    d = client.get(f"/api/trips/{trip_id}").json()
    assert d["run"] is None and d["providers"] == [] and d["legs"] == {"out": [], "in": []}


def test_providers_status_and_last_ok() -> None:
    trip_id = make_trip()
    t1 = datetime.now(UTC) - timedelta(hours=2)
    t2 = datetime.now(UTC)
    add_run(trip_id, [quote("A", 80000)], [quote("C", 90000)], t1)
    run2 = repo.enqueue_run(trip_id, "manual")
    repo.save_snapshot(run2, trip_id, "google_flights", "oneway", "out", OUT, result([], "blocked"), t2)
    repo.save_snapshot(run2, trip_id, "google_flights", "oneway", "in", RET, result([quote("C", 1)]), t2)
    (p,) = client.get(f"/api/trips/{trip_id}").json()["providers"]
    assert p["status"] == "blocked"
    assert datetime.fromisoformat(p["observed_at"]) == t2
    assert datetime.fromisoformat(p["last_ok_at"]) == t2


def test_patch_prefs_changes_candidates() -> None:
    trip_id = make_trip()
    add_run(trip_id, [quote("A", 80000, dep="08:00"), quote("B", 70000, dep="23:00")], [quote("C", 90000)], datetime.now(UTC))
    before = client.get(f"/api/trips/{trip_id}").json()
    assert before["candidates"][0]["out_flight_key"] == "B"
    r = client.patch(
        f"/api/trips/{trip_id}",
        json={"prefs": dict(Preferences(out_dep_window=("06:00", "12:00")).to_dict())},
    )
    assert r.status_code == 200
    after = r.json()
    assert set(after) == set(before)
    assert [c["out_flight_key"] for c in after["candidates"]] == ["A"]
    assert after["trip"]["prefs"]["out_dep_window"] == ["06:00", "12:00"]


def test_patch_target_price_null_clears_and_absent_keeps() -> None:
    trip_id = repo.create_trip("FUK", OUT, RET, Preferences(), 150000)
    assert client.patch(f"/api/trips/{trip_id}", json={"tracking": False}).json()["trip"]["target_price"] == 150000
    d = client.patch(f"/api/trips/{trip_id}", json={"target_price": None}).json()
    assert d["trip"]["target_price"] is None and d["trip"]["tracking"] is False
    assert client.patch(f"/api/trips/{trip_id}", json={"target_price": 120000}).json()["trip"]["target_price"] == 120000


def test_manual_run_cooldown_429() -> None:
    trip_id = make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")
    with db.get_conn() as conn:
        conn.cursor().execute("UPDATE search_runs SET status = 'done' WHERE id = %s", (run_id,))
    r = client.post(f"/api/trips/{trip_id}/runs")
    assert r.status_code == 429
    assert 0 < r.json()["retry_after_seconds"] <= 300


def test_manual_run_after_cooldown_enqueues() -> None:
    trip_id = make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")
    with db.get_conn() as conn:
        conn.cursor().execute(
            "UPDATE search_runs SET status = 'done', requested_at = now() - interval '10 minutes' WHERE id = %s",
            (run_id,),
        )
    r = client.post(f"/api/trips/{trip_id}/runs")
    assert r.status_code == 202
    assert r.json()["run_id"] != run_id


def test_manual_run_returns_open_run() -> None:
    trip_id = make_trip()
    run_id = repo.enqueue_run(trip_id, "schedule")
    r = client.post(f"/api/trips/{trip_id}/runs")
    assert r.status_code == 202 and r.json() == {"run_id": run_id}


def test_refresh_all_queues_and_skips() -> None:
    normal = make_trip()
    running = make_trip()
    repo.enqueue_run(running, "schedule")
    cooling = make_trip()
    cid = repo.enqueue_run(cooling, "manual")
    with db.get_conn() as conn:
        conn.cursor().execute("UPDATE search_runs SET status = 'done' WHERE id = %s", (cid,))
    archived = repo.create_trip("FUK", TODAY - timedelta(days=5), TODAY - timedelta(days=2), Preferences())
    r = client.post("/api/trips/refresh")
    assert r.status_code == 200
    data = r.json()
    assert data["queued"] == [normal]
    assert sorted(data["skipped"], key=lambda s: s["reason"]) == sorted(
        [{"trip_id": running, "reason": "running"}, {"trip_id": cooling, "reason": "cooldown"}],
        key=lambda s: s["reason"],
    )
    assert archived not in data["queued"] and archived not in [s["trip_id"] for s in data["skipped"]]
    assert repo.has_open_run(normal)


def test_run_detail() -> None:
    trip_id = make_trip()
    run_id = add_run(trip_id, [quote("A", 1)], [quote("C", 2)], datetime.now(UTC))
    add_run(trip_id, [quote("A", 1)], [], datetime.now(UTC))
    d = client.get(f"/api/runs/{run_id}").json()
    assert d["id"] == run_id and d["status"] == "queued"
    assert sorted((s["direction"], s["kind"], s["status"], s["provider"]) for s in d["snapshots"]) == [
        ("in", "oneway", "ok", "google_flights"),
        ("out", "oneway", "ok", "google_flights"),
    ]


def test_history_daily_points() -> None:
    trip_id = make_trip()
    now = datetime.now(UTC)
    add_run(trip_id, [quote("A", 80000)], [quote("C", 90000)], now - timedelta(days=1))
    add_run(trip_id, [quote("A", 70000)], [quote("C", 90000)], now)
    pts = client.get(f"/api/trips/{trip_id}/history").json()
    assert len(pts) == 2
    assert set(pts[0]) == {"day", "combo", "out_min", "in_min", "partial"}
    assert [p["combo"] for p in pts] == [170000, 160000]


def test_history_runs_points_per_run() -> None:
    trip_id = make_trip()
    now = datetime.now(UTC)
    first = add_run(trip_id, [quote("A", 80000)], [quote("C", 90000)], now - timedelta(hours=3))
    second = add_run(trip_id, [quote("A", 70000)], [quote("C", 90000)], now - timedelta(hours=1))
    repo.finish_run(first, "done")
    repo.finish_run(second, "done")
    running = add_run(trip_id, [quote("A", 40000)], [quote("C", 40000)], now - timedelta(minutes=5))
    add_run(trip_id, [quote("A", 50000)], [quote("C", 50000)], now)  # 진행 중(queued)인 최신 run
    assert repo.claim_next_run() is not None  # 앞선 run은 running — 최신 run만이 아니라 열린 run 전부 제외
    pts = client.get(f"/api/trips/{trip_id}/history/runs").json()
    assert running not in [p["run_id"] for p in pts]
    assert [p["run_id"] for p in pts] == [first, second]
    assert set(pts[0]) == {"run_id", "at", "combo", "out_min", "in_min", "partial"}
    assert [p["combo"] for p in pts] == [170000, 160000]
    assert pts[0]["at"] < pts[1]["at"]


def test_trip_list_items() -> None:
    trip_id = make_trip()
    add_run(trip_id, [quote("A", 80000)], [quote("C", 90000)], datetime.now(UTC))
    past = repo.create_trip("NRT", TODAY - timedelta(days=2), TODAY - timedelta(days=1), Preferences())
    items = {i["id"]: i for i in client.get("/api/trips").json()}
    item = items[trip_id]
    assert set(item) == {
        "id", "destination", "out_date", "ret_date", "days_to_departure", "tracking", "current",
        "current_observed_at", "change_vs_start_pct", "archived",
        "best_combo", "provider_totals", "series", "low", "low_day", "is_low_now", "target_price",
        "next_auto_at", "provider_status", "open_run_id", "last_checked_at",
    }
    assert item["current"] == 170000 and item["current_observed_at"] is not None
    assert item["change_vs_start_pct"] is None and item["archived"] is False
    assert items[past]["archived"] is True and items[past]["current"] is None


def test_list_item_new_trip_nulls() -> None:
    trip_id = make_trip()
    item = next(i for i in client.get("/api/trips").json() if i["id"] == trip_id)
    assert item["best_combo"] is None and item["series"] == []
    assert item["provider_totals"] == {} and item["provider_status"] == {}
    assert item["is_low_now"] is False and item["low"] is None and item["low_day"] is None
    assert item["target_price"] is None and item["open_run_id"] is None
    assert isinstance(item["next_auto_at"], str)


def test_list_item_last_checked_at() -> None:
    trip_id = make_trip()
    item = next(i for i in client.get("/api/trips").json() if i["id"] == trip_id)
    assert item["last_checked_at"] is None
    old = datetime.now(UTC) - timedelta(days=3)
    add_run(trip_id, [quote("A", 80000)], [quote("C", 90000)], old)
    item = next(i for i in client.get("/api/trips").json() if i["id"] == trip_id)
    assert item["best_combo"] is None and item["current_observed_at"] is None
    assert datetime.fromisoformat(item["last_checked_at"]) == old


def test_list_item_best_combo_and_provider_totals() -> None:
    trip_id = make_trip()
    now = datetime.now(UTC)
    add_run(trip_id, [quote("A", 200000)], [quote("C", 150000)], now)
    add_run(trip_id, [quote("A", 180000)], [quote("C", 160000)], now, provider="naver")
    item = next(i for i in client.get("/api/trips").json() if i["id"] == trip_id)
    combo = item["best_combo"]
    assert combo["total"] == 330000 and combo["cond_total"] is None
    assert combo["out"]["best_provider"] == "naver" and combo["in"]["best_provider"] == "google_flights"
    assert set(combo["out"]) == {
        "airline_iata", "airline_name", "dep_time", "arr_time", "stops", "flight_numbers", "best_provider",
    }
    assert item["provider_totals"] == {"google_flights": 350000, "naver": 340000}
    assert item["low"] is None and item["is_low_now"] is False  # 1일치 → 비교 불가
    assert len(item["series"]) == 1 and set(item["series"][0]) >= {"day", "combo", "partial"}


def test_list_item_single_provider_totals() -> None:
    trip_id = make_trip()
    add_run(trip_id, [quote("A", 180000)], [quote("C", 160000)], datetime.now(UTC), provider="naver")
    item = next(i for i in client.get("/api/trips").json() if i["id"] == trip_id)
    assert item["provider_totals"] == {"naver": 340000}


def test_list_item_cond_total() -> None:
    trip_id = make_trip()
    out = quote("A", 171000)
    out.cond_price = 161700
    out.cond_label = "카드할인"
    add_run(trip_id, [out], [quote("C", 150000)], datetime.now(UTC), provider="naver")
    item = next(i for i in client.get("/api/trips").json() if i["id"] == trip_id)
    assert item["best_combo"]["total"] == 321000 and item["best_combo"]["cond_total"] == 311700


def test_list_item_status_and_open_run() -> None:
    trip_id = make_trip()
    now = datetime.now(UTC)
    run_id = repo.enqueue_run(trip_id, "manual")
    repo.save_snapshot(run_id, trip_id, "naver", "oneway", "out", OUT, result([], "blocked"), now)
    repo.save_snapshot(run_id, trip_id, "naver", "oneway", "in", RET, result([quote("C", 1)]), now)
    item = next(i for i in client.get("/api/trips").json() if i["id"] == trip_id)
    assert item["provider_status"] == {"naver": "blocked"}
    assert item["open_run_id"] == run_id
    with db.get_conn() as conn:
        conn.cursor().execute("UPDATE search_runs SET status = 'done' WHERE id = %s", (run_id,))
    item = next(i for i in client.get("/api/trips").json() if i["id"] == trip_id)
    assert item["open_run_id"] is None


def test_trip_view_next_auto_at() -> None:
    trip_id = make_trip()
    assert isinstance(client.get(f"/api/trips/{trip_id}").json()["trip"]["next_auto_at"], str)
    client.patch(f"/api/trips/{trip_id}", json={"tracking": False})
    assert client.get(f"/api/trips/{trip_id}").json()["trip"]["next_auto_at"] is None


def test_unknown_ids_404() -> None:
    assert client.get("/api/trips/999").status_code == 404
    assert client.patch("/api/trips/999", json={"tracking": False}).status_code == 404
    assert client.post("/api/trips/999/runs").status_code == 404
    assert client.get("/api/trips/999/history").status_code == 404
    assert client.get("/api/trips/999/history/runs").status_code == 404
    assert client.delete("/api/trips/999").status_code == 404
    assert client.get("/api/runs/999").status_code == 404


def test_admin_and_health() -> None:
    trip_id = make_trip()
    add_run(trip_id, [quote("A", 1)], [quote("C", 2)], datetime.now(UTC))
    assert client.get("/healthz").json() == {"ok": True}
    runs = client.get("/api/admin/runs").json()
    assert runs[0]["trip_id"] == trip_id and len(runs[0]["snapshots"]) == 2
    stats = client.get("/api/admin/providers?days=7").json()
    assert stats[0]["provider"] == "google_flights" and stats[0]["total"] == 2


def test_spa_fallback_and_api_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "index.html").write_text("<html>spa</html>")
    monkeypatch.setattr(api_main, "_DIST", tmp_path.resolve())
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
    r = client.get("/trips/1")
    assert r.status_code == 200 and "spa" in r.text


def test_lifespan_creates_schema_when_tables_missing():
    from flight_friend import db

    with db.get_conn() as conn:
        conn.cursor().execute(
            "DROP TABLE IF EXISTS alerts, rt_quotes, leg_quotes, snapshots, search_runs, trips CASCADE"
        )
    assert db.schema_ready() is False
    with TestClient(app) as c:
        assert c.get("/healthz").status_code == 200
    assert db.schema_ready() is True


def test_healthz_ok_and_503(monkeypatch):
    assert client.get("/healthz").json() == {"ok": True}
    monkeypatch.setattr("flight_friend.db.schema_ready", lambda: False)
    r = client.get("/healthz")
    assert r.status_code == 503
    assert r.json() == {"ok": False}


def test_inverted_time_window_is_422() -> None:
    inverted = {"out_dep_window": ["18:00", "06:00"]}
    assert client.post("/api/trips", json=body(prefs=inverted)).status_code == 422
    assert repo.list_trips() == []
    trip_id = make_trip()
    assert client.patch(f"/api/trips/{trip_id}", json={"prefs": {"in_dep_window": ["23:00", "01:00"]}}).status_code == 422
    equal = {"out_dep_window": ["08:00", "08:00"]}
    assert client.patch(f"/api/trips/{trip_id}", json={"prefs": equal}).status_code == 200


def test_delete_trip_removes_trip_and_children() -> None:
    trip_id = make_trip()
    other_id = make_trip()
    now = datetime.now(UTC)
    add_run(trip_id, [quote("A", 100_000)], [quote("B", 90_000)], now)
    add_run(other_id, [quote("A", 100_000)], [quote("B", 90_000)], now)
    repo.record_alert(trip_id, "new_low", 190_000)

    resp = client.delete(f"/api/trips/{trip_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/trips/{trip_id}").status_code == 404
    with db.get_conn() as conn:
        cur = conn.cursor()
        for table in ("search_runs", "snapshots", "alerts"):
            cur.execute(f"SELECT count(*) FROM {table} WHERE trip_id = %s", (trip_id,))
            assert cur.fetchone()[0] == 0, table
        cur.execute(
            "SELECT count(*) FROM leg_quotes q JOIN snapshots s ON s.id = q.snapshot_id WHERE s.trip_id = %s",
            (other_id,),
        )
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM leg_quotes WHERE snapshot_id NOT IN (SELECT id FROM snapshots)")
        assert cur.fetchone()[0] == 0
    assert client.get(f"/api/trips/{other_id}").status_code == 200
