# tests/test_db.py



from flight_friend import db


def test_init_schema_idempotent():
    db.init_schema()
    db.init_schema()

    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN (
                  'trips', 'search_runs', 'snapshots',
                  'leg_quotes', 'rt_quotes', 'alerts'
              )
        """)
        table_names = {row[0] for row in cur.fetchall()}

    assert table_names == {
        "trips", "search_runs", "snapshots", "leg_quotes", "rt_quotes", "alerts",
    }


def test_leg_quotes_cascade_on_snapshot():
    with db.get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO trips (destination, out_date, ret_date)
            VALUES ('FUK', '2026-10-01', '2026-10-05')
            RETURNING id
        """)
        trip_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO search_runs (trip_id, trigger)
            VALUES (%s, 'manual')
            RETURNING id
        """, (trip_id,))
        run_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO snapshots (run_id, trip_id, provider, kind, date, status, card_count)
            VALUES (%s, %s, 'google_flights', 'oneway', '2026-10-01', 'ok', 1)
            RETURNING id
        """, (run_id, trip_id))
        snapshot_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO leg_quotes (
                snapshot_id, flight_key, airline_iata, airline_name, flight_numbers,
                dep_airport, arr_airport, dep_time, arr_time, price
            )
            VALUES (%s, 'k1', 'TW', '티웨이', ARRAY['TW123'], 'ICN', 'FUK', '09:00', '11:00', 100000)
        """, (snapshot_id,))

        cur.execute("DELETE FROM snapshots WHERE id = %s", (snapshot_id,))

        cur.execute("SELECT COUNT(*) FROM leg_quotes WHERE snapshot_id = %s", (snapshot_id,))
        remaining = cur.fetchone()[0]

    assert remaining == 0
