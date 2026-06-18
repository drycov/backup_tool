"""Системные настройки — singleton в PostgreSQL (ранее только .env)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from core.models import SystemConfig
from services.database import is_database_available, require_database, reset_availability_cache

logger = logging.getLogger(__name__)

PASSWORD_MASK = "********"


@dataclass(frozen=True)
class SystemConfigData:
    oxidized_engine: str
    oxidized_external_url: str
    zabbix_auth_key: str
    zabbix_monitoring_enabled: bool
    audit_retention_days: int
    metrics_enabled: bool
    backup_data_dir: str
    access_token_expire_minutes: int
    behind_https_proxy: bool
    task_worker_enabled: bool
    task_worker_poll_sec: int


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes")


def _defaults_from_env() -> dict[str, Any]:
    return {
        "oxidized_engine": os.environ.get("OXIDIZED_ENGINE", "python").lower(),
        "oxidized_external_url": os.environ.get("OXIDIZED_URL", "http://oxidized:8888").rstrip("/"),
        "zabbix_auth_key": os.environ.get("ZABBIX_AUTH_KEY", ""),
        "zabbix_monitoring_enabled": _env_bool("ZABBIX_MONITORING_ENABLED", default=True),
        "audit_retention_days": max(0, int(os.environ.get("AUDIT_RETENTION_DAYS", "365"))),
        "metrics_enabled": _env_bool("METRICS_ENABLED", default=True),
        "backup_data_dir": os.environ.get("BACKUP_DATA_DIR", "/data/backups"),
        "access_token_expire_minutes": max(
            5, int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
        ),
        "behind_https_proxy": _env_bool("BEHIND_HTTPS_PROXY"),
        "task_worker_enabled": _env_bool("TASK_WORKER_ENABLED", default=True),
        "task_worker_poll_sec": max(10, int(os.environ.get("TASK_WORKER_POLL_SEC", "30"))),
    }


def _row_to_data(row: SystemConfig) -> SystemConfigData:
    return SystemConfigData(
        oxidized_engine=(row.oxidized_engine or "python").lower(),
        oxidized_external_url=(row.oxidized_external_url or "http://oxidized:8888").rstrip("/"),
        zabbix_auth_key=row.zabbix_auth_key or "",
        zabbix_monitoring_enabled=bool(row.zabbix_monitoring_enabled),
        audit_retention_days=row.audit_retention_days or 0,
        metrics_enabled=bool(row.metrics_enabled),
        backup_data_dir=row.backup_data_dir or "/data/backups",
        access_token_expire_minutes=row.access_token_expire_minutes or 480,
        behind_https_proxy=bool(row.behind_https_proxy),
        task_worker_enabled=bool(row.task_worker_enabled),
        task_worker_poll_sec=row.task_worker_poll_sec or 30,
    )


def ensure_initialized() -> None:
    if not is_database_available():
        return
    try:
        defaults = _defaults_from_env()
        _, created = SystemConfig.objects.get_or_create(pk=1, defaults=defaults)
        if created:
            logger.info("system | конфигурация инициализирована из .env")
    except Exception as exc:
        logger.warning("system | init failed: %s", exc)
        reset_availability_cache()


def get_config() -> SystemConfigData:
    if not is_database_available():
        return SystemConfigData(**_defaults_from_env())
    try:
        row = SystemConfig.objects.filter(pk=1).first()
        if not row:
            ensure_initialized()
            row = SystemConfig.objects.get(pk=1)
        return _row_to_data(row)
    except Exception as exc:
        logger.warning("system | read failed: %s", exc)
        reset_availability_cache()
        return SystemConfigData(**_defaults_from_env())


def get_config_public() -> dict[str, Any]:
    cfg = get_config()
    row = SystemConfig.objects.filter(pk=1).first() if is_database_available() else None
    return {
        "oxidized_engine": cfg.oxidized_engine,
        "oxidized_external_url": cfg.oxidized_external_url,
        "zabbix_auth_key_set": bool(cfg.zabbix_auth_key),
        "zabbix_monitoring_enabled": cfg.zabbix_monitoring_enabled,
        "audit_retention_days": cfg.audit_retention_days,
        "metrics_enabled": cfg.metrics_enabled,
        "backup_data_dir": cfg.backup_data_dir,
        "access_token_expire_minutes": cfg.access_token_expire_minutes,
        "behind_https_proxy": cfg.behind_https_proxy,
        "task_worker_enabled": cfg.task_worker_enabled,
        "task_worker_poll_sec": cfg.task_worker_poll_sec,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "restart_required_fields": ["oxidized_engine", "behind_https_proxy", "task_worker_enabled"],
    }


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    require_database("Системные настройки требуют базу данных")
    ensure_initialized()
    row = SystemConfig.objects.get(pk=1)

    engine = str(payload.get("oxidized_engine", row.oxidized_engine) or "python").lower()
    if engine not in ("python", "external"):
        raise ValueError("oxidized_engine: python или external")

    row.oxidized_engine = engine
    row.oxidized_external_url = str(
        payload.get("oxidized_external_url", row.oxidized_external_url) or ""
    ).rstrip("/")
    if "zabbix_auth_key" in payload:
        key = str(payload.get("zabbix_auth_key") or "")
        if key and key != PASSWORD_MASK:
            row.zabbix_auth_key = key
    row.zabbix_monitoring_enabled = bool(
        payload.get("zabbix_monitoring_enabled", row.zabbix_monitoring_enabled)
    )
    row.audit_retention_days = max(
        0, int(payload.get("audit_retention_days", row.audit_retention_days))
    )
    row.metrics_enabled = bool(payload.get("metrics_enabled", row.metrics_enabled))
    row.backup_data_dir = str(payload.get("backup_data_dir", row.backup_data_dir) or "/data/backups")
    row.access_token_expire_minutes = max(
        5, int(payload.get("access_token_expire_minutes", row.access_token_expire_minutes))
    )
    row.behind_https_proxy = bool(payload.get("behind_https_proxy", row.behind_https_proxy))
    row.task_worker_enabled = bool(payload.get("task_worker_enabled", row.task_worker_enabled))
    row.task_worker_poll_sec = max(
        10, int(payload.get("task_worker_poll_sec", row.task_worker_poll_sec))
    )
    row.save()
    apply_runtime_overrides()
    logger.info("system | settings saved engine=%s", row.oxidized_engine)
    return get_config_public()


def apply_runtime_overrides() -> None:
    """Применить настройки из БД к django.conf.settings (runtime)."""
    cfg = get_config()
    try:
        from django.conf import settings as dj_settings

        dj_settings.OXIDIZED_ENGINE = cfg.oxidized_engine
        dj_settings.OXIDIZED_URL = cfg.oxidized_external_url
        dj_settings.ZABBIX_AUTH_KEY = cfg.zabbix_auth_key
        dj_settings.ZABBIX_MONITORING_ENABLED = cfg.zabbix_monitoring_enabled
        dj_settings.AUDIT_RETENTION_DAYS = cfg.audit_retention_days
        dj_settings.METRICS_ENABLED = cfg.metrics_enabled
        dj_settings.BACKUP_DATA_DIR = cfg.backup_data_dir
        dj_settings.ACCESS_TOKEN_EXPIRE_MINUTES = cfg.access_token_expire_minutes
        dj_settings.BEHIND_HTTPS_PROXY = cfg.behind_https_proxy
        if cfg.behind_https_proxy:
            dj_settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
            dj_settings.USE_X_FORWARDED_HOST = True
        else:
            dj_settings.SECURE_CROSS_ORIGIN_OPENER_POLICY = None
    except Exception as exc:
        logger.warning("system | apply overrides failed: %s", exc)
