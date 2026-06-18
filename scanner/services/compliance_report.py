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


def send_scoped_compliance_report(
    user,
    *,
    site: str = "",
    role: str = "",
    critical: str | None = None,
    group: str = "",
    state: str = "",
) -> dict:
    """Отправить compliance-отчёт с учётом object scope и фильтров дашборда."""
    if not is_database_available():
        return {"ok": False, "message": "База данных недоступна"}

    cfg = get_config()
    if not cfg.compliance_report_telegram and not cfg.compliance_report_email:
        return {"ok": False, "message": "Compliance-отчёт отключён в настройках"}

    summary = compute_compliance_summary(
        site=site,
        role=role,
        critical=critical,
        group=group,
        state=state,
        user=user,
    )
    filters = summary.get("filters") or {}
    active_filters = [f"{k}={v}" for k, v in filters.items() if v]
    scope_note = ""
    if user is not None:
        from services.object_scope import has_object_scope, scope_public

        if has_object_scope(user):
            sp = scope_public(user)
            scope_note = (
                f"Scope: groups={sp.get('allowed_groups') or 'all'}, "
                f"sites={sp.get('allowed_sites') or 'all'}"
            )

    body = build_compliance_report_body(summary)
    if active_filters or scope_note:
        body = "\n".join(
            filter(
                None,
                [
                    body.splitlines()[0],
                    f"Фильтры: {', '.join(active_filters)}" if active_filters else "",
                    scope_note,
                    "",
                    *body.splitlines()[1:],
                ],
            )
        )

    subject = f"Backup Tools: compliance {summary.get('compliance_pct', 0)}% (scoped)"
    messages = notify_compliance_report(subject, body)
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
    """Deprecated: используйте task_worker + task_queue."""
    logger.warning("compliance | start_compliance_report_scheduler deprecated — use task worker")
