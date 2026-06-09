#!/usr/bin/env python3
"""DB 데이터 신뢰성 진단 스크립트.

OCI 서버에서 실행:
  cd /path/to/my-flight-friend
  DATABASE_URL=... python scripts/diagnose_db.py

또는 .env가 있으면:
  python scripts/diagnose_db.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import psycopg2.extras

DSN = os.environ.get("DATABASE_URL", "")
if not DSN:
    sys.exit("DATABASE_URL 환경변수가 없습니다.")


def conn():
    c = psycopg2.connect(DSN)
    c.cursor().execute("SET TIME ZONE 'Asia/Seoul'")
    return c


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def q(sql: str, params=None, label: str = ""):
    with conn() as c:
        cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
    if label:
        print(f"\n--- {label} ---")
    for r in rows:
        print("  " + " | ".join(f"{k}: {v}" for k, v in r.items()))
    if not rows:
        print("  (결과 없음)")
    return rows


# ────────────────────────────────────────────────────────────────
# 1. 수집 실행 이력
# ────────────────────────────────────────────────────────────────
section("1. 최근 수집 실행 이력 (collection_runs)")

q("""
    SELECT
        id,
        TO_CHAR(started_at, 'YYYY-MM-DD HH24:MI') AS started,
        status,
        google_count,
        COALESCE(naver_count, 0) AS naver_count,
        total_saved,
        alerts_sent,
        ROUND(duration_sec::numeric, 1) AS duration_sec,
        (error_log IS NOT NULL) AS has_error
    FROM collection_runs
    ORDER BY started_at DESC
    LIMIT 20
""", label="최근 20회 실행")

q("""
    SELECT
        status,
        COUNT(*) AS runs,
        ROUND(AVG(duration_sec)::numeric, 1) AS avg_sec,
        SUM(google_count) AS total_google,
        SUM(COALESCE(naver_count, 0)) AS total_naver,
        SUM(total_saved) AS total_combos
    FROM collection_runs
    GROUP BY status
    ORDER BY runs DESC
""", label="상태별 집계")

q("""
    SELECT id, TO_CHAR(started_at, 'YYYY-MM-DD HH24:MI') AS started,
           LEFT(error_log, 300) AS error_snippet
    FROM collection_runs
    WHERE error_log IS NOT NULL
    ORDER BY started_at DESC
    LIMIT 5
""", label="최근 에러 로그 (최대 5건)")


# ────────────────────────────────────────────────────────────────
# 2. raw_legs: 원본 수집 데이터
# ────────────────────────────────────────────────────────────────
section("2. raw_legs — 원본 수집 로그")

q("""
    SELECT
        COUNT(*) AS total_rows,
        COUNT(DISTINCT destination) AS destinations,
        MIN(collected_at) AS oldest,
        MAX(collected_at) AS newest
    FROM raw_legs
""", label="전체 현황")

q("""
    SELECT
        source,
        direction,
        COUNT(*) AS rows,
        COUNT(DISTINCT destination) AS dests,
        COUNT(DISTINCT date) AS dates,
        MIN(price) AS min_price,
        ROUND(AVG(price)::numeric) AS avg_price,
        MAX(price) AS max_price
    FROM raw_legs
    GROUP BY source, direction
    ORDER BY source, direction
""", label="소스×방향별 통계")

q("""
    SELECT
        DATE(collected_at) AS day,
        source,
        COUNT(*) AS rows
    FROM raw_legs
    WHERE collected_at >= NOW() - INTERVAL '7 days'
    GROUP BY day, source
    ORDER BY day DESC, source
""", label="최근 7일 일별 수집량")

q("""
    SELECT destination, COUNT(*) AS rows,
           MIN(price) AS min_p, MAX(price) AS max_p,
           ROUND(AVG(price)::numeric) AS avg_p
    FROM raw_legs
    WHERE collected_at >= NOW() - INTERVAL '3 days'
    GROUP BY destination
    ORDER BY destination
""", label="최근 3일 목적지별 가격 분포")


# ────────────────────────────────────────────────────────────────
# 3. raw_legs NULL / 이상치 검증
# ────────────────────────────────────────────────────────────────
section("3. raw_legs NULL 및 이상치")

q("""
    SELECT
        COUNT(*) FILTER (WHERE airline IS NULL OR airline = '') AS null_airline,
        COUNT(*) FILTER (WHERE dep_time IS NULL) AS null_dep_time,
        COUNT(*) FILTER (WHERE arr_time IS NULL) AS null_arr_time,
        COUNT(*) FILTER (WHERE duration_min IS NULL) AS null_duration,
        COUNT(*) FILTER (WHERE stops IS NULL) AS null_stops,
        COUNT(*) FILTER (WHERE dep_airport IS NULL) AS null_dep_airport,
        COUNT(*) FILTER (WHERE arr_airport IS NULL) AS null_arr_airport,
        COUNT(*) AS total
    FROM raw_legs
    WHERE collected_at >= NOW() - INTERVAL '7 days'
