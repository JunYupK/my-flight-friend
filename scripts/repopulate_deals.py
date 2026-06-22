"""
deals 재계산 스크립트

flight_legs에 이미 수집된 편도 레그 데이터로 deals 테이블을 즉시 재구성한다.
재크롤 없이 기존 수집 원본에서 왕복 조합을 계산해 deals에 저장.

배경: sweep 슬라이싱 배포 당일, skip_set이 오늘 이미 수집된 날짜를 막아
deals가 이전 run의 데이터(단일 tick분)만 남는 문제를 수동으로 복구하는 데 사용.
내일부터는 cron이 자동으로 전체 범위를 채우므로 이 스크립트는 불필요하다.

사용법:
    cd /path/to/my-flight-friend
    python scripts/repopulate_deals.py

    # 특정 source/destination만 재계산:
    python scripts/repopulate_deals.py --source google_flights --dest TYO
"""

import os
import sys
import argparse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2.extras

import flight_monitor.config  # noqa: F401
from flight_monitor.config_db import apply_db_config
from flight_monitor.storage import get_conn, init_db, load_legs_for_combine, materialize_deals_for_route


def main():
    parser = argparse.ArgumentParser(description="deals 테이블을 flight_legs에서 재계산")
    parser.add_argument("--source", help="특정 source만 처리 (e.g. google_flights)")
    parser.add_argument("--dest", help="특정 destination만 처리 (e.g. TYO)")
    args = parser.parse_args()

    apply_db_config()
    init_db()

    today = date.today().isoformat()

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        sql = """
            SELECT DISTINCT source, destination, destination_name
            FROM flight_legs
            WHERE date >= %s
        """
        params: list = [today]
        if args.source:
            sql += " AND source = %s"
            params.append(args.source)
        if args.dest:
            sql += " AND destination = %s"
            params.append(args.dest.upper())
        sql += " ORDER BY source, destination"
        cur.execute(sql, params)
        combos = [dict(r) for r in cur.fetchall()]

    if not combos:
        print(f"flight_legs에 {today} 이후 데이터가 없습니다.")
        return

    print(f"총 {len(combos)}개 (source, destination) 조합 처리 중 (기준: {today} 이후)...\n")

    total_deals = 0
    skipped = 0

    for combo in combos:
        src = combo["source"]
        dest = combo["destination"]
        dest_name = combo["destination_name"] or dest

        out_flights, in_flights = load_legs_for_combine(src, dest, since=today)

        if not out_flights or not in_flights:
            print(f"  [{src}] {dest}: out={len(out_flights)}, in={len(in_flights)} — 스킵 (한쪽 레그 없음)")
            skipped += 1
            continue

        n = materialize_deals_for_route(src, dest, dest_name)

        if n:
            total_deals += n
            print(f"  [{src}] {dest}: {n}건 저장")
        else:
            print(f"  [{src}] {dest}: 왕복 조합 0건 — out/in 날짜 겹침 없음 "
                  f"(out {len(out_flights)}건, in {len(in_flights)}건)")
            skipped += 1

    print(f"\n완료: {total_deals}건 deals 저장, {skipped}개 조합 스킵")


if __name__ == "__main__":
    main()
