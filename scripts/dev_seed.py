"""로컬 개발 DB에 UI 검증용 Trip 4개를 시드한다. 개발 DB 전용.

    DATABASE_URL=postgresql://... python scripts/dev_seed.py [--reset]
    DATABASE_URL=postgresql://... python scripts/dev_seed.py --fake-run <trip_id>   # 진행 표시 확인용

(a) 추적 중 · GF+Naver · 14일치 run · 조건부 요금 · 목표가
(b) Naver만 성공 (GF error)
(c) 스냅샷 없음 (방금 만듦, 대기 중 run)
(d) 보관 (출국일 지남)
"""

import argparse
import os
import random
import sys
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _require_local_db() -> None:
    """모든 모드(seed/--reset/--fake-run)에서 DB에 닿기 전에 로컬 DB인지 확인한다.

    flight_friend.db 가 import 시점에 DATABASE_URL 을 읽으므로 import 전에 호출한다.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL 이 필요합니다 (예: postgresql://flight_user:flight_pass@localhost:5432/flights)")
    host = urlparse(url).hostname
    if host not in ("localhost", "127.0.0.1", "::1"):
        sys.exit(f"dev_seed 는 로컬 DB(localhost/127.0.0.1/::1)에서만 실행됩니다 (host={host})")


_require_local_db()

from flight_friend import db, repo
from flight_friend.types import LegQuote, Preferences, ProviderResult, RtQuote

TODAY = datetime.now(UTC).date()

# (key, iata, name, numbers, dep, arr, minutes, stops, base price)
OUT_FLIGHTS = [
    ("KE787", "KE", "대한항공", ["KE787"], "08:10", "09:50", 100, 0, 182000),
    ("OZ131", "OZ", "아시아나항공", ["OZ131"], "09:30", "11:10", 100, 0, 176000),
    ("7C1401", "7C", "제주항공", ["7C1401"], "06:45", "08:25", 100, 0, 121000),
    ("LJ281", "LJ", "진에어", ["LJ281"], "13:20", "15:00", 100, 0, 118000),
    ("TW231", "TW", "티웨이항공", ["TW231"], "17:05", "18:45", 100, 0, 129000),
    ("KE2201", "KE", "대한항공", ["KE2201", "JL317"], "10:00", "16:30", 390, 1, 143000),
]
IN_FLIGHTS = [
    ("KE788", "KE", "대한항공", ["KE788"], "11:00", "12:40", 100, 0, 178000),
    ("7C1402", "7C", "제주항공", ["7C1402"], "09:50", "11:30", 100, 0, 115000),
    ("LJ282", "LJ", "진에어", ["LJ282"], "16:10", "17:50", 100, 0, 112000),
    ("TW232", "TW", "티웨이항공", ["TW232"], "19:40", "21:20", 100, 0, 125000),
    ("OZ132", "OZ", "아시아나항공", ["OZ132"], "14:25", "16:05", 100, 0, 171000),
]
LONG_LABEL = "현대 M2/M3 Edition2(이용실적 충족시)"


def leg(f: tuple, dest: str, direction: str, price: int, cond: tuple[int, str] | None = None) -> LegQuote:
    key, iata, name, nums, dep, arr, mins, stops, _ = f
    dep_a, arr_a = ("ICN", dest) if direction == "out" else (dest, "ICN")
    return LegQuote(
        flight_key=key,
        airline_iata=iata,
        airline_name=name,
        flight_numbers=nums,
        dep_airport=dep_a,
        arr_airport=arr_a,
        dep_time=dep,
        arr_time=arr,
        duration_min=mins,
        stops=stops,
        price=price,
        booking_url=f"https://example.com/book/{key}",
        search_url="https://example.com/search",
        cond_price=cond[0] if cond else None,
        cond_label=cond[1] if cond else None,
        cond_booking_url=f"https://example.com/cond/{key}" if cond else None,
    )


def ok(legs: list[LegQuote], rts: list[RtQuote] | None = None) -> ProviderResult:
    return ProviderResult(status="ok", legs=legs, rts=rts or [], error=None, seconds=3.2)


def set_run(run_id: int, status: str, requested: datetime) -> None:
    with db.get_conn() as conn:
        conn.cursor().execute(
            "UPDATE search_runs SET status=%s, requested_at=%s, started_at=%s, finished_at=%s WHERE id=%s",
            (status, requested, requested, requested + timedelta(minutes=2), run_id),
        )


def reset() -> None:
    with db.get_conn() as conn:
        conn.cursor().execute(
            "TRUNCATE trips, search_runs, snapshots, leg_quotes, rt_quotes, alerts RESTART IDENTITY CASCADE"
        )


def seed_a(rng: random.Random) -> int:
    out_date, ret_date = TODAY + timedelta(days=60), TODAY + timedelta(days=64)
    trip = repo.create_trip("FUK", out_date, ret_date, Preferences(), target_price=250000)
    now = datetime.now(UTC)
    for i in range(14):
        days_ago = 13 - i
        observed = now - timedelta(days=days_ago, hours=1)
        drift = 1.0 + (days_ago - 6) * 0.012 + rng.uniform(-0.03, 0.03)
        run_id = repo.enqueue_run(trip, "schedule")
        for direction, flights, d in (("out", OUT_FLIGHTS, out_date), ("in", IN_FLIGHTS, ret_date)):
            gf_legs, nv_legs = [], []
            for n, f in enumerate(flights):
                base = int(f[8] * drift / 100) * 100
                gf_legs.append(leg(f, "FUK", direction, base + rng.randint(0, 3) * 1000))
                if n == len(flights) - 1 and direction == "in":
                    continue  # Naver에는 없는 항공편 (GF 단독)
                cond = None
                if n == 0:
                    cond = (base - 14000, LONG_LABEL)
                elif n == 2:
                    cond = (base - 6000, "KB국민 트래블러스")
                nv_legs.append(leg(f, "FUK", direction, base + rng.choice([-2000, 0, 1000]), cond))
            repo.save_snapshot(run_id, trip, "google_flights", "oneway", direction, d, ok(gf_legs), observed)
            repo.save_snapshot(run_id, trip, "naver", "oneway", direction, d, ok(nv_legs), observed)
        rts = [
            RtQuote("7C", "7C1401", int(232000 * drift / 100) * 100),
            RtQuote("LJ", "LJ281", int(226000 * drift / 100) * 100, int(214000 * drift / 100) * 100, LONG_LABEL),
            RtQuote("KE", "KE787", int(361000 * drift / 100) * 100),
        ]
        repo.save_snapshot(run_id, trip, "naver", "roundtrip", None, out_date, ok([], rts), observed)
        set_run(run_id, "done", observed)
    return trip


def seed_b() -> int:
    out_date, ret_date = TODAY + timedelta(days=45), TODAY + timedelta(days=48)
    trip = repo.create_trip("KIX", out_date, ret_date, Preferences(nonstop_only=True))
    observed = datetime.now(UTC) - timedelta(hours=2)
    run_id = repo.enqueue_run(trip, "schedule")
    for direction, flights, d in (("out", OUT_FLIGHTS[:4], out_date), ("in", IN_FLIGHTS[:3], ret_date)):
        legs = [leg(f, "KIX", direction, f[8] + 9000) for f in flights]
        repo.save_snapshot(run_id, trip, "naver", "oneway", direction, d, ok(legs), observed)
        err = ProviderResult(status="error", legs=[], rts=[], error="TimeoutError: page load", seconds=45.0)
        repo.save_snapshot(run_id, trip, "google_flights", "oneway", direction, d, err, observed)
    set_run(run_id, "done", observed)
    return trip


def seed_c() -> int:
    trip = repo.create_trip("NRT", TODAY + timedelta(days=30), TODAY + timedelta(days=34), Preferences())
    repo.enqueue_run(trip, "manual")
    return trip


def seed_d() -> int:
    out_date, ret_date = TODAY - timedelta(days=10), TODAY - timedelta(days=7)
    trip = repo.create_trip("FUK", out_date, ret_date, Preferences(), target_price=200000)
    observed = datetime.now(UTC) - timedelta(days=12)
    run_id = repo.enqueue_run(trip, "schedule")
    for direction, flights, d in (("out", OUT_FLIGHTS[:3], out_date), ("in", IN_FLIGHTS[:3], ret_date)):
        legs = [leg(f, "FUK", direction, f[8]) for f in flights]
        repo.save_snapshot(run_id, trip, "google_flights", "oneway", direction, d, ok(legs), observed)
    set_run(run_id, "done", observed)
    return trip


def fake_run(trip_id: int, interval: float = 2.5) -> None:
    """열린 run(없으면 새 run)에 6개 스냅샷을 interval초 간격으로 넣고 끝낸다 (worker 없이 RunProgress 확인용)."""
    trip = repo.get_trip(trip_id)
    if trip is None:
        sys.exit(f"trip {trip_id} 없음")
    run = repo.latest_run(trip_id)
    run_id = run.id if run is not None and run.status in ("queued", "running") else repo.enqueue_run(trip_id, "manual")
    with db.get_conn() as conn:
        conn.cursor().execute("UPDATE search_runs SET status='running', started_at=now() WHERE id=%s", (run_id,))
    print(f"run {run_id}: {interval}s 간격으로 스냅샷 6개 저장")
    for provider in ("google_flights", "naver"):
        for kind, direction, flights, d in (
            ("oneway", "out", OUT_FLIGHTS[:4], trip.out_date),
            ("oneway", "in", IN_FLIGHTS[:3], trip.ret_date),
            ("roundtrip", None, [], trip.out_date),
        ):
            time.sleep(interval)
            legs = [leg(f, trip.destination, direction or "out", f[8]) for f in flights]
            rts = [RtQuote("7C", "7C1401", 232000)] if kind == "roundtrip" else []
            repo.save_snapshot(run_id, trip_id, provider, kind, direction, d, ok(legs, rts), datetime.now(UTC))
            print(f"  {provider} {kind} {direction}")
    repo.finish_run(run_id, "done")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="V2 테이블을 먼저 비운다 (개발 DB 전용)")
    ap.add_argument("--fake-run", type=int, metavar="TRIP_ID", help="해당 Trip에 가짜 run 진행(스냅샷 6개)을 넣는다")
    args = ap.parse_args()
    db.init_schema()
    if args.fake_run is not None:
        fake_run(args.fake_run)
        return
    if args.reset:
        reset()
    rng = random.Random(42)
    a, b, c, d = seed_a(rng), seed_b(), seed_c(), seed_d()
    print(f"a={a} b={b} c={c} d={d}")


if __name__ == "__main__":
    main()
