"""История scan/discovery и тренды online/offline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from asgiref.sync import sync_to_async

from core.models import ScanRun
from services.schemas import ScanSummary


def _compact_results(summary: ScanSummary) -> list[dict[str, str]]:
    return [
        {"name": r.name, "ip": r.ip, "status": r.status.value}
        for r in summary.results
    ]


def persist_scan_run(
    summary: ScanSummary,
    *,
    job_id: str = "",
    discover: bool = False,
    status: str = "completed",
    error: str = "",
) -> ScanRun:
    run = ScanRun.objects.create(
        job_id=job_id,
        discover=discover,
        status=status,
        total=summary.total,
        online=summary.online,
        offline=summary.offline,
        partial=summary.partial,
        scanned_at=summary.scanned_at,
        error=error,
        results_json=_compact_results(summary),
    )
    _prune_old_runs()
    return run


def persist_failed_scan(
    *,
    job_id: str = "",
    discover: bool = False,
    error: str,
) -> ScanRun:
    now = datetime.now(timezone.utc)
    run = ScanRun.objects.create(
        job_id=job_id,
        discover=discover,
        status="failed",
        scanned_at=now,
        error=error,
        results_json=[],
    )
    _prune_old_runs()
    return run


def _prune_old_runs() -> None:
    keep = 500
    ids = list(
        ScanRun.objects.order_by("-scanned_at").values_list("id", flat=True)[keep:]
    )
    if ids:
        ScanRun.objects.filter(id__in=ids).delete()


def get_latest_scan_reachability() -> dict[str, str]:
    run = ScanRun.objects.filter(status="completed").order_by("-scanned_at").first()
    if not run:
        return {}
    return {
        str(item.get("name", "")): str(item.get("status", "unknown"))
        for item in (run.results_json or [])
        if item.get("name")
    }


def get_scan_history(*, limit: int = 50, days: int = 30) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    qs = ScanRun.objects.filter(scanned_at__gte=since).order_by("-scanned_at")[:limit]
    return {
        "days": days,
        "items": [
            {
                "id": row.id,
                "job_id": row.job_id,
                "discover": row.discover,
                "status": row.status,
                "total": row.total,
                "online": row.online,
                "offline": row.offline,
                "partial": row.partial,
                "scanned_at": row.scanned_at,
                "error": row.error or None,
                "ai_analysis": row.ai_analysis or {},
            }
            for row in qs
        ],
    }


def get_scan_trends(*, days: int = 30) -> dict[str, Any]:
    days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    runs = (
        ScanRun.objects.filter(status="completed", scanned_at__gte=since)
        .order_by("scanned_at")
        .values("scanned_at", "online", "offline", "partial", "total", "discover")
    )
    points: list[dict[str, Any]] = []
    for row in runs:
        scanned_at: datetime = row["scanned_at"]
        if scanned_at.tzinfo is None:
            scanned_at = scanned_at.replace(tzinfo=timezone.utc)
        points.append(
            {
                "scanned_at": scanned_at,
                "online": row["online"],
                "offline": row["offline"],
                "partial": row["partial"],
                "total": row["total"],
                "discover": row["discover"],
            }
        )
    latest = ScanRun.objects.filter(status="completed").order_by("-scanned_at").first()
    return {
        "days": days,
        "points": points,
        "latest": {
            "scanned_at": latest.scanned_at if latest else None,
            "online": latest.online if latest else 0,
            "offline": latest.offline if latest else 0,
            "partial": latest.partial if latest else 0,
            "total": latest.total if latest else 0,
        },
    }


def get_last_scan_from_db() -> tuple[Optional[ScanSummary], Optional[datetime]]:
    run = ScanRun.objects.filter(status="completed").order_by("-scanned_at").first()
    if not run:
        return None, None
    from services.schemas import ScanResult, ScanStatus

    results = []
    for item in run.results_json or []:
        try:
            status = ScanStatus(item.get("status", "unknown"))
        except ValueError:
            status = ScanStatus.UNKNOWN
        results.append(
            ScanResult(
                name=item.get("name", ""),
                ip=item.get("ip", ""),
                status=status,
                ping_ok=status != ScanStatus.OFFLINE,
                scanned_at=run.scanned_at,
            )
        )
    summary = ScanSummary(
        total=run.total,
        online=run.online,
        offline=run.offline,
        partial=run.partial,
        scanned_at=run.scanned_at,
        results=results,
    )
    return summary, run.scanned_at


persist_scan_run_async = sync_to_async(persist_scan_run, thread_sensitive=True)
persist_failed_scan_async = sync_to_async(persist_failed_scan, thread_sensitive=True)
