"""Prometheus-метрики приложения."""

from __future__ import annotations

import logging

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

logger = logging.getLogger(__name__)

backup_success_total = Counter(
    "backup_success_total",
    "Успешные бэкапы конфигурации Oxidized",
    ["group", "model"],
)

devices_offline = Gauge(
    "devices_offline",
    "Устройства offline по последнему scan",
)

oxidized_queue_depth = Gauge(
    "oxidized_queue_depth",
    "Узлы в очереди на бэкап (due + running)",
)

compliance_pct = Gauge(
    "compliance_pct",
    "Процент compliance (enabled devices)",
)

task_queue_depth = Gauge(
    "task_queue_depth",
    "Задачи в очереди (pending)",
    ["task_type"],
)

task_runs_total = Counter(
    "task_runs_total",
    "Выполненные фоновые задачи",
    ["task_type", "status"],
)


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def record_backup_success(*, group: str, model: str) -> None:
    backup_success_total.labels(group=group or "default", model=model or "unknown").inc()


def refresh_compliance_gauges() -> None:
    try:
        from services.compliance import compute_compliance_summary

        summary = compute_compliance_summary()
        counts = summary.get("counts") or {}
        compliance_pct.set(float(summary.get("compliance_pct") or 0))
        devices_offline.set(float(counts.get("unreachable") or 0))
    except Exception:
        logger.debug("metrics | compliance refresh failed", exc_info=True)


def refresh_oxidized_queue_depth() -> None:
    try:
        from django.conf import settings

        if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
            return
        from services.oxidized_engine import get_manager

        manager = get_manager()
        if manager:
            oxidized_queue_depth.set(manager.worker.queue_depth())
    except Exception:
        logger.debug("metrics | oxidized queue depth failed", exc_info=True)


def refresh_task_queue_depth() -> None:
    try:
        from core.models import BackgroundTask

        for task_type in (
            BackgroundTask.TASK_DEGRADE_CHECK,
            BackgroundTask.TASK_COMPLIANCE_REPORT,
            BackgroundTask.TASK_SCHEDULED_SCAN,
            BackgroundTask.TASK_PROVISION_BULK,
        ):
            count = BackgroundTask.objects.filter(
                task_type=task_type,
                status=BackgroundTask.STATUS_PENDING,
            ).count()
            task_queue_depth.labels(task_type=task_type).set(count)
    except Exception:
        logger.debug("metrics | task queue depth failed", exc_info=True)


def refresh_all_gauges() -> None:
    refresh_compliance_gauges()
    refresh_oxidized_queue_depth()
    refresh_task_queue_depth()
