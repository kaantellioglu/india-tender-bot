"""
Yeni ihale tespit edildiginde bildirim gonderir.

Iki kanal desteklenir (ikisi de opsiyonel, env degiskeni yoksa sessizce
atlanir):
- E-posta (SMTP)
- Telegram bot

GitHub Actions'ta bu degerler "repo secrets" olarak tanimlanir, kod
icinde asla sabit yazilmaz.
"""
from __future__ import annotations

import os
import smtplib
import logging
from email.mime.text import MIMEText

import requests

logger = logging.getLogger(__name__)


def send_email(subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    to_addr = os.getenv("NOTIFY_EMAIL_TO")

    if not all([host, user, password, to_addr]):
        logger.info("SMTP ayarlari eksik, e-posta bildirimi atlandi.")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr

    port = int(os.getenv("SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_addr], msg.as_string())
        logger.info("E-posta bildirimi gonderildi -> %s", to_addr)
    except Exception as exc:
        logger.warning("E-posta gonderilemedi: %s", exc)


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not all([token, chat_id]):
        logger.info("Telegram ayarlari eksik, bildirim atlandi.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=15)
        if resp.status_code != 200:
            logger.warning("Telegram bildirimi basarisiz: %s", resp.text)
        else:
            logger.info("Telegram bildirimi gonderildi.")
    except requests.RequestException as exc:
        logger.warning("Telegram istegi basarisiz: %s", exc)


def notify_new_tenders(new_register_rows: int, new_price_rows: int, sample_titles: list[str]) -> None:
    if new_register_rows == 0:
        logger.info("Yeni ihale yok, bildirim gonderilmiyor.")
        return

    subject = f"[ESKA Tender Bot] {new_register_rows} yeni ihale/duyuru bulundu"
    body_lines = [
        f"Toplam yeni kayit: {new_register_rows}",
        f"Fiyat bilgisi cikarilan kayit: {new_price_rows}",
        "",
        "Ornek basliklar:",
    ] + [f"- {t}" for t in sample_titles[:15]]
    body = "\n".join(body_lines)

    send_email(subject, body)
    send_telegram(f"{subject}\n\n" + "\n".join(f"- {t}" for t in sample_titles[:10]))
