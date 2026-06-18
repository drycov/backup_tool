"""Уведомления о бэкапе — email и Telegram (RealMikrotikBackup)."""

from __future__ import annotations

import logging
import smtplib
from dataclasses import replace
from email.mime.text import MIMEText
from typing import Any

import httpx

from services.backup_settings import BackupConfigData, get_config
from services.notification_templates import NotificationBodies, test_notification

logger = logging.getLogger(__name__)


def _normalize_chat_id(chat_id: str) -> str:
    return str(chat_id or "").strip()


def _send_telegram(
    token: str,
    chat_id: str,
    text: str,
    *,
    parse_mode: str | None = None,
) -> tuple[bool, str]:
    token = (token or "").strip()
    chat_id = _normalize_chat_id(chat_id)
    if not token:
        return False, "Telegram: не задан bot token"
    if not chat_id:
        return False, "Telegram: не задан chat ID"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        resp = httpx.post(url, json=payload, timeout=15.0)
        data = resp.json()
        if resp.is_success and data.get("ok"):
            return True, f"Telegram → {chat_id}: отправлено"
        desc = data.get("description") or resp.text
        return False, f"Telegram: {desc}"
    except Exception as exc:
        logger.warning("backup | telegram failed: %s", exc)
        return False, f"Telegram: {exc}"