""", label="최근 7일 NULL 비율")

q("""
    SELECT price, source, destination, date, direction, airline,
           TO_CHAR(collected_at, 'YYYY-MM-DD HH24:MI') AS collected_at
    FROM raw_legs
    WHERE price < 20000 OR price > 3000000
    ORDER BY collected_at DESC
    LIMIT 20
""", label="가격 이상치 (20K 미만 or 300만 초과)")

q("""
    SELECT source, destination, date, direction,
           COUNT(*) AS duplicates,
           MIN(price) AS min_p, MAX(price) AS max_p
    FROM raw_legs
    WHERE collected_at >= NOW() - INTERVAL '7 days'
    GROUP BY source, destination, date, direction
    HAVING COUNT(*) > 10
    ORDER BY duplicates DESC
    LIMIT 20
""", label="같은 날짜/방향 레코드 10건 초과 (중복 과다 의심)")

q("""
    SELECT airline, COUNT(*) AS cnt
    FROM raw_legs
    WHERE collected_at >= NOW() - INTERVAL '7 days'
    GROUP BY airline
    ORDER BY cnt DESC
    LIMIT 30
""", label="항공사명 분포 (한글명/코드 혼재 여부 확인)")


# ────────────────────────────────────────────────────────────────
# 4. flight_legs: UPSERT 현재 상태
# ────────────────────────────────────────────────────────────────
section("4. flight_legs — 현재 최저가 상태")

q("""
    SELECT
        COUNT(*) AS total_rows,
        COUNT(DISTINCT destination) AS destinations,
        COUNT(DISTINCT date) AS dates,
        MIN(price) AS min_price,
        MAX(price) AS max_price,
        ROUND(AVG(price)::numeric) AS avg_price
    FROM flight_legs
""", label="전체 현황")

q("""
    SELECT
        source,
        direction,
        COUNT(*) AS rows,
        MIN(price) AS min_p,
        ROUND(AVG(price)::numeric) AS avg_p,
        MAX(price) AS max_p
    FROM flight_legs
    GROUP BY source, direction
    ORDER BY source, direction
""", label="소스×방향별 분포")

q("""
    SELECT destination, direction,
           COUNT(*) AS leg_count,
           MIN(date) AS earliest_date,
           MAX(date) AS latest_date,
           MIN(price) AS min_p, MAX(price) AS max_p
    FROM flight_legs
    GROUP BY destination, direction
    ORDER BY destination, direction
""", label="목적지×방향별 현황")

q("""
    SELECT
        COUNT(*) FILTER (WHERE dep_airport IS NULL) AS null_dep_airport,
        COUNT(*) FILTER (WHERE arr_airport IS NULL) AS null_arr_airport,
        COUNT(*) FILTER (WHERE airline IS NULL OR airline = '') AS null_airline,
        COUNT(*) FILTER (WHERE dep_time IS NULL) AS null_dep_time,
        COUNT(*) FILTER (WHERE duration_min IS NULL) AS null_duration,
        COUNT(*) AS total
    FROM flight_legs
""", label="NULL 비율")


# ────────────────────────────────────────────────────────────────
# 5. price_events: 가격 변동 트리거 이력
# ────────────────────────────────────────────────────────────────
section("5. price_events — 가격 변동 이력")

q("""
    SELECT COUNT(*) AS total_events,
           MIN(changed_at) AS oldest,
           MAX(changed_at) AS newest
    FROM price_events
""", label="전체 현황")

q("""
    SELECT destination, direction,
           COUNT(*) AS events,
           ROUND(AVG(new_price - old_price)::numeric) AS avg_delta_krw,
           MIN(new_price - old_price) AS max_drop,
           MAX(new_price - old_price) AS max_rise
    FROM price_events
    GROUP BY destination, direction
    ORDER BY events DESC
""", label="목적지×방향별 가격 변동 패턴")


# ────────────────────────────────────────────────────────────────
# 6. price_history (레거시 테이블 현황)
# ────────────────────────────────────────────────────────────────
section("6. price_history — 레거시 테이블 현황 (신규 쓰기 없음)")

q("""
    SELECT
        COUNT(*) AS total_rows,
        MIN(checked_at) AS oldest,
        MAX(checked_at) AS newest,
        COUNT(DISTINCT destination) AS destinations
    FROM price_history
