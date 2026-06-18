"""ServiceNow, Jira, audit SIEM webhook — singleton в PostgreSQL."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from core.models import IntegrationConfig
from services.database import is_database_available, require_database, reset_availability_cache

logger = logging.getLogger(__name__)

PASSWORD_MASK = "********"


@dataclass(frozen=True)
class IntegrationConfigData:
    snow_enabled: bool
    snow_instance_url: str
    snow_username: str
    snow_password: str
    snow_assignment_group: str
    jira_enabled: bool
    jira_url: str
    jira_username: str
    jira_api_token: str
    jira_project_key: str
    jira_issue_type: str
    ticket_on_backup_failed: bool
    ticket_on_device_offline: bool
    ticket_cooldown_hours: int
    audit_webhook_enabled: bool
    audit_webhook_url: str
    audit_webhook_secret: str
    audit_webhook_action_prefix: str


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes")


def _defaults_from_env() -> dict[str, Any]:
    return {
        "snow_enabled": _env_bool("SNOW_ENABLED"),
        "snow_instance_url": os.environ.get("SNOW_INSTANCE_URL", "").strip(),
        "snow_username": os.environ.get("SNOW_USERNAME", "").strip(),
        "snow_password": os.environ.get("SNOW_PASSWORD", ""),
        "snow_assignment_group": os.environ.get("SNOW_ASSIGNMENT_GROUP", "").strip(),
        "jira_enabled": _env_bool("JIRA_ENABLED"),
        "jira_url": os.environ.get("JIRA_URL", "").strip(),
        "jira_username": os.environ.get("JIRA_USERNAME", "").strip(),
        "jira_api_token": os.environ.get("JIRA_API_TOKEN", ""),
        "jira_project_key": os.environ.get("JIRA_PROJECT_KEY", "").strip(),
        "jira_issue_type": os.environ.get("JIRA_ISSUE_TYPE", "Task").strip() or "Task",
        "ticket_on_backup_failed": _env_bool("TICKET_ON_BACKUP_FAILED", default=True),
        "ticket_on_device_offline": _env_bool("TICKET_ON_DEVICE_OFFLINE", default=True),
        "ticket_cooldown_hours": max(
            1, int(os.environ.get("TICKET_COOLDOWN_HOURS", "24"))
        ),
        "audit_webhook_enabled": _env_bool("AUDIT_WEBHOOK_ENABLED"),
        "audit_webhook_url": os.environ.get("AUDIT_WEBHOOK_URL", "").strip(),
        "audit_webhook_secret": os.environ.get("AUDIT_WEBHOOK_SECRET", ""),
        "audit_webhook_action_prefix": os.environ.get(
            "AUDIT_WEBHOOK_ACTION_PREFIX", ""
        ).strip(),
    }


def _row_to_data(row: IntegrationConfig) -> IntegrationConfigData:
    return IntegrationConfigData(
        snow_enabled=row.snow_enabled,
        snow_instance_url=row.snow_instance_url or "",
        snow_username=row.snow_username or "",
        snow_password=row.snow_password or "",
        snow_assignment_group=row.snow_assignment_group or "",
        jira_enabled=row.jira_enabled,
        jira_url=row.jira_url or "",
        jira_username=row.jira_username or "",
        jira_api_token=row.jira_api_token or "",
        jira_project_key=row.jira_project_key or "",
        jira_issue_type=row.jira_issue_type or "Task",
        ticket_on_backup_failed=row.ticket_on_backup_failed,
        ticket_on_device_offline=row.ticket_on_device_offline,
        ticket_cooldown_hours=row.ticket_cooldown_hours or 24,
        audit_webhook_enabled=row.audit_webhook_enabled,
        audit_webhook_url=row.audit_webhook_url or "",
        audit_webhook_secret=row.audit_webhook_secret or "",
        audit_webhook_action_prefix=row.audit_webhook_action_prefix or "",
    )


def ensure_initialized() -> None:
    if not is_database_available():
        return
    try:
        defaults = _defaults_from_env()
        _, created = IntegrationConfig.objects.get_or_create(pk=1, defaults=defaults)
        if created:
            logger.info("integration | конфигурация инициализирована из .env")
    except Exception as exc:
        logger.warning("integration | init failed: %s", exc)
        reset_availability_cache()


def get_config() -> IntegrationConfigData:
    if not is_database_available():
        return IntegrationConfigData(**_defaults_from_env())
    try:
        row = IntegrationConfig.objects.filter(pk=1).first()
        if not row:
            ensure_initialized()
            row = IntegrationConfig.objects.get(pk=1)
        return _row_to_data(row)
    except Exception as exc:
        logger.warning("integration | read failed: %s", exc)
        reset_availability_cache()
        return IntegrationConfigData(**_defaults_from_env())


def get_config_public() -> dict[str, Any]:
    cfg = get_config()
    return {
        "snow_enabled": cfg.snow_enabled,
        "snow_instance_url": cfg.snow_instance_url,
        "snow_username": cfg.snow_username,
        "snow_password_set": bool(cfg.snow_password),
        "snow_assignment_group": cfg.snow_assignment_group,
        "jira_enabled": cfg.jira_enabled,
        "jira_url": cfg.jira_url,
        "jira_username": cfg.jira_username,
        "jira_api_token_set": bool(cfg.jira_api_token),
        "jira_project_key": cfg.jira_project_key,
        "jira_issue_type": cfg.jira_issue_type,
        "ticket_on_backup_failed": cfg.ticket_on_backup_failed,
        "ticket_on_device_offline": cfg.ticket_on_device_offline,
        "ticket_cooldown_hours": cfg.ticket_cooldown_hours,
        "audit_webhook_enabled": cfg.audit_webhook_enabled,
        "audit_webhook_url": cfg.audit_webhook_url,
        "audit_webhook_secret_set": bool(cfg.audit_webhook_secret),
        "audit_webhook_action_prefix": cfg.audit_webhook_action_prefix,
        "storage": "database" if is_database_available() else "env",
    }


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    require_database("Сохранение интеграций невозможно")
    row = IntegrationConfig.objects.filter(pk=1).first()
    if not row:
        ensure_initialized()
        row = IntegrationConfig.objects.get(pk=1)

    snow_password = payload.get("snow_password")
    if snow_password in (None, "", PASSWORD_MASK):
        snow_password = row.snow_password
    else:
        snow_password = str(snow_password)

    jira_api_token = payload.get("jira_api_token")
    if jira_api_token in (None, "", PASSWORD_MASK):
        jira_api_token = row.jira_api_token
    else:
        jira_api_token = str(jira_api_token)

    audit_secret = payload.get("audit_webhook_secret")
    if audit_secret in (None, "", PASSWORD_MASK):
        audit_secret = row.audit_webhook_secret
    else:
        audit_secret = str(audit_secret)

    row.snow_enabled = bool(payload.get("snow_enabled", row.snow_enabled))
    row.snow_instance_url = str(
        payload.get("snow_instance_url", row.snow_instance_url)
    ).strip().rstrip("/")
    row.snow_username = str(payload.get("snow_username", row.snow_username)).strip()
    row.snow_password = snow_password
    row.snow_assignment_group = str(
        payload.get("snow_assignment_group", row.snow_assignment_group)
    ).strip()
    row.jira_enabled = bool(payload.get("jira_enabled", row.jira_enabled))
    row.jira_url = str(payload.get("jira_url", row.jira_url)).strip().rstrip("/")
    row.jira_username = str(payload.get("jira_username", row.jira_username)).strip()
    row.jira_api_token = jira_api_token
    row.jira_project_key = str(
        payload.get("jira_project_key", row.jira_project_key)
    ).strip()
    row.jira_issue_type = (
        str(payload.get("jira_issue_type", row.jira_issue_type)).strip() or "Task"
    )
    row.ticket_on_backup_failed = bool(
        payload.get("ticket_on_backup_failed", row.ticket_on_backup_failed)
    )
    row.ticket_on_device_offline = bool(
        payload.get("ticket_on_device_offline", row.ticket_on_device_offline)
    )
    cooldown = int(payload.get("ticket_cooldown_hours", row.ticket_cooldown_hours))
    if cooldown < 1 or cooldown > 168:
        raise ValueError("ticket_cooldown_hours должен быть от 1 до 168")
    row.ticket_cooldown_hours = cooldown
    row.audit_webhook_enabled = bool(
        payload.get("audit_webhook_enabled", row.audit_webhook_enabled)
    )
    row.audit_webhook_url = str(
        payload.get("audit_webhook_url", row.audit_webhook_url)
    ).strip()
    row.audit_webhook_secret = audit_secret
    row.audit_webhook_action_prefix = str(
        payload.get("audit_webhook_action_prefix", row.audit_webhook_action_prefix)
    ).strip()
    row.save()
    logger.info("integration | настройки сохранены через UI")
    return get_config_public()
