"""Уведомления о бэкапе — email и Telegram (RealMikrotikBackup)."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from services.backup_settings import BackupConfigData, get_config

logger = logging.getLogger(__name__)


def _send_telegram(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    if not token or not chat_id:
        return False, "Telegram не настроен"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15.0,
        )
        data = resp.json()
        if resp.is_success and data.get("ok"):
            return True, "Telegram: отправлено"
        desc = data.get("description") or resp.text
        return False, f"Telegram: {desc}"
    except Exception as exc:
        logger.warning("backup | telegram failed: %s", exc)
        return False, f"Telegram: {exc}"


def _send_email(cfg: BackupConfigData, to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    if not cfg.smtp_server or not cfg.smtp_from or not to_addr:
        return False, "SMTP не настроен"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_from
    msg["To"] = to_addr
    try:
        if cfg.smtp_ssl:
            server = smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port, timeout=20)
        else:
            server = smtplib.SMTP(cfg.smtp_server, cfg.smtp_port, timeout=20)
            server.starttls()
        if cfg.smtp_user:
            server.login(cfg.smtp_user, cfg.smtp_password)
        server.sendmail(cfg.smtp_from, [to_addr], msg.as_string())
        server.quit()
        return True, f"Email → {to_addr}: отправлено"
    except Exception as exc:
        logger.warning("backup | smtp failed: %s", exc)
        return False, f"Email: {exc}"


def _dispatch(cfg: BackupConfigData, *, kind: str, subject: str, body: str) -> None:
    if kind == "error":
        if cfg.error_notify_telegram:
            ok, msg = _send_telegram(cfg.telegram_token, cfg.telegram_chat_notify, body)
            logger.log(logging.INFO if ok else logging.WARNING, "backup | notify | %s", msg)
        if cfg.error_notify_email:
            ok, msg = _send_email(cfg, cfg.smtp_to_notify, subject, body)
            logger.log(logging.INFO if ok else logging.WARNING, "backup | notify | %s", msg)
    elif kind == "report":
        if cfg.report_send_telegram:
            ok, msg = _send_telegram(cfg.telegram_token, cfg.telegram_chat_report, body)
            logger.log(logging.INFO if ok else logging.WARNING, "backup | notify | %s", msg)
        if cfg.report_send_email:
            ok, msg = _send_email(cfg, cfg.smtp_to_report, subject, body)
            logger.log(logging.INFO if ok else logging.WARNING, "backup | notify | %s", msg)
    elif kind == "degrade":
        if cfg.degrade_notify_telegram:
            ok, msg = _send_telegram(cfg.telegram_token, cfg.telegram_chat_notify, body)
            logger.log(logging.INFO if ok else logging.WARNING, "backup | degrade | %s", msg)
        if cfg.degrade_notify_email:
            ok, msg = _send_email(cfg, cfg.smtp_to_notify, subject, body)
            logger.log(logging.INFO if ok else logging.WARNING, "backup | degrade | %s", msg)


def notify_backup_error(device: str, ip: str, status: str, detail: str = "") -> None:
    cfg = get_config()
    if not cfg.error_notify_telegram and not cfg.error_notify_email:
        return
    lines = [f"Backup Tools — ошибка бэкапа", f"Устройство: {device}", f"IP: {ip}", f"Статус: {status}"]
    if detail:
        lines.append(f"Детали: {detail}")
    body = "\n".join(lines)
    _dispatch(cfg, kind="error", subject="RMBackup: ошибка бэкапа", body=body)


def notify_degradation(kind_label: str, device_lines: list[str], *, stale_days: int = 30) -> None:
    cfg = get_config()
    if not cfg.degrade_notify_telegram and not cfg.degrade_notify_email:
        return
    if not device_lines:
        return
    body = "\n".join(
        [
            "Backup Tools — деградация",
            f"Категория: {kind_label}",
            f"Устройств: {len(device_lines)}",
            "",
            *device_lines,
        ]
    )
    _dispatch(cfg, kind="degrade", subject=f"Backup Tools: {kind_label}", body=body)


def notify_backup_report(device: str, ip: str, *, config_changed: bool, binary_ok: bool = True) -> None:
    cfg = get_config()
    if not cfg.report_send_telegram and not cfg.report_send_email:
        return
    change = "конфиг изменён" if config_changed else "без изменений в Git"
    binary = "OK" if binary_ok else "ошибка"
    body = "\n".join(
        [
            "Backup Tools — отчёт о бэкапе",
            f"Устройство: {device}",
            f"IP: {ip}",
            f"Git: {change}",
            f"Binary/export: {binary}",
        ]
    )
    _dispatch(cfg, kind="report", subject="RMBackup: бэкап выполнен", body=body)


def send_test_notification(kind: str = "report") -> dict[str, list[str]]:
    cfg = get_config()
    subject = "RMBackup: тестовое уведомление"
    body = f"Backup Tools — тест ({kind}). Настройки уведомлений работают."
    results: list[str] = []

    if kind == "error":
        if cfg.error_notify_telegram:
            ok, msg = _send_telegram(cfg.telegram_token, cfg.telegram_chat_notify, body)
            results.append(msg if ok else f"Ошибка: {msg}")
        elif cfg.telegram_token and cfg.telegram_chat_notify:
            ok, msg = _send_telegram(cfg.telegram_token, cfg.telegram_chat_notify, body)
            results.append(msg if ok else f"Ошибка: {msg}")
        if cfg.error_notify_email:
            ok, msg = _send_email(cfg, cfg.smtp_to_notify, subject, body)
            results.append(msg if ok else f"Ошибка: {msg}")
        elif cfg.smtp_server and cfg.smtp_to_notify:
            ok, msg = _send_email(cfg, cfg.smtp_to_notify, subject, body)
            results.append(msg if ok else f"Ошибка: {msg}")
    else:
        if cfg.report_send_telegram or (cfg.telegram_token and cfg.telegram_chat_report):
            chat = cfg.telegram_chat_report or cfg.telegram_chat_notify
            ok, msg = _send_telegram(cfg.telegram_token, chat, body)
            results.append(msg if ok else f"Ошибка: {msg}")
        if cfg.report_send_email or (cfg.smtp_server and cfg.smtp_to_report):
            to_addr = cfg.smtp_to_report or cfg.smtp_to_notify
            ok, msg = _send_email(cfg, to_addr, subject, body)
            results.append(msg if ok else f"Ошибка: {msg}")

    if not results:
        return {"ok": False, "messages": ["Включите каналы уведомлений и укажите адреса"]}
    return {"ok": all(not m.startswith("Ошибка:") for m in results), "messages": results}