""", label="전체 현황 (마지막 수집일 확인)")


# ────────────────────────────────────────────────────────────────
# 7. 교차 검증: raw_legs ↔ flight_legs 정합성
# ────────────────────────────────────────────────────────────────
section("7. raw_legs ↔ flight_legs 정합성")

q("""
    WITH raw_counts AS (
        SELECT source, destination, date, direction, COUNT(*) AS raw_cnt
        FROM raw_legs
        WHERE collected_at >= NOW() - INTERVAL '3 days'
        GROUP BY source, destination, date, direction
    ),
    leg_exists AS (
        SELECT DISTINCT source, destination, date, direction
        FROM flight_legs
    )
    SELECT
        rc.source,
        rc.destination,
        rc.date,
        rc.direction,
        rc.raw_cnt,
        CASE WHEN le.destination IS NOT NULL THEN 'YES' ELSE 'NO' END AS in_flight_legs
    FROM raw_counts rc
    LEFT JOIN leg_exists le
        ON rc.source = le.source
        AND rc.destination = le.destination
        AND rc.date = le.date
        AND rc.direction = le.direction
    WHERE le.destination IS NULL
    ORDER BY rc.destination, rc.date, rc.direction
    LIMIT 30
""", label="raw_legs에만 있고 flight_legs에 없는 조합 (UPSERT 누락 의심)")

q("""
    SELECT
        fl.source,
        fl.destination,
        fl.date,
        fl.direction,
        fl.price AS flight_legs_price,
        MIN(rl.price) AS raw_legs_min_price,
        ABS(fl.price - MIN(rl.price)) AS diff
    FROM flight_legs fl
    JOIN raw_legs rl
        ON fl.source = rl.source
        AND fl.destination = rl.destination
        AND fl.date = rl.date
        AND fl.direction = rl.direction
    WHERE rl.collected_at >= NOW() - INTERVAL '7 days'
    GROUP BY fl.source, fl.destination, fl.date, fl.direction, fl.price
    HAVING fl.price > MIN(rl.price) + 1000
    ORDER BY diff DESC
    LIMIT 20
""", label="flight_legs 가격이 raw_legs 최솟값보다 1000원 이상 높은 경우 (UPSERT 오작동 의심)")


# ────────────────────────────────────────────────────────────────
# 8. 출발일별 커버리지 (날짜별 수집 공백 탐지)
# ────────────────────────────────────────────────────────────────
section("8. 날짜별 수집 커버리지")

q("""
    SELECT
        destination,
        DATE_TRUNC('month', date::date) AS month,
        COUNT(DISTINCT date) AS days_with_data,
        MIN(price) AS best_price
    FROM flight_legs
    WHERE direction = 'out'
      AND date >= TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
    GROUP BY destination, month
    ORDER BY destination, month
""", label="목적지×월별 출발편 커버리지 (향후 날짜)")

q("""
    WITH all_dates AS (
        SELECT generate_series(
            CURRENT_DATE,
            CURRENT_DATE + INTERVAL '30 days',
            '1 day'::interval
        )::date AS d
    ),
    covered AS (
        SELECT DISTINCT destination, date::date AS d
        FROM flight_legs WHERE direction = 'out'
    )
    SELECT
        ad.d AS date,
        COUNT(DISTINCT cv.destination) AS destinations_with_data
    FROM all_dates ad
    LEFT JOIN covered cv ON ad.d = cv.d
    GROUP BY ad.d
    ORDER BY ad.d
""", label="향후 30일 날짜별 커버된 목적지 수")


# ────────────────────────────────────────────────────────────────
# 9. airports 테이블 현황
# ────────────────────────────────────────────────────────────────
section("9. airports 설정 현황")

q("""
    SELECT code, name,
           CASE WHEN tfs_out IS NOT NULL THEN 'Y' ELSE 'N' END AS has_tfs_out,
           CASE WHEN tfs_in  IS NOT NULL THEN 'Y' ELSE 'N' END AS has_tfs_in
    FROM airports
    ORDER BY code
