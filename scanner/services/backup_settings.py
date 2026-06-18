"""Настройки MikroTik backup и уведомлений (singleton в PostgreSQL)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.models import BackupConfig
from services.database import is_database_available, require_database, reset_availability_cache
from services.maintenance_window import maintenance_config_public

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
    degrade_notify_telegram: bool
    degrade_notify_email: bool
    stale_days_threshold: int
    alert_cooldown_hours: int
    mk_backup_git_push: bool
    degrade_check_interval_sec: int
    compliance_report_telegram: bool
    compliance_report_email: bool
    compliance_report_hour_utc: int
    degrade_webhook_enabled: bool
    degrade_webhook_url: str
    slack_webhook_url: str
    teams_webhook_url: str
    error_notify_slack: bool
    error_notify_teams: bool
    report_send_slack: bool
    report_send_teams: bool
    degrade_notify_slack: bool
    degrade_notify_teams: bool
    compliance_report_slack: bool
    compliance_report_teams: bool
    maintenance_window_enabled: bool
    maintenance_start_hour_utc: int
    maintenance_end_hour_utc: int
    maintenance_days: list[int]


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
        "degrade_notify_telegram": _env_bool("DEGRADE_NOTIFICATION_TELEGRAM")
        or _env_bool("ERROR_NOTIFICATION_TELEGRAM"),
        "degrade_notify_email": _env_bool("DEGRADE_NOTIFICATION_EMAIL")
        or _env_bool("ERROR_NOTIFICATION_EMAIL"),
        "stale_days_threshold": max(1, int(os.environ.get("STALE_DAYS_THRESHOLD", "30"))),
        "alert_cooldown_hours": max(1, int(os.environ.get("ALERT_COOLDOWN_HOURS", "24"))),
        "mk_backup_git_push": _env_bool("MK_BACKUP_GIT_PUSH", default=True)
        if os.environ.get("MK_BACKUP_GIT_PUSH")
        else bool(os.environ.get("GIT_REMOTE_URL", "")),
        "degrade_check_interval_sec": max(
            300, int(os.environ.get("DEGRADE_CHECK_INTERVAL_SEC", "3600"))
        ),
        "compliance_report_telegram": _env_bool("COMPLIANCE_REPORT_TELEGRAM"),
        "compliance_report_email": _env_bool("COMPLIANCE_REPORT_EMAIL"),
        "compliance_report_hour_utc": max(
            0, min(23, int(os.environ.get("COMPLIANCE_REPORT_HOUR_UTC", "7")))
        ),
        "degrade_webhook_enabled": _env_bool("DEGRADE_WEBHOOK_ENABLED"),
        "degrade_webhook_url": os.environ.get("DEGRADE_WEBHOOK_URL", ""),
        "slack_webhook_url": os.environ.get("SLACK_WEBHOOK_URL", ""),
        "teams_webhook_url": os.environ.get("TEAMS_WEBHOOK_URL", ""),
        "error_notify_slack": _env_bool("ERROR_NOTIFICATION_SLACK"),
        "error_notify_teams": _env_bool("ERROR_NOTIFICATION_TEAMS"),
        "report_send_slack": _env_bool("REPORT_SEND_SLACK"),
        "report_send_teams": _env_bool("REPORT_SEND_TEAMS"),
        "degrade_notify_slack": _env_bool("DEGRADE_NOTIFICATION_SLACK"),
        "degrade_notify_teams": _env_bool("DEGRADE_NOTIFICATION_TEAMS"),
        "compliance_report_slack": _env_bool("COMPLIANCE_REPORT_SLACK"),
        "compliance_report_teams": _env_bool("COMPLIANCE_REPORT_TEAMS"),
        "maintenance_window_enabled": _env_bool("MAINTENANCE_WINDOW_ENABLED", default=True),
        "maintenance_start_hour_utc": max(
            0, min(23, int(os.environ.get("MAINTENANCE_START_HOUR_UTC", "22")))
        ),
        "maintenance_end_hour_utc": max(
            0, min(23, int(os.environ.get("MAINTENANCE_END_HOUR_UTC", "6")))
        ),
        "maintenance_days": list(range(7)),
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
        degrade_notify_telegram=row.degrade_notify_telegram,
        degrade_notify_email=row.degrade_notify_email,
        stale_days_threshold=row.stale_days_threshold or 30,
        alert_cooldown_hours=row.alert_cooldown_hours or 24,
        mk_backup_git_push=row.mk_backup_git_push,
        degrade_check_interval_sec=row.degrade_check_interval_sec or 3600,
        compliance_report_telegram=row.compliance_report_telegram,
        compliance_report_email=row.compliance_report_email,
        compliance_report_hour_utc=row.compliance_report_hour_utc or 7,
        degrade_webhook_enabled=row.degrade_webhook_enabled,
        degrade_webhook_url=row.degrade_webhook_url or "",
        slack_webhook_url=getattr(row, "slack_webhook_url", None) or "",
        teams_webhook_url=getattr(row, "teams_webhook_url", None) or "",
        error_notify_slack=getattr(row, "error_notify_slack", False),
        error_notify_teams=getattr(row, "error_notify_teams", False),
        report_send_slack=getattr(row, "report_send_slack", False),
        report_send_teams=getattr(row, "report_send_teams", False),
        degrade_notify_slack=getattr(row, "degrade_notify_slack", False),
        degrade_notify_teams=getattr(row, "degrade_notify_teams", False),
        compliance_report_slack=getattr(row, "compliance_report_slack", False),
        compliance_report_teams=getattr(row, "compliance_report_teams", False),
        maintenance_window_enabled=getattr(row, "maintenance_window_enabled", True),
        maintenance_start_hour_utc=getattr(row, "maintenance_start_hour_utc", None) or 22,
        maintenance_end_hour_utc=getattr(row, "maintenance_end_hour_utc", None) or 6,
        maintenance_days=list(getattr(row, "maintenance_days", None) or list(range(7))),
    )


def ensure_initialized() -> None:
    if not is_database_available():
        return
    try:
        defaults = _defaults_from_env()
        _, created = BackupConfig.objects.get_or_create(pk=1, defaults=defaults)
        if created:
            logger.info("backup | конфигурация инициализирована из .env")
    except Exception as exc:
        logger.warning("backup | init failed: %s", exc)
        reset_availability_cache()


def get_config() -> BackupConfigData:
    if not is_database_available():
        return BackupConfigData(**_defaults_from_env())
    try:
        row = BackupConfig.objects.filter(pk=1).first()
        if not row:
            ensure_initialized()
            row = BackupConfig.objects.get(pk=1)
        return _row_to_data(row)
    except Exception as exc:
        logger.warning("backup | read failed: %s", exc)
        reset_availability_cache()
        return BackupConfigData(**_defaults_from_env())


def _compliance_report_last_sent_iso() -> str | None:
    if not is_database_available():
        return None
    try:
        row = BackupConfig.objects.filter(pk=1).only("compliance_report_last_sent_at").first()
        if row and row.compliance_report_last_sent_at:
            return row.compliance_report_last_sent_at.isoformat()
    except Exception:
        pass
    return None


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
        "degrade_notify_telegram": cfg.degrade_notify_telegram,
        "degrade_notify_email": cfg.degrade_notify_email,
        "stale_days_threshold": cfg.stale_days_threshold,
        "alert_cooldown_hours": cfg.alert_cooldown_hours,
        "mk_backup_git_push": cfg.mk_backup_git_push,
        "degrade_check_interval_sec": cfg.degrade_check_interval_sec,
        "compliance_report_telegram": cfg.compliance_report_telegram,
        "compliance_report_email": cfg.compliance_report_email,
        "compliance_report_hour_utc": cfg.compliance_report_hour_utc,
        "degrade_webhook_enabled": cfg.degrade_webhook_enabled,
        "degrade_webhook_url": cfg.degrade_webhook_url,
        "slack_webhook_url": cfg.slack_webhook_url,
        "teams_webhook_url": cfg.teams_webhook_url,
        "error_notify_slack": cfg.error_notify_slack,
        "error_notify_teams": cfg.error_notify_teams,
        "report_send_slack": cfg.report_send_slack,
        "report_send_teams": cfg.report_send_teams,
        "degrade_notify_slack": cfg.degrade_notify_slack,
        "degrade_notify_teams": cfg.degrade_notify_teams,
        "compliance_report_slack": cfg.compliance_report_slack,
        "compliance_report_teams": cfg.compliance_report_teams,
        "compliance_report_last_sent_at": _compliance_report_last_sent_iso(),
        **maintenance_config_public(cfg),
        "storage": "database" if is_database_available() else "env",
        "notifications_configured": bool(
            cfg.telegram_token
            or (cfg.smtp_server and cfg.smtp_from)
            or cfg.slack_webhook_url
            or cfg.teams_webhook_url
        ),
    }


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    require_database("Сохранение настроек backup невозможно")
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
    row.degrade_notify_telegram = bool(
        payload.get("degrade_notify_telegram", row.degrade_notify_telegram)
    )
    row.degrade_notify_email = bool(
        payload.get("degrade_notify_email", row.degrade_notify_email)
    )
    stale_days = int(payload.get("stale_days_threshold", row.stale_days_threshold))
    if stale_days < 1 or stale_days > 365:
        raise ValueError("stale_days_threshold должен быть от 1 до 365")
    row.stale_days_threshold = stale_days
    cooldown = int(payload.get("alert_cooldown_hours", row.alert_cooldown_hours))
    if cooldown < 1 or cooldown > 168:
        raise ValueError("alert_cooldown_hours должен быть от 1 до 168")
    row.alert_cooldown_hours = cooldown
    row.mk_backup_git_push = bool(payload.get("mk_backup_git_push", row.mk_backup_git_push))
    interval = int(payload.get("degrade_check_interval_sec", row.degrade_check_interval_sec))
    if interval < 300 or interval > 86400:
        raise ValueError("degrade_check_interval_sec должен быть от 300 до 86400")
    row.degrade_check_interval_sec = interval
    row.compliance_report_telegram = bool(
        payload.get("compliance_report_telegram", row.compliance_report_telegram)
    )
    row.compliance_report_email = bool(
        payload.get("compliance_report_email", row.compliance_report_email)
    )
    hour = int(payload.get("compliance_report_hour_utc", row.compliance_report_hour_utc))
    if hour < 0 or hour > 23:
        raise ValueError("compliance_report_hour_utc должен быть 0–23")
    row.compliance_report_hour_utc = hour
    row.degrade_webhook_enabled = bool(
        payload.get("degrade_webhook_enabled", row.degrade_webhook_enabled)
    )
    row.degrade_webhook_url = str(
        payload.get("degrade_webhook_url", row.degrade_webhook_url)
    ).strip()
    row.slack_webhook_url = str(
        payload.get("slack_webhook_url", getattr(row, "slack_webhook_url", ""))
    ).strip()
    row.teams_webhook_url = str(
        payload.get("teams_webhook_url", getattr(row, "teams_webhook_url", ""))
    ).strip()
    row.error_notify_slack = bool(
        payload.get("error_notify_slack", getattr(row, "error_notify_slack", False))
    )
    row.error_notify_teams = bool(
        payload.get("error_notify_teams", getattr(row, "error_notify_teams", False))
    )
    row.report_send_slack = bool(
        payload.get("report_send_slack", getattr(row, "report_send_slack", False))
    )
    row.report_send_teams = bool(
        payload.get("report_send_teams", getattr(row, "report_send_teams", False))
    )
    row.degrade_notify_slack = bool(
        payload.get("degrade_notify_slack", getattr(row, "degrade_notify_slack", False))
    )
    row.degrade_notify_teams = bool(
        payload.get("degrade_notify_teams", getattr(row, "degrade_notify_teams", False))
    )
    row.compliance_report_slack = bool(
        payload.get(
            "compliance_report_slack", getattr(row, "compliance_report_slack", False)
        )
    )
    row.compliance_report_teams = bool(
        payload.get(
            "compliance_report_teams", getattr(row, "compliance_report_teams", False)
        )
    )
    row.maintenance_window_enabled = bool(
        payload.get("maintenance_window_enabled", row.maintenance_window_enabled)
    )
    m_start = int(payload.get("maintenance_start_hour_utc", row.maintenance_start_hour_utc))
    m_end = int(payload.get("maintenance_end_hour_utc", row.maintenance_end_hour_utc))
    if m_start < 0 or m_start > 23 or m_end < 0 or m_end > 23:
        raise ValueError("maintenance hours должны быть 0–23")
    row.maintenance_start_hour_utc = m_start
    row.maintenance_end_hour_utc = m_end
    days = payload.get("maintenance_days")
    if days is not None:
        row.maintenance_days = [int(d) for d in days if 0 <= int(d) <= 6]
    row.save()

    try:
        from services.oxidized_engine import reload_engine

        reload_engine()
    except Exception:
        logger.exception("backup | reload engine after settings save failed")

    logger.info("backup | настройки сохранены через UI")
    return get_config_public()
