"""Настройки MikroTik backup и уведомлений (singleton в PostgreSQL)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.models import BackupConfig

logger = logging.getLogger(__name__)

PASSWORD_MASK = "********"


@dataclass(frozen=True)
class BackupConfigData:
    binary_enabled: bool
    export_enabled: bool
    hide_sensitive: bool
    encrypt_password: str
    purge_enabled: bool
    purge_keep: int
    bin_dir: str
    rsc_dir: str
    backup_timeout: int
    error_notify_telegram: bool
    error_notify_email: bool
    report_send_telegram: bool
    report_send_email: bool
    telegram_token: str
    telegram_chat_notify: str
    telegram_chat_report: str
    smtp_server: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_ssl: bool
    smtp_from: str
    smtp_to_notify: str
    smtp_to_report: str


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes")


def _defaults_from_env() -> dict[str, Any]:
    return {
        "binary_enabled": _env_bool("MK_BACKUP_BINARY", default=True),
        "export_enabled": _env_bool("MK_BACKUP_EXPORT", default=True),
        "hide_sensitive": _env_bool("MK_BACKUP_HIDE_SENSITIVE"),
        "encrypt_password": os.environ.get("MK_BACKUP_ENCRYPT_PASSWORD", ""),
        "purge_enabled": _env_bool("PURGE_OLD_BACKUP", default=True),
        "purge_keep": max(1, int(os.environ.get("PURGE_N_PIECE", "10"))),
        "bin_dir": os.environ.get("MK_BACKUP_BIN_DIR", "/var/lib/oxidized/bin"),
        "rsc_dir": os.environ.get("MK_BACKUP_RSC_DIR", "/var/lib/oxidized/rsc"),
        "backup_timeout": max(30, int(os.environ.get("MK_BACKUP_TIMEOUT", "300"))),
        "error_notify_telegram": _env_bool("ERROR_NOTIFICATION_TELEGRAM"),
        "error_notify_email": _env_bool("ERROR_NOTIFICATION_EMAIL"),
        "report_send_telegram": _env_bool("REPORT_SEND_TELEGRAM"),
        "report_send_email": _env_bool("REPORT_SEND_EMAIL"),
        "telegram_token": os.environ.get("TELEGRAM_ACCESS_TOKEN", ""),
        "telegram_chat_notify": os.environ.get("TELEGRAM_CHATID_NOTIFY", ""),
        "telegram_chat_report": os.environ.get("TELEGRAM_CHATID_REPORT", ""),
        "smtp_server": os.environ.get("SMTP_SERVER", ""),
        "smtp_port": int(os.environ.get("SMTP_PORT", "465")),
        "smtp_user": os.environ.get("SMTP_USER", ""),
        "smtp_password": os.environ.get("SMTP_PASSWORD", ""),
        "smtp_ssl": _env_bool("SMTP_SSL", default=True),
        "smtp_from": os.environ.get("SMTP_FROM_MAIL", ""),
        "smtp_to_notify": os.environ.get("SMTP_TO_MAIL_NOTIFY", ""),
        "smtp_to_report": os.environ.get("SMTP_TO_MAIL_REPORT", ""),
    }


def _row_to_data(row: BackupConfig) -> BackupConfigData:
    return BackupConfigData(
        binary_enabled=row.binary_enabled,
        export_enabled=row.export_enabled,
        hide_sensitive=row.hide_sensitive,
        encrypt_password=row.encrypt_password or "",
        purge_enabled=row.purge_enabled,
        purge_keep=row.purge_keep or 10,
        bin_dir=row.bin_dir or "/var/lib/oxidized/bin",
        rsc_dir=row.rsc_dir or "/var/lib/oxidized/rsc",
        backup_timeout=row.backup_timeout or 300,
        error_notify_telegram=row.error_notify_telegram,
        error_notify_email=row.error_notify_email,
        report_send_telegram=row.report_send_telegram,
        report_send_email=row.report_send_email,
        telegram_token=row.telegram_token or "",
        telegram_chat_notify=row.telegram_chat_notify or "",
        telegram_chat_report=row.telegram_chat_report or "",
        smtp_server=row.smtp_server or "",
        smtp_port=row.smtp_port or 465,
        smtp_user=row.smtp_user or "",
        smtp_password=row.smtp_password or "",
        smtp_ssl=row.smtp_ssl,
        smtp_from=row.smtp_from or "",
        smtp_to_notify=row.smtp_to_notify or "",
        smtp_to_report=row.smtp_to_report or "",
    )


def ensure_initialized() -> None:
    defaults = _defaults_from_env()
    _, created = BackupConfig.objects.get_or_create(pk=1, defaults=defaults)
    if created:
        logger.info("backup | конфигурация инициализирована из .env")


def get_config() -> BackupConfigData:
    row = BackupConfig.objects.filter(pk=1).first()
    if not row:
        ensure_initialized()
        row = BackupConfig.objects.get(pk=1)
    return _row_to_data(row)


def get_mikrotik_config():
    """Shortcut for mikrotik_backup.MikrotikBackupConfig."""
    from services.mikrotik_backup import MikrotikBackupConfig

    cfg = get_config()
    return MikrotikBackupConfig(
        binary_enabled=cfg.binary_enabled,
        export_enabled=cfg.export_enabled,
        hide_sensitive=cfg.hide_sensitive,
        encrypt_password=cfg.encrypt_password,
        purge_enabled=cfg.purge_enabled,
        purge_keep=cfg.purge_keep,
        bin_dir=Path(cfg.bin_dir),
        rsc_dir=Path(cfg.rsc_dir),
        timeout=cfg.backup_timeout,
    )


def get_config_public() -> dict[str, Any]:
    cfg = get_config()
    return {
        "binary_enabled": cfg.binary_enabled,
        "export_enabled": cfg.export_enabled,
        "hide_sensitive": cfg.hide_sensitive,
        "encrypt_password_set": bool(cfg.encrypt_password),
        "purge_enabled": cfg.purge_enabled,
        "purge_keep": cfg.purge_keep,
        "bin_dir": cfg.bin_dir,
        "rsc_dir": cfg.rsc_dir,
        "backup_timeout": cfg.backup_timeout,
        "error_notify_telegram": cfg.error_notify_telegram,
        "error_notify_email": cfg.error_notify_email,
        "report_send_telegram": cfg.report_send_telegram,
        "report_send_email": cfg.report_send_email,
        "telegram_token_set": bool(cfg.telegram_token),
        "telegram_chat_notify": cfg.telegram_chat_notify,
        "telegram_chat_report": cfg.telegram_chat_report,
        "smtp_server": cfg.smtp_server,
        "smtp_port": cfg.smtp_port,
        "smtp_user": cfg.smtp_user,
        "smtp_password_set": bool(cfg.smtp_password),
        "smtp_ssl": cfg.smtp_ssl,
        "smtp_from": cfg.smtp_from,
        "smtp_to_notify": cfg.smtp_to_notify,
        "smtp_to_report": cfg.smtp_to_report,
        "notifications_configured": bool(
            cfg.telegram_token
            or (cfg.smtp_server and cfg.smtp_from)
        ),
    }


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    row = BackupConfig.objects.filter(pk=1).first()
    if not row:
        ensure_initialized()
        row = BackupConfig.objects.get(pk=1)

    purge_keep = int(payload.get("purge_keep", row.purge_keep))
    if purge_keep < 1 or purge_keep > 100:
        raise ValueError("purge_keep должен быть от 1 до 100")

    timeout = int(payload.get("backup_timeout", row.backup_timeout))
    if timeout < 30 or timeout > 3600:
        raise ValueError("backup_timeout должен быть от 30 до 3600 секунд")

    encrypt_password = payload.get("encrypt_password")
    if encrypt_password in (None, "", PASSWORD_MASK):
        encrypt_password = row.encrypt_password
    else:
        encrypt_password = str(encrypt_password)

    smtp_password = payload.get("smtp_password")
    if smtp_password in (None, "", PASSWORD_MASK):
        smtp_password = row.smtp_password
    else:
        smtp_password = str(smtp_password)

    telegram_token = payload.get("telegram_token")
    if telegram_token in (None, "", PASSWORD_MASK):
        telegram_token = row.telegram_token
    else:
        telegram_token = str(telegram_token)

    row.binary_enabled = bool(payload.get("binary_enabled", row.binary_enabled))
    row.export_enabled = bool(payload.get("export_enabled", row.export_enabled))
    row.hide_sensitive = bool(payload.get("hide_sensitive", row.hide_sensitive))
    row.encrypt_password = encrypt_password
    row.purge_enabled = bool(payload.get("purge_enabled", row.purge_enabled))
    row.purge_keep = purge_keep
    row.bin_dir = str(payload.get("bin_dir", row.bin_dir)).strip() or row.bin_dir
    row.rsc_dir = str(payload.get("rsc_dir", row.rsc_dir)).strip() or row.rsc_dir
    row.backup_timeout = timeout
    row.error_notify_telegram = bool(
        payload.get("error_notify_telegram", row.error_notify_telegram)
    )
    row.error_notify_email = bool(payload.get("error_notify_email", row.error_notify_email))
    row.report_send_telegram = bool(
        payload.get("report_send_telegram", row.report_send_telegram)
    )
    row.report_send_email = bool(payload.get("report_send_email", row.report_send_email))
    row.telegram_token = telegram_token
    row.telegram_chat_notify = str(
        payload.get("telegram_chat_notify", row.telegram_chat_notify)
    ).strip()
    row.telegram_chat_report = str(
        payload.get("telegram_chat_report", row.telegram_chat_report)
    ).strip()
    row.smtp_server = str(payload.get("smtp_server", row.smtp_server)).strip()
    row.smtp_port = max(1, min(65535, int(payload.get("smtp_port", row.smtp_port))))
    row.smtp_user = str(payload.get("smtp_user", row.smtp_user)).strip()
    row.smtp_password = smtp_password
    row.smtp_ssl = bool(payload.get("smtp_ssl", row.smtp_ssl))
    row.smtp_from = str(payload.get("smtp_from", row.smtp_from)).strip()
    row.smtp_to_notify = str(payload.get("smtp_to_notify", row.smtp_to_notify)).strip()
    row.smtp_to_report = str(payload.get("smtp_to_report", row.smtp_to_report)).strip()
    row.save()

    try:
        from services.oxidized_engine import reload_engine

        reload_engine()
    except Exception:
        logger.exception("backup | reload engine after settings save failed")

    logger.info("backup | настройки сохранены через UI")
    return get_config_public()
