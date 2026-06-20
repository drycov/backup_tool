"""Zabbix HTTP agent API — Backup Tools / RMB_Monitoring."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.compliance import STATE_OK, _STATE_LABELS, compute_compliance_summary, device_compliance_item
from services.inventory import load_inventory


def _dt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def list_devices(*, user=None) -> list[dict[str, str]]:
    """Список устройств для Zabbix LLD: id, name, ip, group, site, critical."""
    devices = [d for d in load_inventory().devices if d.enabled]
    if user is not None:
        from services.object_scope import filter_devices

        devices = filter_devices(user, devices)
    devices.sort(key=lambda d: d.name.lower())
    return [
        {
            "id": d.name,
            "name": d.name,
            "ip": d.ip or "",
            "group": d.group or "",
            "site": d.site or "",
            "critical": "1" if d.critical else "0",
        }
        for d in devices
    ]


def device_last_status(device_id: str, *, user=None) -> dict[str, Any]:
    """Статус бэкапа устройства (поле laststatus + метаданные для Zabbix)."""
    device_id = (device_id or "").strip()
    if not device_id:
        raise ValueError("id обязателен")

    row = device_compliance_item(device_id, user=user)
    if row is None:
        raise LookupError(f"Устройство '{device_id}' не найдено")

    state = str(row.get("state") or "")
    if state == STATE_OK:
        laststatus = "OK"
    else:
        label = row.get("state_label") or _STATE_LABELS.get(state, "") or state or "ERROR"
        laststatus = str(label).strip() or "ERROR"

    last_backup = row.get("last_backup_at")
    return {
        "laststatus": laststatus,
        "state": state,
        "ip": row.get("ip") or "",
        "group": row.get("group") or "",
        "site": row.get("site") or "",
        "critical": "1" if row.get("critical") else "0",
        "reachability": row.get("reachability") or "",
        "last_backup_at": _dt_iso(last_backup if isinstance(last_backup, datetime) else None),
    }


def platform_summary(*, user=None) -> dict[str, Any]:
    """Сводка платформы Backup Tools для master-item Zabbix."""
    summary = compute_compliance_summary(user=user)
    counts = summary.get("counts") or {}

    ready = False
    checks: dict[str, Any] = {}
    try:
        from services.database import is_database_available
        from services.oxidized_client import check_health

        db_ok = is_database_available()
        ox = check_health()
        ox_ok = bool(ox.get("reachable"))
        ready = db_ok and ox_ok
        checks = {
            "database": db_ok,
            "oxidized_worker": ox_ok,
            "oxidized_engine": ox.get("engine"),
            "oxidized_nodes": ox.get("nodes_count", 0),
        }
        if not ox_ok:
            checks["oxidized_error"] = ox.get("error")
    except Exception as exc:
        checks["error"] = str(exc)

    queue_depth = 0
    try:
        from django.conf import settings

        if getattr(settings, "OXIDIZED_ENGINE", "python").lower() == "python":
            from services.oxidized_engine import get_manager

            manager = get_manager()
            if manager:
                queue_depth = int(manager.worker.queue_depth())
    except Exception:
        pass

    task_pending = 0
    try:
        from core.models import BackgroundTask

        task_pending = BackgroundTask.objects.filter(status=BackgroundTask.STATUS_PENDING).count()
    except Exception:
        pass

    generated = summary.get("generated_at")
    if isinstance(generated, datetime):
        generated_at = _dt_iso(generated)
    else:
        generated_at = _dt_iso(datetime.now(timezone.utc))

    return {
        "status": "ok",
        "ready": ready,
        "checks": checks,
        "compliance_pct": summary.get("compliance_pct", 0),
        "devices_total": summary.get("total_enabled", 0),
        "devices_ok": int(counts.get(STATE_OK, 0) or 0),
        "counts": counts,
        "oxidized_queue_depth": queue_depth,
        "task_queue_pending": task_pending,
        "oxidized_error": summary.get("oxidized_error") or "",
        "generated_at": generated_at,
    }


def device_tags(device_id: str, *, user=None) -> dict[str, Any]:
    """Теги Zabbix-хоста по имени устройства из inventory."""
    device_id = (device_id or "").strip()
    if not device_id:
        raise ValueError("id обязателен")

    from services.inventory import load_inventory
    from services.object_scope import device_in_scope

    inventory = load_inventory()
    device = next((d for d in inventory.devices if d.name == device_id), None)
    if not device:
        raise LookupError(f"Устройство '{device_id}' не найдено")
    if user is not None and not device_in_scope(user, device):
        raise LookupError(f"Устройство '{device_id}' вне scope")

    from services.zabbix_client import ZabbixClientError, ZabbixNotConfigured, get_host_tags

    try:
        tags_payload = get_host_tags(device.name)
    except ZabbixNotConfigured as exc:
        raise ValueError(str(exc)) from exc
    except ZabbixClientError as exc:
        raise RuntimeError(str(exc)) from exc

    return {
        "id": device.name,
        "name": device.name,
        **tags_payload,
    }
