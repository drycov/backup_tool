"""Фоновая проверка деградации бэкапов и доступности устройств."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from core.models import AlertState
from services.backup_notifications import notify_degradation
from services.backup_settings import get_config
from services.compliance import collect_degradation_issues

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SEC = 3600


def _check_interval_sec() -> int:
    try:
        from services.backup_settings import get_config

        return max(300, get_config().degrade_check_interval_sec)
    except Exception:
        return max(300, int(os.environ.get("DEGRADE_CHECK_INTERVAL_SEC", "3600")))

_thread: threading.Thread | None = None
_stop = threading.Event()

_KIND_LABELS = {
    "backup_failed": "Ошибки бэкапа",
    "backup_overdue": "Просроченные / отсутствующие бэкапы",
    "config_stale": "Нет изменений конфига",
    "device_offline": "Устройства offline (scan)",
}


def _should_notify(alert_key: str, device_count: int, cooldown_hours: int) -> bool:
    now = datetime.now(timezone.utc)
    row = AlertState.objects.filter(alert_key=alert_key).first()
    if not row:
        return device_count > 0
    if device_count == 0:
        return False
    cooldown = timedelta(hours=max(1, cooldown_hours))
    if now - row.last_notified_at < cooldown and row.device_count == device_count:
        return False
    return True


def _mark_notified(alert_key: str, device_count: int) -> None:
    now = datetime.now(timezone.utc)
    AlertState.objects.update_or_create(
        alert_key=alert_key,
        defaults={"last_notified_at": now, "device_count": device_count},
    )


def run_degradation_check() -> dict[str, int]:
    cfg = get_config()
    if not cfg.degrade_notify_telegram and not cfg.degrade_notify_email:
        return {"skipped": 1}

    buckets = collect_degradation_issues()
    sent = 0
    for kind, devices in buckets.items():
        if not devices:
            continue
        alert_key = f"degrade:{kind}"
        if not _should_notify(alert_key, len(devices), cfg.alert_cooldown_hours):
            continue
        label = _KIND_LABELS.get(kind, kind)
        lines = [f"{d['name']} ({d['ip']})" for d in devices[:50]]
        if len(devices) > 50:
            lines.append(f"… и ещё {len(devices) - 50}")
        notify_degradation(label, lines, stale_days=cfg.stale_days_threshold)
        _mark_notified(alert_key, len(devices))
        sent += 1
        logger.info("degrade | notified | %s | devices=%d", kind, len(devices))
    return {"sent": sent}


def _loop() -> None:
    time.sleep(60)
    while not _stop.is_set():
        try:
            run_degradation_check()
        except Exception:
            logger.exception("degrade | check failed")
        _stop.wait(_check_interval_sec())


def start_degradation_monitor() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="degradation-monitor", daemon=True)
    _thread.start()
    logger.info("degrade | monitor started | interval=%ss", _check_interval_sec())
