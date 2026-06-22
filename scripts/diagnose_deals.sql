-- scripts/diagnose_deals.sql
--
-- /deals에 목적지가 듬성듬성 뜨는 원인 진단.
-- 크롤 부분실패(legs 누락) vs 조합 실패(legs는 있는데 deal 없음)를 구분한다.
--
-- 실행:
--   psql "postgresql://flight_user:flight_pass@localhost:5432/flights" -f scripts/diagnose_deals.sql
--   또는 docker compose exec db psql -U flight_user -d flights -f /...

\echo '═══════════════════════════════════════════════════════════'
\echo '0. 등록된 공항(목적지) 목록 — 전체 수집 대상'
\echo '═══════════════════════════════════════════════════════════'
SELECT code, name FROM airports ORDER BY code;

\echo ''
\echo '═══════════════════════════════════════════════════════════'
\echo '1. deals 현황: 목적지 × 월별 deal 수 (현재 화면에 뜨는 것)'
\echo '═══════════════════════════════════════════════════════════'
SELECT destination,
       LEFT(departure_date, 7)      AS month,
       COUNT(*)                     AS deals,
       MIN(min_price)::int          AS best_price,
       MAX(last_checked_at)         AS last_updated
FROM deals
WHERE departure_date >= to_char(NOW(), 'YYYY-MM-DD')
GROUP BY destination, month
ORDER BY destination, month;

\echo ''
\echo '═══════════════════════════════════════════════════════════'
\echo '2. 목적지 × 월 격자 — deals 유무 한눈에 (피벗)'
\echo '   값 = deal 수, 빈칸 = 그 달에 그 목적지 deal 없음'
\echo '═══════════════════════════════════════════════════════════'
SELECT destination,
       COUNT(*) FILTER (WHERE LEFT(departure_date,7) = to_char(NOW(),                'YYYY-MM')) AS m0,
       COUNT(*) FILTER (WHERE LEFT(departure_date,7) = to_char(NOW()+INTERVAL '1 mon','YYYY-MM')) AS m1,
       COUNT(*) FILTER (WHERE LEFT(departure_date,7) = to_char(NOW()+INTERVAL '2 mon','YYYY-MM')) AS m2,
       COUNT(*) FILTER (WHERE LEFT(departure_date,7) = to_char(NOW()+INTERVAL '3 mon','YYYY-MM')) AS m3,
       COUNT(*) FILTER (WHERE LEFT(departure_date,7) = to_char(NOW()+INTERVAL '4 mon','YYYY-MM')) AS m4,
       COUNT(*) FILTER (WHERE LEFT(departure_date,7) = to_char(NOW()+INTERVAL '5 mon','YYYY-MM')) AS m5,
       COUNT(*)                                                                                   AS total
FROM deals
WHERE departure_date >= to_char(NOW(), 'YYYY-MM-DD')
GROUP BY destination
ORDER BY destination;

\echo ''
\echo '═══════════════════════════════════════════════════════════'
\echo '3. flight_legs 현황: 목적지 × 방향 × 월 (크롤이 실제로 된 양)'
\echo '   out/in 한쪽만 있으면 조합 불가 → deal 0건'
\echo '═══════════════════════════════════════════════════════════'
SELECT destination,
       LEFT(date, 7)            AS month,
       direction,
       COUNT(DISTINCT date)     AS distinct_dates,
       COUNT(*)                 AS legs,
       MIN(price)::int          AS min_price
FROM flight_legs
WHERE date >= to_char(NOW(), 'YYYY-MM-DD')
GROUP BY destination, month, direction
ORDER BY destination, month, direction;

\echo ''
\echo '═══════════════════════════════════════════════════════════'
\echo '4. 진단 핵심: legs는 양방향 다 있는데 deal이 0인 (목적지,월)'
\echo '   → 크롤은 됐으나 날짜 정렬(D+3/4/5)이 안 맞아 조합 실패한 케이스'
\echo '═══════════════════════════════════════════════════════════'
WITH legs AS (
    SELECT destination, LEFT(date,7) AS month,
           COUNT(*) FILTER (WHERE direction='out') AS out_legs,
           COUNT(*) FILTER (WHERE direction='in')  AS in_legs
    FROM flight_legs
    WHERE date >= to_char(NOW(), 'YYYY-MM-DD')
    GROUP BY destination, month
),
d AS (
    SELECT destination, LEFT(departure_date,7) AS month, COUNT(*) AS deals
    FROM deals
    WHERE departure_date >= to_char(NOW(), 'YYYY-MM-DD')
    GROUP BY destination, month
)
SELECT legs.destination, legs.month,
       legs.out_legs, legs.in_legs,
       COALESCE(d.deals, 0) AS deals,
       CASE
         WHEN legs.out_legs = 0 OR legs.in_legs = 0 THEN 'CRAWL_FAIL (한쪽 방향 누락)'
         WHEN COALESCE(d.deals,0) = 0               THEN 'COMBINE_FAIL (날짜 정렬 안맞음)'
         ELSE 'OK'
       END AS verdict
FROM legs
LEFT JOIN d ON d.destination = legs.destination AND d.month = legs.month
WHERE legs.out_legs = 0 OR legs.in_legs = 0 OR COALESCE(d.deals,0) = 0
ORDER BY legs.destination, legs.month;

\echo ''
\echo '═══════════════════════════════════════════════════════════'
\echo '5. 최근 수집 run 상태 (death spiral / 부분실패 여부)'
\echo '═══════════════════════════════════════════════════════════'
SELECT id, started_at, status,
       google_count, naver_count, total_saved, alerts_sent,
       ROUND(duration_sec)::int AS dur_sec,
       error_log IS NOT NULL AS has_error
FROM collection_runs
ORDER BY started_at DESC
LIMIT 12;

\echo ''
\echo '═══════════════════════════════════════════════════════════'
\echo '6. 오늘(KST) 수집된 raw_legs — tick별 목적지 커버리지'
\echo '   슬라이스별로 어느 목적지가 실제 크롤됐는지'
\echo '═══════════════════════════════════════════════════════════'
SELECT source,
       LEFT(date, 7)         AS dep_month,
       COUNT(DISTINCT destination) AS dests,
       COUNT(DISTINCT date)        AS dates,
       COUNT(*)                    AS legs
FROM raw_legs
WHERE collected_at >= CURRENT_DATE
GROUP BY source, dep_month
ORDER BY source, dep_month;
