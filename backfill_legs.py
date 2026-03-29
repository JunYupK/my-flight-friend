#!/usr/bin/env python3
"""price_history 오늘치 → flight_legs 백필 (1회성 실행 스크립트)"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from flight_monitor.storage import get_conn, save_legs

BATCH_SIZE = 2000


def backfill():
    print("price_history 오늘치 조회 중...")
    with get_conn() as conn:
        cur = conn.cursor(name="backfill_cursor")
        cur.execute("""
            SELECT source, origin, destination, destination_name,
                   departure_date, out_airline, out_dep_time, out_arr_time,
                   out_duration_min, out_stops, out_arr_airport, out_url, out_price,
                   return_date, in_airline, in_dep_time, in_arr_time,
                   in_duration_min, in_stops, in_dep_airport, in_url, in_price,
                   checked_at
            FROM price_history
            WHERE checked_at >= CURRENT_DATE
              AND (out_price IS NOT NULL OR in_price IS NOT NULL)
        """)

        legs_batch = []
        total_saved = 0

        while True:
            rows = cur.fetchmany(BATCH_SIZE)
            if not rows:
                break

            for row in rows:
                (source, origin, destination, destination_name,
                 dep_date, out_airline, out_dep_time, out_arr_time,
                 out_duration_min, out_stops, out_arr_airport, out_url, out_price,
                 ret_date, in_airline, in_dep_time, in_arr_time,
                 in_duration_min, in_stops, in_dep_airport, in_url, in_price,
                 checked_at) = row

                if out_price is not None:
                    legs_batch.append({
                        "source": source, "origin": origin,
                        "destination": destination, "destination_name": destination_name,
                        "date": dep_date, "direction": "out",
                        "airline": out_airline,
                        "dep_time": out_dep_time, "arr_time": out_arr_time,
                        "duration_min": out_duration_min, "stops": out_stops,
                        "dep_airport": None, "arr_airport": out_arr_airport,
                        "price": out_price, "booking_url": None, "search_url": out_url,
                        "checked_at": checked_at,
                    })

                if in_price is not None:
                    legs_batch.append({
                        "source": source, "origin": origin,
                        "destination": destination, "destination_name": destination_name,
                        "date": ret_date, "direction": "in",
                        "airline": in_airline,
                        "dep_time": in_dep_time, "arr_time": in_arr_time,
                        "duration_min": in_duration_min, "stops": in_stops,
                        "dep_airport": in_dep_airport, "arr_airport": None,
                        "price": in_price, "booking_url": None, "search_url": in_url,
                        "checked_at": checked_at,
                    })

            if legs_batch:
                save_legs(legs_batch)
                total_saved += len(legs_batch)
                print(f"  {total_saved}개 저장됨...")
                legs_batch = []

    print(f"백필 완료: 총 {total_saved}개 레그 저장")


if __name__ == "__main__":
    backfill()