""", label="등록된 공항 및 tfs 템플릿 보유 여부")


# ────────────────────────────────────────────────────────────────
# 10. Naver vs Google 가격 편차 분석
# ────────────────────────────────────────────────────────────────
section("10. Naver vs Google 가격 편차 분석")

q("""
    SELECT
        destination,
        direction,
        COUNT(*) FILTER (WHERE source='google_flights') AS gf_count,
        ROUND(AVG(price) FILTER (WHERE source='google_flights')::numeric) AS gf_avg,
        MIN(price) FILTER (WHERE source='google_flights') AS gf_min,
        MAX(price) FILTER (WHERE source='google_flights') AS gf_max,
        COUNT(*) FILTER (WHERE source='naver') AS nv_count,
        ROUND(AVG(price) FILTER (WHERE source='naver')::numeric) AS nv_avg,
        MIN(price) FILTER (WHERE source='naver') AS nv_min,
        MAX(price) FILTER (WHERE source='naver') AS nv_max,
        ROUND((AVG(price) FILTER (WHERE source='naver') -
               AVG(price) FILTER (WHERE source='google_flights'))::numeric) AS avg_diff_nv_minus_gf
    FROM flight_legs
    WHERE checked_at >= NOW() - INTERVAL '7 days'
    GROUP BY destination, direction
    HAVING COUNT(*) FILTER (WHERE source='google_flights') > 0
       AND COUNT(*) FILTER (WHERE source='naver') > 0
    ORDER BY ABS(AVG(price) FILTER (WHERE source='naver') -
                 AVG(price) FILTER (WHERE source='google_flights')) DESC NULLS LAST
""", label="소스별 편도 가격 비교 (최근 7일, 두 소스 모두 있는 노선)")

q("""
    SELECT
        rl.destination, rl.date, rl.direction,
        rl.price AS naver_price,
        rl.collected_at,
        gf_avg.avg_gf_price,
        ROUND((rl.price - gf_avg.avg_gf_price)::numeric) AS diff
    FROM raw_legs rl
    JOIN (
        SELECT destination, date, direction, AVG(price) AS avg_gf_price
        FROM raw_legs
        WHERE source = 'google_flights'
          AND collected_at >= NOW() - INTERVAL '30 days'
        GROUP BY destination, date, direction
    ) gf_avg
        ON rl.destination = gf_avg.destination
        AND rl.date = gf_avg.date
        AND rl.direction = gf_avg.direction
    WHERE rl.source = 'naver'
      AND rl.collected_at >= NOW() - INTERVAL '30 days'
      AND rl.price > gf_avg.avg_gf_price * 1.8
    ORDER BY diff DESC
    LIMIT 30
""", label="Naver 가격이 Google 평균의 180% 초과인 레그 (오염 의심)")

# tripType=OW 추가 이전(2026-06-04) Naver 데이터 가격 분포
q("""
    SELECT
        '2026-06-04 이전' AS period,
        COUNT(*) AS rows,
        MIN(price) AS min_p,
        ROUND(AVG(price)::numeric) AS avg_p,
        MAX(price) AS max_p,
        ROUND(STDDEV(price)::numeric) AS stddev_p
    FROM raw_legs
    WHERE source = 'naver'
      AND collected_at < '2026-06-04 00:00:00'
    UNION ALL
    SELECT
        '2026-06-04 이후' AS period,
        COUNT(*) AS rows,
        MIN(price) AS min_p,
        ROUND(AVG(price)::numeric) AS avg_p,
        MAX(price) AS max_p,
        ROUND(STDDEV(price)::numeric) AS stddev_p
    FROM raw_legs
    WHERE source = 'naver'
      AND collected_at >= '2026-06-04 00:00:00'
    ORDER BY period
""", label="tripType=OW 추가 전후 Naver 가격 분포 비교 (2026-06-04 기준)")

q("""
    SELECT COUNT(*) AS contaminated_rows
    FROM raw_legs
    WHERE source = 'naver'
      AND collected_at < '2026-06-04 00:00:00'
      AND price > 200000
""", label="OW 추가 전 Naver 데이터 중 20만원 초과 (왕복 기준 의심) 건수")

q("""
    SELECT
        COUNT(DISTINCT (o.destination, o.date, i.date)) AS cross_source_combos,
        COUNT(*) AS total_cross_rows
    FROM flight_legs o
    JOIN flight_legs i
        ON o.destination = i.destination
        AND (i.date::date - o.date::date) BETWEEN 3 AND 5
    WHERE o.direction = 'out' AND i.direction = 'in'
      AND o.source != i.source
      AND o.checked_at >= CURRENT_DATE
      AND i.checked_at >= CURRENT_DATE
""", label="현재 교차 소스 왕복 조합 가능 건수 (out≠in source)")


print(f"\n\n{'='*60}")
print("  진단 완료")
print(f"  실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print('='*60)
