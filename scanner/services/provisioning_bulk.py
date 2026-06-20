"""Массовый провижионинг: шаблон на группу/site через task queue."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.models import ProvisionBulkRun, ProvisionTemplate, User
from django.utils import timezone as dj_tz

from services.inventory import load_inventory
from services.object_scope import device_in_scope, filter_devices
from services.provisioning import ProvisioningError, get_template, run_provision
from services.schemas import Device
from services.sites import site_matches_filter
from services.vendor_catalog import normalize_model

logger = logging.getLogger(__name__)


def _complex_device_names(template: ProvisionTemplate) -> set[str]:
    meta = template.meta if isinstance(template.meta, dict) else {}
    names: set[str] = set()
    for item in meta.get("complex_devices") or []:
        if isinstance(item, dict) and item.get("name"):
            names.add(str(item["name"]))
    return names


def list_bulk_targets(
    *,
    template: ProvisionTemplate,
    group: str = "",
    site: str = "",
    model: str = "",
    device_names: list[str] | None = None,
    exclude_complex: bool = False,
    user=None,
) -> list[Device]:
    inventory = load_inventory()
    if device_names:
        wanted = {n.strip() for n in device_names if str(n).strip()}
        devices = [d for d in inventory.devices if d.enabled and d.name in wanted]
    else:
        devices = [d for d in inventory.devices if d.enabled]
        if group:
            devices = [d for d in devices if d.group == group]
        if site:
            devices = [d for d in devices if site_matches_filter(d.site or "", site)]
        if model:
            want = normalize_model(model)
            devices = [d for d in devices if normalize_model(d.model) == want]

    if user is not None:
        devices = filter_devices(user, devices)

    tpl_model = normalize_model(template.model) if template.model != "*" else "*"
    if tpl_model != "*":
        devices = [d for d in devices if normalize_model(d.model) == tpl_model]

    if exclude_complex:
        skip = _complex_device_names(template)
        if skip:
            devices = [d for d in devices if d.name not in skip]

    return sorted(devices, key=lambda d: d.name.lower())


def preview_bulk_provision(
    *,
    template_id: int | None = None,
    template_slug: str = "",
    group: str = "",
    site: str = "",
    model: str = "",
    device_names: list[str] | None = None,
    exclude_complex: bool = False,
    user=None,
) -> dict[str, Any]:
    template = get_template(template_id, slug=template_slug)
    if not template.is_active:
        raise ProvisioningError("Шаблон отключён")

    devices = list_bulk_targets(
        template=template,
        group=group,
        site=site,
        model=model,
        device_names=device_names,
        exclude_complex=exclude_complex,
        user=user,
    )
    skipped_complex = []
    if exclude_complex:
        skip = _complex_device_names(template)
        if skip:
            inventory = load_inventory()
            skipped_complex = sorted(
                n
                for n in skip
                if any(d.name == n and device_in_scope(user, d) for d in inventory.devices if d.enabled)
            )

    return {
        "template_slug": template.slug,
        "scope_group": group,
        "scope_site": site,
        "scope_model": model,
        "exclude_complex": exclude_complex,
        "device_count": len(devices),
        "devices": [
            {"name": d.name, "ip": d.ip, "model": d.model, "group": d.group, "site": d.site or ""}
            for d in devices
        ],
        "skipped_complex": skipped_complex,
    }


def _append_bulk_log(bulk: ProvisionBulkRun, level: str, text: str, *, save: bool = True) -> None:
    entries = list(bulk.log) if isinstance(bulk.log, list) else []
    entries.append({"level": level, "text": text})
    bulk.log = entries[-500:]
    if save:
        bulk.save(update_fields=["log"])


def _bulk_row_public(row: ProvisionBulkRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "template_id": row.template_id,
        "template_slug": row.template_slug,
        "scope_group": row.scope_group,
        "scope_site": row.scope_site,
        "scope_model": row.scope_model,
        "dry_run": row.dry_run,
        "exclude_complex": row.exclude_complex,
        "status": row.status,
        "triggered_by": row.triggered_by,
        "correlation_id": row.correlation_id,
        "background_task_id": row.background_task_id,
        "devices_total": row.devices_total,
        "devices_completed": row.devices_completed,
        "devices_failed": row.devices_failed,
        "results": row.results if isinstance(row.results, list) else [],
        "log": row.log if isinstance(row.log, list) else [],
        "error": row.error,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "created_at": row.created_at,
    }


def list_bulk_runs(*, limit: int = 30) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    return [_bulk_row_public(r) for r in ProvisionBulkRun.objects.order_by("-created_at")[:limit]]


def get_bulk_run(bulk_run_id: int) -> dict[str, Any]:
    row = ProvisionBulkRun.objects.filter(id=bulk_run_id).first()
    if not row:
        raise ProvisioningError("Bulk run не найден")
    return _bulk_row_public(row)


def create_bulk_run(
    *,
    template_id: int | None = None,
    template_slug: str = "",
    group: str = "",
    site: str = "",
    model: str = "",
    device_names: list[str] | None = None,
    dry_run: bool = True,
    exclude_complex: bool = False,
    triggered_by: str = "",
    correlation_id: str = "",
    user=None,
) -> ProvisionBulkRun:
    preview = preview_bulk_provision(
        template_id=template_id,
        template_slug=template_slug,
        group=group,
        site=site,
        model=model,
        device_names=device_names,
        exclude_complex=exclude_complex,
        user=user,
    )
    if preview["device_count"] == 0:
        raise ProvisioningError("Нет устройств для применения шаблона")

    template = get_template(template_id, slug=template_slug)
    return ProvisionBulkRun.objects.create(
        template=template,
        template_slug=template.slug,
        scope_group=group,
        scope_site=site,
        scope_model=model,
        dry_run=bool(dry_run),
        exclude_complex=bool(exclude_complex),
        status=ProvisionBulkRun.STATUS_QUEUED,
        triggered_by=(triggered_by or "")[:64],
        correlation_id=(correlation_id or "")[:64],
        devices_total=preview["device_count"],
    )


def enqueue_bulk_provision(
    bulk_run: ProvisionBulkRun,
    *,
    user_id: int | None = None,
    device_names: list[str] | None = None,
) -> int | None:
    from core.models import BackgroundTask
    from services.task_queue import enqueue

    task = enqueue(
        BackgroundTask.TASK_PROVISION_BULK,
        payload={
            "bulk_run_id": bulk_run.id,
            "user_id": user_id,
            "device_names": device_names or [],
        },
        correlation_id=bulk_run.correlation_id or None,
        dedupe=False,
    )
    if not task:
        return None
    bulk_run.background_task_id = task.id
    bulk_run.save(update_fields=["background_task_id"])
    return task.id


def run_bulk_provision_task(payload: dict[str, Any]) -> dict[str, Any]:
    bulk_run_id = int(payload.get("bulk_run_id") or 0)
    bulk = ProvisionBulkRun.objects.filter(id=bulk_run_id).first()
    if not bulk:
        raise ValueError(f"ProvisionBulkRun {bulk_run_id} not found")

    user = None
    user_id = payload.get("user_id")
    if user_id:
        user = User.objects.filter(pk=int(user_id)).first()

    device_names = payload.get("device_names") or None
    if device_names and not isinstance(device_names, list):
        device_names = None
    if device_names:
        device_names = [str(n).strip() for n in device_names if str(n).strip()]

    template = bulk.template
    if not template:
        bulk.status = ProvisionBulkRun.STATUS_FAILED
        bulk.error = "Шаблон удалён"
        bulk.finished_at = dj_tz.now()
        bulk.save(update_fields=["status", "error", "finished_at"])
        raise ValueError(bulk.error)

    now = dj_tz.now()
    bulk.status = ProvisionBulkRun.STATUS_RUNNING
    bulk.started_at = now
    bulk.log = []
    _append_bulk_log(
        bulk,
        "info",
        f"Bulk #{bulk.id} запущен: шаблон {template.slug}, устройств {bulk.devices_total}"
        + (" (dry-run)" if bulk.dry_run else ""),
        save=False,
    )
    bulk.save(update_fields=["status", "started_at", "log"])

    devices = list_bulk_targets(
        template=template,
        group=bulk.scope_group,
        site=bulk.scope_site,
        model=bulk.scope_model,
        device_names=device_names,
        exclude_complex=bulk.exclude_complex,
        user=user,
    )
    bulk.devices_total = len(devices)
    bulk.save(update_fields=["devices_total"])

    results: list[dict[str, Any]] = []
    completed = 0
    failed = 0

    for idx, device in enumerate(devices, start=1):
        _append_bulk_log(bulk, "info", f"[{idx}/{len(devices)}] {device.name}…")
        try:
            run_row = run_provision(
                template_id=template.id,
                device_name=device.name,
                dry_run=bulk.dry_run,
                triggered_by=bulk.triggered_by,
                correlation_id=bulk.correlation_id,
                user=user,
                bulk_run_id=bulk.id,
            )
            completed += 1
            results.append(
                {
                    "device_name": device.name,
                    "status": run_row["status"],
                    "run_id": run_row["id"],
                    "error": "",
                }
            )
            _append_bulk_log(
                bulk,
                "success",
                f"✓ {device.name}: {run_row['status']}",
                save=False,
            )
        except ProvisioningError as exc:
            failed += 1
            msg = str(exc)[:500]
            results.append(
                {
                    "device_name": device.name,
                    "status": "failed",
                    "run_id": None,
                    "error": msg,
                }
            )
            _append_bulk_log(bulk, "error", f"✗ {device.name}: {msg}", save=False)
            logger.warning(
                "provision | bulk | failed | bulk=%s device=%s | %s",
                bulk.id,
                device.name,
                exc,
            )

        bulk.devices_completed = completed
        bulk.devices_failed = failed
        bulk.results = results[-200:]
        bulk.save(update_fields=["devices_completed", "devices_failed", "results", "log"])

    _append_bulk_log(
        bulk,
        "info" if failed == 0 else "warn",
        f"Итог: успешно {completed}, ошибок {failed}, всего {len(devices)}",
        save=False,
    )
    bulk.status = ProvisionBulkRun.STATUS_COMPLETED
    bulk.finished_at = dj_tz.now()
    bulk.save(update_fields=["status", "finished_at", "log"])

    logger.info(
        "provision | bulk | done | id=%s completed=%s failed=%s total=%s",
        bulk.id,
        completed,
        failed,
        len(devices),
    )
    return {
        "bulk_run_id": bulk.id,
        "devices_total": len(devices),
        "devices_completed": completed,
        "devices_failed": failed,
    }
