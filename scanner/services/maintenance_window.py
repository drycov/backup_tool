"""Окна обслуживания — пауза scheduled backup для maintenance-узлов."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DAYS = list(range(7))  # 0=Mon … 6=Sun (UTC weekday)


def _normalize_days(days: list[Any] | None) -> set[int]:
    if not days:
        return set(_DEFAULT_DAYS)
    out: set[int] = set()
    for d in days:
        try:
            n = int(d)
            if 0 <= n <= 6:
                out.add(n)
        except (TypeError, ValueError):
            continue
    return out or set(_DEFAULT_DAYS)


def _hour_in_window(hour: int, start: int, end: int) -> bool:
    """UTC hour in [start, end) — end may be less than start (overnight)."""
    start = max(0, min(23, start))
    end = max(0, min(23, end))
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def is_maintenance_window_active(
    *,
    now: datetime | None = None,
    start_hour_utc: int = 22,
    end_hour_utc: int = 6,
    days: list[Any] | None = None,
) -> bool:
    now = now or datetime.now(timezone.utc)
    if now.weekday() not in _normalize_days(days):
        return False
    return _hour_in_window(now.hour, start_hour_utc, end_hour_utc)


def is_backup_paused_for_device(
    *,
    device_name: str,
    maintenance: bool = False,
    group_name: str = "",
    now: datetime | None = None,
) -> bool:
    """Scheduled backup skip: group override, device maintenance + global window."""
    from services.group_policies import effective_maintenance_override

    override = effective_maintenance_override(group_name)
    if override is True:
        logger.debug("maintenance | skip (group override) | %s", device_name)
        return True
    if override is False:
        return False
    if not maintenance:
        return False
    from services.backup_settings import get_config

    cfg = get_config()
    if not cfg.maintenance_window_enabled:
        return False
    active = is_maintenance_window_active(
        now=now,
        start_hour_utc=cfg.maintenance_start_hour_utc,
        end_hour_utc=cfg.maintenance_end_hour_utc,
        days=cfg.maintenance_days,
    )
    if active:
        logger.debug("maintenance | skip scheduled backup | %s", device_name)
    return active


def device_maintenance_flag(device_name: str) -> bool:
    from core.models import Device

    row = Device.objects.filter(name=device_name).only("maintenance").first()
    return bool(row and row.maintenance)


def maintenance_config_public(cfg) -> dict[str, Any]:
    days = cfg.maintenance_days if cfg.maintenance_days else _DEFAULT_DAYS
    return {
        "maintenance_window_enabled": cfg.maintenance_window_enabled,
        "maintenance_start_hour_utc": cfg.maintenance_start_hour_utc,
        "maintenance_end_hour_utc": cfg.maintenance_end_hour_utc,
        "maintenance_days": list(days),
    }
