"""Персистентная очередь фоновых задач (БД, без Redis)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from django.db import transaction
from django.utils import timezone as dj_tz

from core.models import BackgroundTask, ScanConfig
from services.correlation import correlation_context, new_correlation_id
from services.database import is_database_available

logger = logging.getLogger(__name__)


def enqueue(
    task_type: str,
    *,
    payload: dict[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    correlation_id: str | None = None,
    max_attempts: int = 3,
    dedupe: bool = True,
) -> BackgroundTask | None:
    if not is_database_available():
        return None
    when = scheduled_at or dj_tz.now()
    if dedupe and _has_active_task(task_type):
        return None
    task = BackgroundTask.objects.create(
        task_type=task_type,
        status=BackgroundTask.STATUS_PENDING,
        payload=payload or {},
        correlation_id=correlation_id or new_correlation_id(),
        scheduled_at=when,
        max_attempts=max(1, min(max_attempts, 10)),
    )
    logger.info(
        "task_queue | enqueued | type=%s id=%s corr=%s",
        task_type,
        task.id,
        task.correlation_id,
    )
    return task


def _has_active_task(task_type: str) -> bool:
    return BackgroundTask.objects.filter(
        task_type=task_type,
        status__in=(BackgroundTask.STATUS_PENDING, BackgroundTask.STATUS_RUNNING),
    ).exists()


def _last_finished_at(task_type: str) -> datetime | None:
    row = (
        BackgroundTask.objects.filter(
            task_type=task_type,
            status=BackgroundTask.STATUS_COMPLETED,
        )
        .order_by("-finished_at")
        .first()
    )
    return row.finished_at if row else None


def schedule_periodic_tasks() -> int:
    """Поставить в очередь периодические задачи, если пришло время."""
    if not is_database_available():
        return 0
    now = dj_tz.now()
    enqueued = 0

    from services.backup_settings import get_config as get_backup_config

    backup_cfg = get_backup_config()
    degrade_interval = timedelta(seconds=max(300, backup_cfg.degrade_check_interval_sec))
    last_degrade = _last_finished_at(BackgroundTask.TASK_DEGRADE_CHECK)
    if last_degrade is None or now - last_degrade >= degrade_interval:
        if enqueue(BackgroundTask.TASK_DEGRADE_CHECK, dedupe=True):
            enqueued += 1

    from services.compliance_report import _should_send_now

    if (backup_cfg.compliance_report_telegram or backup_cfg.compliance_report_email) and _should_send_now(
        backup_cfg.compliance_report_hour_utc
    ):
        if enqueue(BackgroundTask.TASK_COMPLIANCE_REPORT, dedupe=True):
            enqueued += 1

    scan_row = ScanConfig.objects.filter(pk=1).first()
    if scan_row and scan_row.schedule_enabled:
        interval = timedelta(hours=max(1, scan_row.schedule_interval_hours))
        last_run = scan_row.schedule_last_run_at
        if last_run is None or now - last_run >= interval:
            if enqueue(
                BackgroundTask.TASK_SCHEDULED_SCAN,
                payload={"discover": bool(scan_row.schedule_discover)},
                dedupe=True,
            ):
                enqueued += 1

    from django.conf import settings

    retention_days = int(getattr(settings, "AUDIT_RETENTION_DAYS", 0) or 0)
    if retention_days > 0:
        last_purge = _last_finished_at(BackgroundTask.TASK_AUDIT_PURGE)
        if last_purge is None or now - last_purge >= timedelta(days=1):
            if enqueue(BackgroundTask.TASK_AUDIT_PURGE, dedupe=True):
                enqueued += 1

    return enqueued


def process_next_task() -> bool:
    """Взять одну задачу из очереди и выполнить. Возвращает True, если задача обработана."""
    if not is_database_available():
        return False

    with transaction.atomic():
        task = (
            BackgroundTask.objects.select_for_update(skip_locked=True)
            .filter(
                status=BackgroundTask.STATUS_PENDING,
                scheduled_at__lte=dj_tz.now(),
            )
            .order_by("scheduled_at", "id")
            .first()
        )
        if not task:
            return False
        task.status = BackgroundTask.STATUS_RUNNING
        task.started_at = dj_tz.now()
        task.attempts += 1
        task.save(update_fields=["status", "started_at", "attempts"])

    with correlation_context(task.correlation_id):
        try:
            result = _run_task(task)
            task.status = BackgroundTask.STATUS_COMPLETED
            task.finished_at = dj_tz.now()
            task.last_error = ""
            task.payload = {**(task.payload or {}), "result": result}
            task.save(update_fields=["status", "finished_at", "last_error", "payload"])
            from services.metrics import task_runs_total

            task_runs_total.labels(task_type=task.task_type, status="completed").inc()
            logger.info(
                "task_queue | completed | type=%s id=%s corr=%s",
                task.task_type,
                task.id,
                task.correlation_id,
            )
            return True
        except Exception as exc:
            logger.exception(
                "task_queue | failed | type=%s id=%s attempt=%s",
                task.task_type,
                task.id,
                task.attempts,
            )
            task.last_error = str(exc)[:2000]
            if task.attempts < task.max_attempts:
                task.status = BackgroundTask.STATUS_PENDING
                task.scheduled_at = dj_tz.now() + timedelta(
                    minutes=min(60, 2**task.attempts)
                )
                task.save(update_fields=["status", "scheduled_at", "last_error"])
            else:
                task.status = BackgroundTask.STATUS_FAILED
                task.finished_at = dj_tz.now()
                task.save(update_fields=["status", "finished_at", "last_error"])
                from services.metrics import task_runs_total

                task_runs_total.labels(task_type=task.task_type, status="failed").inc()
            return True


def _run_task(task: BackgroundTask) -> dict[str, Any]:
    if task.task_type == BackgroundTask.TASK_DEGRADE_CHECK:
        from services.degradation_monitor import run_degradation_check

        return run_degradation_check()

    if task.task_type == BackgroundTask.TASK_COMPLIANCE_REPORT:
        from services.compliance_report import send_compliance_report

        return send_compliance_report(force=True)

    if task.task_type == BackgroundTask.TASK_SCHEDULED_SCAN:
        from services import scan_job

        discover = bool((task.payload or {}).get("discover"))
        current = scan_job.get_current_job()
        if current and current.status == "running":
            return {"skipped": True, "reason": "scan already running"}
        job = scan_job.start_scan(discover=discover)
        scan_row = ScanConfig.objects.filter(pk=1).first()
        if scan_row:
            scan_row.schedule_last_run_at = dj_tz.now()
            scan_row.save(update_fields=["schedule_last_run_at"])
        return {"job_id": job.id, "discover": discover}

    if task.task_type == BackgroundTask.TASK_AUDIT_PURGE:
        from services.audit import purge_old_audit_events

        return purge_old_audit_events()

    raise ValueError(f"Unknown task type: {task.task_type}")


def purge_stale_running(max_age_minutes: int = 120) -> int:
    """Сбросить зависшие running-задачи после рестарта."""
    if not is_database_available():
        return 0
    cutoff = dj_tz.now() - timedelta(minutes=max_age_minutes)
    qs = BackgroundTask.objects.filter(
        status=BackgroundTask.STATUS_RUNNING,
        started_at__lt=cutoff,
    )
    count = qs.count()
    if count:
        qs.update(
            status=BackgroundTask.STATUS_PENDING,
            scheduled_at=dj_tz.now(),
            last_error="stale running reset after restart",
        )
    return count
