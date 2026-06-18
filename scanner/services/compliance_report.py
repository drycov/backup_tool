"""Ежедневный compliance-отчёт по расписанию."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from services.backup_notifications import notify_compliance_report
from services.backup_settings import get_config
from services.compliance import compute_compliance_summary
from services.database import is_database_available

logger = logging.getLogger(__name__)

_thread: threading.Thread | None = None
_stop = threading.Event()


def build_compliance_report_body(summary: dict | None = None) -> str:
    data = summary or compute_compliance_summary()
    counts = data.get("counts") or {}
    lines = [
        "Backup Tools — ежедневный compliance-отчёт",
        f"Compliance: {data.get('compliance_pct', 0)}%",
        f"Устройств (enabled): {data.get('total_enabled', 0)}",
        "",
        f"OK: {counts.get('ok', 0)}",
        f"Ошибки бэкапа: {counts.get('failed', 0)}",
        f"Просрочено: {counts.get('overdue', 0)}",
        f"Stale (>{data.get('stale_days_threshold', 30)}д): {counts.get('stale', 0)}",
        f"Offline: {counts.get('unreachable', 0)}",
        f"Нет бэкапа: {counts.get('never', 0)}",
        "",
        "Проблемные устройства:",
    ]
    problems = [n for n in data.get("nodes") or [] if n.get("state") != "ok"]
    if not problems:
        lines.append("  (нет)")
    else:
        for node in problems[:40]:
            tags = []
            if node.get("critical"):
                tags.append("critical")
            if node.get("site"):
                tags.append(node["site"])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(
                f"  {node['name']} ({node['ip']}) — {node.get('state_label', '')}{tag_str}"
            )
        if len(problems) > 40:
            lines.append(f"  … и ещё {len(problems) - 40}")
    if data.get("oxidized_error"):
        lines.extend(["", f"Oxidized: {data['oxidized_error']}"])
    return "\n".join(lines)


def send_compliance_report(*, force: bool = False) -> dict:
    if not is_database_available():
        return {"ok": False, "message": "База данных недоступна"}

    cfg = get_config()
    if not force and not cfg.compliance_report_telegram and not cfg.compliance_report_email:
        return {"ok": False, "message": "Compliance-отчёт отключён в настройках"}

    summary = compute_compliance_summary()
    body = build_compliance_report_body(summary)
    subject = f"Backup Tools: compliance {summary.get('compliance_pct', 0)}%"
    messages = notify_compliance_report(subject, body)

    from core.models import BackupConfig

    row = BackupConfig.objects.filter(pk=1).first()
    if row:
        row.compliance_report_last_sent_at = datetime.now(timezone.utc)
        row.save(update_fields=["compliance_report_last_sent_at"])

    ok = bool(messages) and all(not m.startswith("Ошибка:") for m in messages)
    return {"ok": ok, "messages": messages or ["Нет активных каналов"]}


def _should_send_now(hour_utc: int) -> bool:
    now = datetime.now(timezone.utc)
    if now.hour != max(0, min(23, hour_utc)):
        return False
    row = None
    try:
        from core.models import BackupConfig

        row = BackupConfig.objects.filter(pk=1).first()
    except Exception:
        pass
    if row and row.compliance_report_last_sent_at:
        last = row.compliance_report_last_sent_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last.date() == now.date():
            return False
    return True


def _loop() -> None:
    time.sleep(90)
    while not _stop.is_set():
        try:
            cfg = get_config()
            if (cfg.compliance_report_telegram or cfg.compliance_report_email) and _should_send_now(
                cfg.compliance_report_hour_utc
            ):
                result = send_compliance_report(force=True)
                logger.info("compliance | daily report | %s", result)
        except Exception:
            logger.exception("compliance | daily report failed")
        _stop.wait(300)


def start_compliance_report_scheduler() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="compliance-report", daemon=True)
    _thread.start()
    logger.info("compliance | report scheduler started")