def _send_email(cfg: BackupConfigData, to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    to_addr = (to_addr or "").strip()
    if not cfg.smtp_server or not cfg.smtp_from or not to_addr:
        return False, "SMTP: задайте сервер, From и адрес получателя"
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


def _dispatch(
    cfg: BackupConfigData,
    *,
    kind: str,
    subject: str,
    bodies: NotificationBodies,
) -> list[str]:
    """Send notification; returns log lines for each attempted channel."""
    messages: list[str] = []
    if kind == "error":
        if cfg.error_notify_telegram:
            ok, msg = _send_telegram(
                cfg.telegram_token,
                cfg.telegram_chat_notify,
                bodies.telegram,
                parse_mode=bodies.parse_mode,
            )
            messages.append(msg if ok else f"Ошибка: {msg}")
        if cfg.error_notify_email:
            ok, msg = _send_email(cfg, cfg.smtp_to_notify, subject, bodies.email)
            messages.append(msg if ok else f"Ошибка: {msg}")
    elif kind == "report":
        if cfg.report_send_telegram:
            chat = cfg.telegram_chat_report or cfg.telegram_chat_notify
            ok, msg = _send_telegram(
                cfg.telegram_token,
                chat,
                bodies.telegram,
                parse_mode=bodies.parse_mode,
            )
            messages.append(msg if ok else f"Ошибка: {msg}")
        if cfg.report_send_email:
            to_addr = cfg.smtp_to_report or cfg.smtp_to_notify
            ok, msg = _send_email(cfg, to_addr, subject, bodies.email)
            messages.append(msg if ok else f"Ошибка: {msg}")
    elif kind == "degrade":
        if cfg.degrade_notify_telegram:
            ok, msg = _send_telegram(
                cfg.telegram_token,
                cfg.telegram_chat_notify,
                bodies.telegram,
                parse_mode=bodies.parse_mode,
            )
            messages.append(msg if ok else f"Ошибка: {msg}")
        if cfg.degrade_notify_email:
            ok, msg = _send_email(cfg, cfg.smtp_to_notify, subject, bodies.email)
            messages.append(msg if ok else f"Ошибка: {msg}")
    elif kind == "compliance":
        if cfg.compliance_report_telegram:
            chat = cfg.telegram_chat_report or cfg.telegram_chat_notify
            ok, msg = _send_telegram(
                cfg.telegram_token,
                chat,
                bodies.telegram,
                parse_mode=bodies.parse_mode,
            )
            messages.append(msg if ok else f"Ошибка: {msg}")
        if cfg.compliance_report_email:
            to_addr = cfg.smtp_to_report or cfg.smtp_to_notify
            ok, msg = _send_email(cfg, to_addr, subject, bodies.email)
            messages.append(msg if ok else f"Ошибка: {msg}")
    return messages


def notify_webhook(url: str, payload: dict[str, Any]) -> tuple[bool, str]:
    url = (url or "").strip()
    if not url:
        return False, "Webhook URL не задан"
    try:
        resp = httpx.post(url, json=payload, timeout=15.0)
        if resp.is_success:
            return True, f"Webhook → {url}: {resp.status_code}"
        return False, f"Webhook: HTTP {resp.status_code}"
    except Exception as exc:
        logger.warning("backup | webhook failed: %s", exc)
        return False, f"Webhook: {exc}"


def notify_degradation_webhook(kind: str, devices: list[dict[str, Any]]) -> None:
    cfg = get_config()
    if not cfg.degrade_webhook_enabled or not cfg.degrade_webhook_url:
        return
    payload = {
        "event": "degradation",
        "kind": kind,
        "device_count": len(devices),
        "devices": devices[:50],
    }
    ok, msg = notify_webhook(cfg.degrade_webhook_url, payload)
    level = logging.INFO if ok else logging.WARNING
    logger.log(level, "backup | webhook | %s", msg)


def notify_compliance_report(subject: str, bodies: NotificationBodies) -> list[str]:
    cfg = get_config()
    return _dispatch(cfg, kind="compliance", subject=subject, bodies=bodies)


def _apply_test_overrides(cfg: BackupConfigData, overrides: dict[str, Any] | None) -> BackupConfigData:
    if not overrides:
        return cfg
    data = {
        "error_notify_telegram": overrides.get("error_notify_telegram", cfg.error_notify_telegram),
        "error_notify_email": overrides.get("error_notify_email", cfg.error_notify_email),
        "report_send_telegram": overrides.get("report_send_telegram", cfg.report_send_telegram),
        "report_send_email": overrides.get("report_send_email", cfg.report_send_email),
        "degrade_notify_telegram": overrides.get("degrade_notify_telegram", cfg.degrade_notify_telegram),
        "degrade_notify_email": overrides.get("degrade_notify_email", cfg.degrade_notify_email),
        "telegram_token": overrides.get("telegram_token") or cfg.telegram_token,
        "telegram_chat_notify": overrides.get("telegram_chat_notify", cfg.telegram_chat_notify),
        "telegram_chat_report": overrides.get("telegram_chat_report", cfg.telegram_chat_report),
        "smtp_server": overrides.get("smtp_server", cfg.smtp_server),
        "smtp_port": overrides.get("smtp_port", cfg.smtp_port),
        "smtp_user": overrides.get("smtp_user", cfg.smtp_user),
        "smtp_password": overrides.get("smtp_password") or cfg.smtp_password,
        "smtp_ssl": overrides.get("smtp_ssl", cfg.smtp_ssl),
        "smtp_from": overrides.get("smtp_from", cfg.smtp_from),
        "smtp_to_notify": overrides.get("smtp_to_notify", cfg.smtp_to_notify),
        "smtp_to_report": overrides.get("smtp_to_report", cfg.smtp_to_report),
    }
    return replace(cfg, **data)


def notify_backup_error(device: str, ip: str, status: str, detail: str = "") -> None:
    from services.notification_templates import backup_error

    cfg = get_config()
    if not cfg.error_notify_telegram and not cfg.error_notify_email:
        return
    bodies = backup_error(device, ip, status, detail)
    for msg in _dispatch(cfg, kind="error", subject="Backup Tools: ошибка бэкапа", bodies=bodies):
        level = logging.WARNING if msg.startswith("Ошибка:") else logging.INFO
        logger.log(level, "backup | notify | %s", msg)


def notify_degradation(
    kind_label: str,
    devices: list[dict[str, Any]],
    *,
    stale_days: int = 30,
) -> None:
    from services.notification_templates import degradation_alert

    cfg = get_config()
    if not cfg.degrade_notify_telegram and not cfg.degrade_notify_email:
        return
    if not devices:
        return
    bodies = degradation_alert(kind_label, devices, stale_days=stale_days)
    for msg in _dispatch(cfg, kind="degrade", subject=f"Backup Tools: {kind_label}", bodies=bodies):
        level = logging.WARNING if msg.startswith("Ошибка:") else logging.INFO
        logger.log(level, "backup | degrade | %s", msg)


def notify_backup_report(device: str, ip: str, *, config_changed: bool, binary_ok: bool = True) -> None:
    from services.notification_templates import backup_report

    cfg = get_config()
    if not cfg.report_send_telegram and not cfg.report_send_email:
        return
    bodies = backup_report(device, ip, config_changed=config_changed, binary_ok=binary_ok)
    for msg in _dispatch(cfg, kind="report", subject="Backup Tools: бэкап выполнен", bodies=bodies):
        level = logging.WARNING if msg.startswith("Ошибка:") else logging.INFO
        logger.log(level, "backup | notify | %s", msg)


def send_test_notification(
    kind: str = "report",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Test notification. Uses DB config + optional form overrides (unsaved UI values)."""
    cfg = _apply_test_overrides(get_config(), overrides)
    kind = (kind or "report").strip().lower()
    subject = f"Backup Tools: тест ({kind})"
    bodies = test_notification(kind)

    channel_map = {
        "error": ("error_notify_telegram", "error_notify_email"),
        "report": ("report_send_telegram", "report_send_email"),
        "degrade": ("degrade_notify_telegram", "degrade_notify_email"),
        "compliance": ("compliance_report_telegram", "compliance_report_email"),
    }
    if kind not in channel_map:
        return {"ok": False, "messages": [f"Неизвестный тип: {kind}"]}

    tg_flag, email_flag = channel_map[kind]
    if not getattr(cfg, tg_flag) and not getattr(cfg, email_flag):
        return {
            "ok": False,
            "messages": [
                f"Включите Telegram и/или Email для типа «{kind}» (галочки в форме)"
            ],
        }

    messages = _dispatch(cfg, kind=kind, subject=subject, bodies=bodies)
    if not messages:
        return {"ok": False, "messages": ["Нет активных каналов для отправки"]}
    return {
        "ok": all(not m.startswith("Ошибка:") for m in messages),
        "messages": messages,
    }
