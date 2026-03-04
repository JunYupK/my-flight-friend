from flight_monitor.collector_amadeus        import fetch_fsc_offers
from flight_monitor.collector_google_flights import fetch_google_flights_offers
from flight_monitor.storage                  import init_db, save_prices, should_notify, record_alert
from flight_monitor.notifier                 import notify
from flight_monitor.config                   import SEARCH_CONFIG


def main():
    print("=== 일본 항공권 최저가 탐색 시작 ===")
    init_db()

    fsc_offers = fetch_fsc_offers()
    gf_offers  = fetch_google_flights_offers()
    all_offers = fsc_offers + gf_offers
    save_prices(all_offers)
    print(f"[수집] FSC {len(fsc_offers)}건 / GoogleFlights {len(gf_offers)}건")

    target = SEARCH_CONFIG["target_price_krw"]
    for offer in [o for o in all_offers if o["price"] <= target]:
        if should_notify(offer):
            notify(offer, target_price=target)
            record_alert(offer)
            print(f"[알림] {offer['destination']} {offer['departure_date']}~{offer['return_date']} → {offer['price']:,}원")

    print("=== 탐색 완료 ===")


if __name__ == "__main__":
    main()
