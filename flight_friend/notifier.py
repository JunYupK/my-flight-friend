# flight_friend/notifier.py

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

