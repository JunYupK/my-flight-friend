import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import traceback
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from flight_monitor.config import KST

from dotenv import load_dotenv
load_dotenv()
import flight_monitor.config  # noqa: F401 — sys.modules에 먼저 올려두기
from flight_monitor.config_db import apply_db_config
apply_db_config()

from flight_monitor.collector_google_flights import fetch_google_flights_offers
from flight_monitor.collector_naver          import fetch_naver_offers
from flight_monitor.storage                  import init_db, should_notify, record_alert, start_collection_run, finish_collection_run, save_deals, cleanup_old_data
from flight_monitor.notifier                 import notify, send_alert
from flight_monitor.config                   import SEARCH_CONFIG


def _ts() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def main():
    print(f"[{_ts()}] === 일본 항공권 최저가 탐색 시작 ===")
    init_db()

    run_id = start_collection_run()

    try:
        _collect_and_alert(run_id)
    except Exception:
        # main 내부 예상치 못한 에러 → running 상태 run을 error로 마무리
        finish_collection_run(
            run_id,
            status="error",
            error_log=f"FATAL in main():\n{traceback.format_exc()}",
        )
        raise


def _collect_and_alert(run_id: int):
    errors: list[str] = []
    alerts_sent = 0

    # --- Google Flights + Naver 병렬 수집 ---
    # on_route_done=save_deals: 공항별 수집 완료 즉시 deals를 증분 갱신한다.
    # run이 중간에 죽어도 완료된 공항만큼은 사이트에 신선하게 반영 → 유사 장애 방지.
    with ThreadPoolExecutor(max_workers=2) as pool:
        gf_future: Future = pool.submit(fetch_google_flights_offers, save_deals)
        nv_future: Future = pool.submit(fetch_naver_offers, save_deals)

    gf_offers: list[dict] = []
    nv_offers: list[dict] = []

    try:
        gf_offers = gf_future.result()
    except Exception as e:
        errors.append(f"GoogleFlights 수집 에러: {e}\n{traceback.format_exc()}")
        print(f"[{_ts()}] [ERROR] GoogleFlights 수집 실패: {e}")
        traceback.print_exc()

    try:
        nv_offers = nv_future.result()
    except Exception as e:
        errors.append(f"Naver 수집 에러: {e}\n{traceback.format_exc()}")
        print(f"[{_ts()}] [ERROR] Naver 수집 실패: {e}")
        traceback.print_exc()

    all_offers = gf_offers + nv_offers
    print(f"[{_ts()}] [수집] GoogleFlights {len(gf_offers)}건, Naver {len(nv_offers)}건")

    # --- 수집 결과 0건 경고 ---
    if not all_offers:
        msg = (
            f"[{_ts()}] [WARN] 수집 결과 0건!\n"
            f"GoogleFlights: {len(gf_offers)}건\n"
            f"Naver: {len(nv_offers)}건\n"
        )
        if errors:
            msg += "에러 목록:\n" + "\n".join(f"  - {e}" for e in errors)
        print(msg)
        send_alert(f"[항공권 모니터] 수집 결과 0건 경고\n{msg}")

    # --- deals 사전계산 저장 (읽기 최적화) ---
    try:
        save_deals(all_offers)
    except Exception as e:
        errors.append(f"save_deals 에러: {e}\n{traceback.format_exc()}")
        print(f"[{_ts()}] [ERROR] save_deals 실패: {e}")

    # --- 알림 처리 (목적지 × 출발월 단위 집약) ---
    # all_offers를 (destination, month)별 최저가 1건으로 줄여서 알림 폭주 방지.
    target = SEARCH_CONFIG["target_price_krw"]
    best_by_dest_month: dict[tuple[str, str], dict] = {}
    for o in all_offers:
        if o["price"] > target:
            continue
        key = (o["destination"], o["departure_date"][:7])
        if key not in best_by_dest_month or o["price"] < best_by_dest_month[key]["price"]:
            best_by_dest_month[key] = o

    for offer in best_by_dest_month.values():
        if should_notify(offer):
            notify(offer, target_price=target)
            record_alert(offer)
            alerts_sent += 1
            print(f"[{_ts()}] [알림] {offer['destination']} {offer['departure_date']}~{offer['return_date']} → {offer['price']:,}원")

    # --- 실행 결과 기록 ---
    total_saved = len(gf_offers) + len(nv_offers)
    if errors:
        status = "partial" if total_saved > 0 else "error"
        error_log = "\n---\n".join(errors)
    else:
        status = "success"
        error_log = None

    finish_collection_run(
        run_id,
        status=status,
        google_count=len(gf_offers),
        naver_count=len(nv_offers),
        total_saved=total_saved,
        alerts_sent=alerts_sent,
        error_log=error_log,
    )

    # --- 캐시 버전 bump + 워밍 ---
    # 데이터가 1건이라도 저장된 경우에만 버전을 올려서 기존 캐시를 원자 무효화.
    # 완전 실패(total_saved == 0)면 이전 버전 유지 → graceful degradation.
    if total_saved > 0:
        try:
            from flight_front.api.deals_cache import bump_deals_version, warm_deals_cache
            new_version = bump_deals_version()
            print(f"[{_ts()}] [cache] deals version → v{new_version}", flush=True)
            stats = warm_deals_cache()
            print(f"[{_ts()}] [warmup] {stats}", flush=True)
        except Exception as e:
            print(f"[{_ts()}] [warmup] skipped due to error: {e}", flush=True)
    else:
        print(f"[{_ts()}] [warmup] skipped: no data saved this run", flush=True)

    # --- raw_legs 90일 보존 정리 ---
    try:
        deleted = cleanup_old_data()
        print(f"[{_ts()}] [cleanup] raw_legs {deleted}건 삭제 (90일 초과)", flush=True)
    except Exception as e:
        print(f"[{_ts()}] [cleanup] skipped due to error: {e}", flush=True)

    print(f"[{_ts()}] === 탐색 완료 ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(f"[{datetime.now(KST):%Y-%m-%d %H:%M:%S}] [FATAL] 예상치 못한 오류:")
        traceback.print_exc()
        try:
            send_alert(f"[항공권 모니터] 크롤링 크래시 발생\n{traceback.format_exc()}")
        except Exception:
            pass
        sys.exit(1)
