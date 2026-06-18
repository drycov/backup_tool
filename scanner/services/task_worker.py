"""Воркер очереди задач — inline-поток или management command."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_thread: threading.Thread | None = None
_stop = threading.Event()


def _poll_interval_sec() -> int:
    from services.system_settings import get_config

    return max(10, get_config().task_worker_poll_sec)


def tick() -> None:
    from services.metrics import refresh_all_gauges
    from services.task_queue import process_next_task, purge_stale_running, schedule_periodic_tasks

    purge_stale_running()
    schedule_periodic_tasks()
    while process_next_task():
        pass
    refresh_all_gauges()


def _loop() -> None:
    time.sleep(15)
    while not _stop.is_set():
        try:
            tick()
        except Exception:
            logger.exception("task_worker | tick failed")
        _stop.wait(_poll_interval_sec())


def start_inline_task_worker() -> None:
    """Запуск воркера в daemon-потоке (по умолчанию в web-контейнере)."""
    global _thread
    from services.system_settings import get_config

    if not get_config().task_worker_enabled:
        logger.info("task_worker | disabled in system settings")
        return
    if os.environ.get("TASK_WORKER_INLINE", "true").lower() in ("0", "false", "no"):
        logger.info("task_worker | inline disabled — use manage.py run_task_worker")
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="task-worker", daemon=True)
    _thread.start()
    logger.info("task_worker | inline started | poll=%ss", _poll_interval_sec())


def stop_inline_task_worker() -> None:
    _stop.set()
