-- scripts/v1_freeze.sql
--
-- V1 테이블을 public 에서 v1 스키마로 옮겨 동결한다. 데이터는 그대로 남고
-- (분석용으로 v1.raw_legs 등으로 조회), V2 테이블(trips, search_runs, snapshots,
-- leg_quotes, rt_quotes, alerts)은 건드리지 않는다. V1 코드는 커밋 d8e0422 에 있다.
--
-- 실행 전 반드시 백업 (서버, ~/my-flight-friend):
--   mkdir -p backups
--   docker compose exec -T db pg_dump -U flight_user -d flights -Fc > backups/pre_v1_freeze_$(date +%Y%m%d_%H%M).dump
--
-- 실행:
--   docker compose exec -T db psql -U flight_user -d flights -v ON_ERROR_STOP=1 < scripts/v1_freeze.sql
--
-- 되돌리기: 각 문장의 SET SCHEMA v1 을 SET SCHEMA public 으로 바꿔 실행 (예: ALTER TABLE v1.deals SET SCHEMA public).
-- 멱등: 이미 옮긴 객체는 IF EXISTS 로 건너뛴다.

BEGIN;

CREATE SCHEMA IF NOT EXISTS v1;

-- 뷰 (deals 기반) — 테이블과 함께 이동. 의존성은 OID 기준이라 이동 후에도 유효.
ALTER VIEW IF EXISTS public.v_best_observed SET SCHEMA v1;

ALTER TABLE IF EXISTS public.raw_legs        SET SCHEMA v1;
ALTER TABLE IF EXISTS public.flight_legs     SET SCHEMA v1;
ALTER TABLE IF EXISTS public.price_events    SET SCHEMA v1;
ALTER TABLE IF EXISTS public.price_history   SET SCHEMA v1;
ALTER TABLE IF EXISTS public.deals           SET SCHEMA v1;
ALTER TABLE IF EXISTS public.collection_runs SET SCHEMA v1;
ALTER TABLE IF EXISTS public.alert_state     SET SCHEMA v1;
ALTER TABLE IF EXISTS public.airports        SET SCHEMA v1;
ALTER TABLE IF EXISTS public.app_config      SET SCHEMA v1;

-- flight_legs_price_change 트리거는 테이블을 따라 이동한다. 함수 본문이 price_events 를
-- 스키마 없이 참조하므로, 함수도 옮기고 search_path 를 v1 로 고정한다.
-- (ALTER FUNCTION 에는 IF EXISTS 가 없어 DO 블록으로 멱등 처리)
DO $$
BEGIN
    IF to_regprocedure('public.record_price_change()') IS NOT NULL THEN
        ALTER FUNCTION public.record_price_change() SET SCHEMA v1;
    END IF;
    IF to_regprocedure('v1.record_price_change()') IS NOT NULL THEN
        ALTER FUNCTION v1.record_price_change() SET search_path = v1;
    END IF;
END $$;

COMMIT;

-- 확인: public 에는 V2 테이블 6개만 남아야 한다.
\dt public.*
\dt v1.*
