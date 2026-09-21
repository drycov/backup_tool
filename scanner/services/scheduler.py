"""APScheduler для внутренних периодических задач вместо cron."""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


def scheduler_interval_sec() -> int:
    return max(10, int(os.getenv("SCHEDULER_TICK_SEC", "30")))


def run_scheduler() -> None:
    from services.task_queue import schedule_periodic_tasks

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        schedule_periodic_tasks,
        trigger=IntervalTrigger(seconds=scheduler_interval_sec()),
        id="backup-tools-periodic-tasks",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    logger.info("scheduler | started | interval=%ss", scheduler_interval_sec())
    schedule_periodic_tasks()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler | stopped")
