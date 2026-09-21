"""Фоновые задачи сканирования и discovery."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from services.correlation import correlation_context, get_correlation_id, new_correlation_id
from services.inventory import load_inventory_async
from services.schemas import ScanSummary
from services.scanner import apply_device_names, discover_and_enrich, scan_devices

logger = logging.getLogger(__name__)


class ScanPhase(str, Enum):
    IDLE = "idle"
    DISCOVERY = "discovery"
    SCAN = "scan"
    RENAME = "rename"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ScanLogEntry:
    ts: datetime
    level: str
    message: str


@dataclass
class ScanJob:
    id: str
    discover: bool
    correlation_id: str = ""
    status: str = "running"
    phase: ScanPhase = ScanPhase.DISCOVERY
    message: str = ""
    progress_current: int = 0
    progress_total: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    summary: Optional[ScanSummary] = None
    error: Optional[str] = None
    logs: list[ScanLogEntry] = field(default_factory=list)

    @property
    def progress_pct(self) -> int:
        if self.progress_total <= 0:
            return 0
        return min(100, int(100 * self.progress_current / self.progress_total))


_current_job: Optional[ScanJob] = None
_last_scan: Optional[ScanSummary] = None
_last_scan_at: Optional[datetime] = None
_lock = threading.Lock()


def get_last_scan() -> tuple[Optional[ScanSummary], Optional[datetime]]:
    return _last_scan, _last_scan_at


def get_current_job() -> Optional[ScanJob]:
    return _current_job


def append_job_log(job: ScanJob, message: str, level: str = "info") -> None:
    job.logs.append(
        ScanLogEntry(
            ts=datetime.now(timezone.utc),
            level=level,
            message=message,
        )
    )
    if len(job.logs) > 500:
        job.logs = job.logs[-500:]


def _set_progress(
    job: ScanJob,
    phase: ScanPhase,
    message: str,
    current: int = 0,
    total: int = 0,
    *,
    log: bool = False,
) -> None:
    phase_changed = job.phase != phase
    job.phase = phase
    job.message = message
    job.progress_current = current
    job.progress_total = total
    if log or phase_changed:
        append_job_log(job, message)


async def _run_scan_job(job: ScanJob) -> None:
    global _last_scan, _last_scan_at

    cid = job.correlation_id or new_correlation_id()
    with correlation_context(cid):
        await _run_scan_job_inner(job)


async def _run_scan_job_inner(job: ScanJob) -> None:
    global _last_scan, _last_scan_at

    try:
        mode = "discovery + scan" if job.discover else "scan"
        append_job_log(job, f"Запуск: {mode}", "info")
        inventory = await load_inventory_async()
        append_job_log(
            job,
            f"Инвентарь: {len(inventory.devices)} устройств, {len(inventory.networks)} подсетей",
        )

        if job.discover and inventory.networks:
            subnet_count = len(inventory.networks)
            _set_progress(
                job,
                ScanPhase.DISCOVERY,
                f"Discovery: ping sweep {subnet_count} подсетей…",
                0,
                subnet_count,
                log=True,
            )

            def on_discovery_progress(done: int, total: int, subnet: str) -> None:
                _set_progress(
                    job,
                    ScanPhase.DISCOVERY,
                    f"Discovery: {subnet} ({done}/{total})",
                    done,
                    total,
                )
                if done > 0 and done == total:
                    append_job_log(job, f"Discovery: подсеть {subnet} ({done}/{total})")

            saved_count = 0

            def on_device_saved(device) -> None:
                nonlocal saved_count
                saved_count += 1
                _set_progress(
                    job,
                    ScanPhase.DISCOVERY,
                    f"Discovery: сохранено {saved_count} — {device.name} ({device.ip})",
                    job.progress_current,
                    job.progress_total,
                )
                append_job_log(
                    job,
                    f"Discovery: + {device.name} ({device.ip})",
                    "success",
                )

            discovered_devices = await discover_and_enrich(
                inventory.networks,
                inventory.devices,
                inventory.credential_profiles,
                on_progress=on_discovery_progress,
                on_device_saved=on_device_saved,
            )

            if os.getenv("AI_DISCOVERY_ENABLED", "false").lower() in ("1", "true", "yes", "on") and discovered_devices:
                from asgiref.sync import sync_to_async
                from services.task_queue import enqueue
                from core.models import BackgroundTask

                for device in discovered_devices:
                    await sync_to_async(enqueue, thread_sensitive=True)(
                        BackgroundTask.TASK_DISCOVERY_AI_ENRICHMENT,
                        payload={"device_name": device.name},
                        dedupe=False,
                    )

            inventory = await load_inventory_async()
            append_job_log(job, f"Discovery завершён, устройств: {len(inventory.devices)}")

        enabled_count = sum(1 for d in inventory.devices if d.enabled)
        _set_progress(
            job,
            ScanPhase.SCAN,
            f"Сканирование {enabled_count} устройств…",
            0,
            enabled_count,
            log=True,
        )

        def on_scan_progress(done: int, total: int, result) -> None:
            _set_progress(
                job,
                ScanPhase.SCAN,
                f"Сканирование: {done}/{total}",
                done,
                total,
            )
            if (
                done == total
                or done % 25 == 0
                or result.status.value != "offline"
            ):
                append_job_log(
                    job,
                    f"scan | {result.status.value:8} | {result.name} ({result.ip})",
                )

        summary = await scan_devices(
            inventory.devices,
            on_progress=on_scan_progress,
        )

        _set_progress(job, ScanPhase.RENAME, "Обновление имён устройств…", 0, 0, log=True)
        updated_devices, names_changed = await apply_device_names(
            inventory.devices,
            summary.results,
            inventory.credential_profiles,
        )
        if names_changed:
            inventory = await load_inventory_async()
            name_by_ip = {d.ip: d.name for d in inventory.devices}
            for result in summary.results:
                if result.ip in name_by_ip:
                    result.name = name_by_ip[result.ip]

        _last_scan = summary
        _last_scan_at = datetime.now(timezone.utc)
        job.summary = summary
        job.status = "completed"
        job.phase = ScanPhase.DONE
        job.message = (
            f"Готово: {summary.online} online, "
            f"{summary.partial} partial, {summary.offline} offline"
        )
        job.progress_current = summary.total
        job.progress_total = summary.total
        job.finished_at = datetime.now(timezone.utc)
        append_job_log(job, job.message, "success")
        logger.info(
            "scan_job | completed | job_id=%s corr=%s",
            job.id,
            get_correlation_id(),
        )
        try:
            from services.metrics import refresh_compliance_gauges

            refresh_compliance_gauges()
        except Exception:
            pass
        try:
            from services.scan_history import persist_scan_run_async

            run_row = await persist_scan_run_async(
                summary,
                job_id=job.id,
                discover=job.discover,
                status="completed",
            )
            if os.getenv("AI_ENABLED", "false").lower() in ("1", "true", "yes", "on"):
                from asgiref.sync import sync_to_async
                from services.task_queue import enqueue
                from core.models import BackgroundTask

                await sync_to_async(enqueue, thread_sensitive=True)(
                    BackgroundTask.TASK_SCAN_AI_ANALYSIS,
                    payload={"scan_run_id": run_row.id},
                    dedupe=True,
                )
        except Exception:
            logger.exception("scan_job | failed to persist history")

    except Exception as exc:
        logger.exception(
            "scan_job | failed | job_id=%s corr=%s",
            job.id,
            get_correlation_id(),
        )
        job.status = "failed"
        job.phase = ScanPhase.FAILED
        job.error = str(exc)
        job.message = f"Ошибка: {exc}"
        job.finished_at = datetime.now(timezone.utc)
        append_job_log(job, job.message, "error")
        try:
            from services.scan_history import persist_failed_scan_async

            await persist_failed_scan_async(
                job_id=job.id,
                discover=job.discover,
                error=str(exc),
            )
        except Exception:
            logger.exception("scan_job | failed to persist failed run")


def _thread_runner(job: ScanJob) -> None:
    asyncio.run(_run_scan_job(job))


def start_scan(discover: bool = False) -> ScanJob:
    global _current_job

    with _lock:
        if _current_job and _current_job.status == "running":
            return _current_job

        job = ScanJob(
            id=uuid.uuid4().hex[:12],
            discover=discover,
            correlation_id=get_correlation_id() or new_correlation_id(),
            phase=ScanPhase.DISCOVERY if discover else ScanPhase.SCAN,
            message="Запуск…" if discover else "Подготовка к сканированию…",
        )
        append_job_log(job, job.message)
        _current_job = job
        thread = threading.Thread(
            target=_thread_runner,
            args=(job,),
            name=f"scan-{job.id}",
            daemon=True,
        )
        thread.start()
        return job
