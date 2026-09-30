# tests/test_repo_trips_runs.py

from datetime import date, timedelta

from flight_friend import db, repo
from flight_friend.types import Preferences


def _make_trip(**overrides: object) -> int:
    defaults: dict[str, object] = {
        "destination": "FUK",
        "out_date": date(2026, 10, 1),
        "ret_date": date(2026, 10, 5),
        "prefs": Preferences(),
        "target_price": None,
    }
    defaults.update(overrides)
    return repo.create_trip(**defaults)  # type: ignore[arg-type]


def test_create_and_get_trip_roundtrips_prefs():
    prefs = Preferences(
        out_dep_window=("08:00", "14:00"),
        in_dep_window=None,
        nonstop_only=True,
        include_airlines=["TW"],
        exclude_airlines=[],
        max_price=400_000,
        max_duration_min=None,
    )

    trip_id = repo.create_trip(
        destination="FUK",
        out_date=date(2026, 10, 1),
        ret_date=date(2026, 10, 5),
        prefs=prefs,
        target_price=350_000,
    )

    trip = repo.get_trip(trip_id)

    assert trip is not None
    assert trip.id == trip_id
    assert trip.destination == "FUK"
    assert trip.out_date == date(2026, 10, 1)
    assert trip.ret_date == date(2026, 10, 5)
    assert trip.target_price == 350_000
    assert trip.tracking is True
    assert trip.prefs == prefs
    assert trip.prefs.out_dep_window == ("08:00", "14:00")
    assert isinstance(trip.prefs.out_dep_window, tuple)


def test_get_trip_returns_none_for_missing():
    assert repo.get_trip(999_999) is None


def test_list_trips_ordered_by_out_date():
    id_late = _make_trip(destination="OSA", out_date=date(2026, 11, 1), ret_date=date(2026, 11, 5))
    id_early = _make_trip(destination="FUK", out_date=date(2026, 10, 1), ret_date=date(2026, 10, 5))
    id_mid = _make_trip(destination="KIX", out_date=date(2026, 10, 15), ret_date=date(2026, 10, 20))

    trips = repo.list_trips()

    assert [t.id for t in trips] == [id_early, id_mid, id_late]


def test_update_trip_partial():
    trip_id = _make_trip(prefs=Preferences(nonstop_only=False))
    repo.update_trip(trip_id, tracking=False)

    new_prefs = Preferences(nonstop_only=True, max_price=200_000)
    repo.update_trip(trip_id, prefs=new_prefs)

    trip = repo.get_trip(trip_id)
    assert trip is not None
    assert trip.prefs == new_prefs
    assert trip.tracking is False


def test_update_trip_target_price():
    trip_id = _make_trip(target_price=300_000)

    repo.update_trip(trip_id, target_price=250_000)
    assert repo.get_trip(trip_id).target_price == 250_000  # type: ignore[union-attr]

    repo.update_trip(trip_id, clear_target=True)
    assert repo.get_trip(trip_id).target_price is None  # type: ignore[union-attr]


def test_enqueue_and_get_run():
    trip_id = _make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")

    run = repo.get_run(run_id)

    assert run is not None
    assert run.id == run_id
    assert run.trip_id == trip_id
    assert run.trigger == "manual"
    assert run.status == "queued"
    assert run.started_at is None
    assert run.finished_at is None


def test_get_run_returns_none_for_missing():
    assert repo.get_run(999_999) is None


def test_latest_run_returns_most_recently_requested():
    trip_id = _make_trip()
    first_id = repo.enqueue_run(trip_id, "schedule")
    second_id = repo.enqueue_run(trip_id, "manual")

    latest = repo.latest_run(trip_id)

    assert latest is not None
    assert latest.id == second_id
    assert first_id != second_id


def test_latest_run_returns_none_when_no_runs():
    trip_id = _make_trip()
    assert repo.latest_run(trip_id) is None


def test_claim_is_fifo_and_single():
    trip_id = _make_trip()
    first_run_id = repo.enqueue_run(trip_id, "schedule")
    second_run_id = repo.enqueue_run(trip_id, "manual")

    claimed_first = repo.claim_next_run()
    assert claimed_first is not None
    assert claimed_first.id == first_run_id
    assert claimed_first.status == "running"
    assert claimed_first.started_at is not None

    claimed_second = repo.claim_next_run()
    assert claimed_second is not None
    assert claimed_second.id == second_run_id
    assert claimed_second.status == "running"

    assert repo.claim_next_run() is None


def test_finish_run():
    trip_id = _make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")
    repo.claim_next_run()

    repo.finish_run(run_id, "done")

    run = repo.get_run(run_id)
    assert run is not None
    assert run.status == "done"
    assert run.finished_at is not None


def test_expire_stuck_runs():
    trip_id = _make_trip()
    run_id = repo.enqueue_run(trip_id, "manual")
    claimed = repo.claim_next_run()
    assert claimed is not None

    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE search_runs SET started_at = now() - interval '11 minutes' WHERE id = %s",
            (run_id,),
        )

    expired_count = repo.expire_stuck_runs(timedelta(minutes=10))

    assert expired_count == 1
    run = repo.get_run(run_id)
    assert run is not None
    assert run.status == "error"


def test_expire_stuck_runs_ignores_recent():
    trip_id = _make_trip()
    repo.enqueue_run(trip_id, "manual")
    repo.claim_next_run()

    expired_count = repo.expire_stuck_runs(timedelta(minutes=10))

    assert expired_count == 0


def test_has_open_run():
    trip_id = _make_trip()
    assert repo.has_open_run(trip_id) is False

    run_id = repo.enqueue_run(trip_id, "manual")
    assert repo.has_open_run(trip_id) is True

    repo.claim_next_run()
    assert repo.has_open_run(trip_id) is True

    repo.finish_run(run_id, "done")
    assert repo.has_open_run(trip_id) is False
