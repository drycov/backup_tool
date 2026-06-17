"""Фоновые задачи сканирования и discovery."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from .inventory import load_inventory
from .models import ScanSummary
from .scanner import apply_device_names, discover_and_enrich, scan_devices

logger = logging.getLogger(__name__)


class ScanPhase(str, Enum):
    IDLE = "idle"
    DISCOVERY = "discovery"
    SCAN = "scan"
    RENAME = "rename"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ScanJob:
    id: str
    discover: bool
    status: str = "running"
    phase: ScanPhase = ScanPhase.DISCOVERY
    message: str = ""
    progress_current: int = 0
    progress_total: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    summary: Optional[ScanSummary] = None
    error: Optional[str] = None
    _task: Optional[asyncio.Task] = field(default=None, repr=False, compare=False)

    @property
    def progress_pct(self) -> int:
        if self.progress_total <= 0:
            return 0
        return min(100, int(100 * self.progress_current / self.progress_total))


_current_job: Optional[ScanJob] = None
_last_scan: Optional[ScanSummary] = None
_last_scan_at: Optional[datetime] = None
_lock = asyncio.Lock()


def get_last_scan() -> tuple[Optional[ScanSummary], Optional[datetime]]:
    return _last_scan, _last_scan_at


def get_current_job() -> Optional[ScanJob]:
    return _current_job


def _set_progress(
    job: ScanJob,
    phase: ScanPhase,
    message: str,
    current: int = 0,
    total: int = 0,
) -> None:
    job.phase = phase
    job.message = message
    job.progress_current = current
    job.progress_total = total


async def _run_scan_job(job: ScanJob) -> None:
    global _last_scan, _last_scan_at

    try:
        inventory = load_inventory()

        if job.discover and inventory.networks:
            subnet_count = len(inventory.networks)
            _set_progress(
                job,
                ScanPhase.DISCOVERY,
                f"Discovery: ping sweep {subnet_count} подсетей…",
                0,
                subnet_count,
            )

            def on_discovery_progress(done: int, total: int, subnet: str) -> None:
                _set_progress(
                    job,
                    ScanPhase.DISCOVERY,
                    f"Discovery: {subnet} ({done}/{total})",
                    done,
                    total,
                )

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

            await discover_and_enrich(
                inventory.networks,
                inventory.devices,
                inventory.credential_profiles,
                on_progress=on_discovery_progress,
                on_device_saved=on_device_saved,
            )

            inventory = load_inventory()
            if saved_count:
                logger.info(
                    "scan_job | discovery saved %d devices incrementally, total=%d",
                    saved_count,
                    len(inventory.devices),
                )

        enabled_count = sum(1 for d in inventory.devices if d.enabled)
        _set_progress(
            job,
            ScanPhase.SCAN,
            f"Сканирование {enabled_count} устройств…",
            0,
            enabled_count,
        )

        def on_scan_progress(done: int, total: int, _result) -> None:
            _set_progress(
                job,
                ScanPhase.SCAN,
                f"Сканирование: {done}/{total}",
                done,
                total,
            )

        summary = await scan_devices(
            inventory.devices,
            on_progress=on_scan_progress,
        )

        _set_progress(job, ScanPhase.RENAME, "Обновление имён устройств…", 0, 0)
        updated_devices, names_changed = await apply_device_names(
            inventory.devices,
            summary.results,
            inventory.credential_profiles,
        )
        if names_changed:
            inventory = load_inventory()
            updated_devices = inventory.devices
            name_by_ip = {d.ip: d.name for d in updated_devices}
            for result in summary.results:
                if result.ip in name_by_ip:
                    result.name = name_by_ip[result.ip]
            logger.info("scan_job | device names updated incrementally")

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
        logger.info("scan_job | completed | job_id=%s", job.id)

    except asyncio.CancelledError:
        job.status = "failed"
        job.phase = ScanPhase.FAILED
        job.error = "Отменено"
        job.message = "Сканирование отменено"
        job.finished_at = datetime.now(timezone.utc)
        raise
    except Exception as exc:
        logger.exception("scan_job | failed | job_id=%s", job.id)
        job.status = "failed"
        job.phase = ScanPhase.FAILED
        job.error = str(exc)
        job.message = f"Ошибка: {exc}"
        job.finished_at = datetime.now(timezone.utc)


async def start_scan(discover: bool = False) -> ScanJob:
    global _current_job

    async with _lock:
        if _current_job and _current_job.status == "running":
            return _current_job

        job = ScanJob(
            id=uuid.uuid4().hex[:12],
            discover=discover,
            phase=ScanPhase.DISCOVERY if discover else ScanPhase.SCAN,
            message="Запуск…" if discover else "Подготовка к сканированию…",
        )
        _current_job = job
        job._task = asyncio.create_task(_run_scan_job(job), name=f"scan-{job.id}")
        return job


async def wait_for_job(job_id: str, timeout: float | None = None) -> Optional[ScanJob]:
    job = _current_job
    if not job or job.id != job_id or not job._task:
        return None
    try:
        await asyncio.wait_for(asyncio.shield(job._task), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return job
