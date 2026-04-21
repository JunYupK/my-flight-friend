# flight_monitor/notifier.py

import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_whatsapp(message: str):
    phone   = os.environ.get("CALLMEBOT_PHONE")
    api_key = os.environ.get("CALLMEBOT_API_KEY")
    if not phone or not api_key:
        print("[알림] WhatsApp 환경변수 없음, 건너뜀")
        return
    requests.get(
        "https://api.callmebot.com/whatsapp.php",
        params={"phone": phone, "text": message, "apikey": api_key},
        timeout=10,
    )


def send_email(subject: str, body: str):
    gmail   = os.environ.get("GMAIL_ADDRESS")
    pw      = os.environ.get("GMAIL_APP_PASSWORD")
    to      = os.environ.get("ALERT_EMAIL")
    if not gmail or not pw or not to:
        print("[알림] 이메일 환경변수 없음, 건너뜀")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail
    msg["To"]      = to
    msg.attach(MIMEText(body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail, pw)
        server.sendmail(gmail, to, msg.as_string())


def send_telegram(message: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[알림] Telegram 환경변수 없음, 건너뜀")
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=10,
    )


def notify(offer: dict, target_price: int):
    dest     = offer["destination_name"]
    dep_date = offer["departure_date"]
    ret_date = offer["return_date"]
    stay     = offer["stay_nights"]
    price    = int(offer["price"])

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
    send_whatsapp(msg)
    send_email(subject=f"[항공권 알림] 인천→{dest} 왕복 {price:,}원", body=f"<pre>{msg}</pre>")
    send_telegram(msg)
