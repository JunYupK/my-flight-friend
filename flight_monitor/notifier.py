import os
import sys
import requests


def send_telegram(message: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=10,
        )
        return r.ok
    except requests.RequestException:
        return False


def send_discord(message: str) -> bool:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return False
    try:
        r = requests.post(url, json={"content": message}, timeout=10)
        return r.ok
    except requests.RequestException:
        return False


def send_alert(message: str) -> str | None:
    """Telegram(1순위) → Discord(2순위) fallback. 성공한 채널명 반환."""
    if send_telegram(message):
        return "telegram"
    if send_discord(message):
        return "discord"
    print("[알림] Telegram/Discord 모두 실패 또는 미설정", file=sys.stderr)
    return None


def notify(offer: dict, target_price: int) -> str | None:
    dest = offer["destination_name"]
    dep_date = offer["departure_date"]
    ret_date = offer["return_date"]
    stay = offer["stay_nights"]
    price = int(offer["price"])

    if offer["is_mixed_airline"]:
        airline_info = (
            f"가는편 {offer['out_airline']} / 오는편 {offer['in_airline']}"
            f"\n⚠️ 다른 항공사 조합 — 개별 예약 필요"
        )
    else:
        airline_info = f"{offer['out_airline']} (동일 항공사 왕복)"

    msg = (
        f"✈️ 왕복 최저가 발견!\n"
        f"📍 인천 → {dest}\n"
        f"📅 출발: {dep_date}  귀국: {ret_date} ({stay}박)\n"
        f"💰 왕복 총액: {price:,}원\n"
        f"🛫 {airline_info}"
    )
    return send_alert(msg)
