"""Scan/discovery и seed credentials — singleton в PostgreSQL, .env как fallback."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from core.models import ScanConfig
from services.database import is_database_available, require_database, reset_availability_cache

logger = logging.getLogger(__name__)

PASSWORD_MASK = "********"


@dataclass(frozen=True)
class ScanConfigData:
    scan_concurrency: int
    discover_max_hosts: int
    discover_ping_workers: int
    ovn_user: str
    ovn_pass: str
    us_user: str
    us_pass: str


def _defaults_from_env() -> dict[str, Any]:
    return {
        "scan_concurrency": max(1, int(os.environ.get("SCAN_CONCURRENCY", "50"))),
        "discover_max_hosts": max(1, int(os.environ.get("DISCOVER_MAX_HOSTS", "4096"))),
        "discover_ping_workers": max(1, int(os.environ.get("DISCOVER_PING_WORKERS", "100"))),
        "ovn_user": os.environ.get("OVN_USER", "satcoadm").strip() or "satcoadm",
        "ovn_pass": os.environ.get("OVN_PASS", ""),
        "us_user": os.environ.get("US_USER", "satcoadm").strip() or "satcoadm",
        "us_pass": os.environ.get("US_PASS", ""),
    }


def _row_to_data(row: ScanConfig) -> ScanConfigData:
    return ScanConfigData(
        scan_concurrency=row.scan_concurrency or 50,
        discover_max_hosts=row.discover_max_hosts or 4096,
        discover_ping_workers=row.discover_ping_workers or 100,
        ovn_user=row.ovn_user or "satcoadm",
        ovn_pass=row.ovn_pass or "",
        us_user=row.us_user or "satcoadm",
        us_pass=row.us_pass or "",
    )


def ensure_initialized() -> None:
    if not is_database_available():
        return
    try:
        defaults = _defaults_from_env()
        _, created = ScanConfig.objects.get_or_create(pk=1, defaults=defaults)
        if created:
            logger.info("scan | конфигурация инициализирована из .env")
    except Exception as exc:
        logger.warning("scan | init failed: %s", exc)
        reset_availability_cache()


def get_config() -> ScanConfigData:
    if not is_database_available():
        return ScanConfigData(**_defaults_from_env())
    try:
        row = ScanConfig.objects.filter(pk=1).first()
        if not row:
            ensure_initialized()
            row = ScanConfig.objects.get(pk=1)
        return _row_to_data(row)
    except Exception as exc:
        logger.warning("scan | read failed: %s", exc)
        reset_availability_cache()
        return ScanConfigData(**_defaults_from_env())


def get_config_public() -> dict[str, Any]:
    cfg = get_config()
    return {
        "scan_concurrency": cfg.scan_concurrency,
        "discover_max_hosts": cfg.discover_max_hosts,
        "discover_ping_workers": cfg.discover_ping_workers,
        "ovn_user": cfg.ovn_user,
        "ovn_pass_set": bool(cfg.ovn_pass),
        "us_user": cfg.us_user,
        "us_pass_set": bool(cfg.us_pass),
        "storage": "database" if is_database_available() else "env",
    }


def get_credentials() -> tuple[str, str, str, str]:
    cfg = get_config()
    return cfg.ovn_user, cfg.ovn_pass, cfg.us_user, cfg.us_pass


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    require_database("Сохранение настроек scan невозможно")
    row = ScanConfig.objects.filter(pk=1).first()
    if not row:
        ensure_initialized()
        row = ScanConfig.objects.get(pk=1)

    concurrency = int(payload.get("scan_concurrency", row.scan_concurrency))
    if concurrency < 1 or concurrency > 500:
        raise ValueError("scan_concurrency должен быть от 1 до 500")

    max_hosts = int(payload.get("discover_max_hosts", row.discover_max_hosts))
    if max_hosts < 1 or max_hosts > 65536:
        raise ValueError("discover_max_hosts должен быть от 1 до 65536")

    ping_workers = int(payload.get("discover_ping_workers", row.discover_ping_workers))
    if ping_workers < 1 or ping_workers > 1000:
        raise ValueError("discover_ping_workers должен быть от 1 до 1000")

    ovn_pass = payload.get("ovn_pass")
    if ovn_pass in (None, "", PASSWORD_MASK):
        ovn_pass = row.ovn_pass
    else:
        ovn_pass = str(ovn_pass)

    us_pass = payload.get("us_pass")
    if us_pass in (None, "", PASSWORD_MASK):
        us_pass = row.us_pass
    else:
        us_pass = str(us_pass)

    row.scan_concurrency = concurrency
    row.discover_max_hosts = max_hosts
    row.discover_ping_workers = ping_workers
    row.ovn_user = str(payload.get("ovn_user", row.ovn_user)).strip() or "satcoadm"
    row.ovn_pass = ovn_pass
    row.us_user = str(payload.get("us_user", row.us_user)).strip() or "satcoadm"
    row.us_pass = us_pass
    row.save()

    logger.info("scan | настройки сохранены через UI")
    return get_config_public()
