"""Журнал аудита действий пользователей."""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest

from core.models import AuditEvent

logger = logging.getLogger(__name__)

ACTION_CREDENTIAL_CREATE = "credential.create"
ACTION_CREDENTIAL_UPDATE = "credential.update"
ACTION_CREDENTIAL_DELETE = "credential.delete"
ACTION_OXIDIZED_FETCH = "oxidized.fetch"
ACTION_OXIDIZED_BACKUP_ALL = "oxidized.backup_all"
ACTION_SCAN_RUN = "scan.run"
ACTION_SCAN_DISCOVER = "scan.discover"
ACTION_SCAN_SCHEDULED = "scan.scheduled"
ACTION_SETTINGS_UPDATE = "settings.update"
ACTION_AUTH_LOGIN = "auth.login"
ACTION_AUTH_LOGIN_LDAP = "auth.login_ldap"
ACTION_AUTH_LOGIN_FAILED = "auth.login_failed"
ACTION_USER_SCOPE_UPDATE = "user.scope_update"
ACTION_COMPLIANCE_EXPORT = "compliance.export"
ACTION_COMPLIANCE_REPORT_SEND = "compliance.report_send"
ACTION_SECURITY_AUDIT_RUN = "security.audit_run"
ACTION_SECURITY_EXPORT = "security.export"
ACTION_MIKROTIK_RESTORE = "mikrotik.restore"
ACTION_API_KEY_CREATE = "api_key.create"
ACTION_API_KEY_ROTATE = "api_key.rotate"
ACTION_API_KEY_REVOKE = "api_key.revoke"
ACTION_API_KEY_USE = "api_key.use"


def _client_ip(request: HttpRequest | None) -> str:
    if request is None:
        return ""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def log_audit(
    username: str,
    action: str,
    *,
    target: str = "",
    detail: str = "",
    request: HttpRequest | None = None,
) -> None:
    try:
        event = AuditEvent.objects.create(
            username=username or "system",
            action=action,
            target=target[:256],
            detail=detail[:2000],
            ip_address=_client_ip(request)[:64],
        )
        logger.info("audit | %s | %s | %s | %s", username, action, target, detail)
        try:
            from services.audit_webhook import schedule_audit_webhook

            schedule_audit_webhook(event.id)
        except Exception:
            logger.exception("audit | webhook schedule failed | %s", action)
    except Exception:
        logger.exception("audit | failed to persist | %s %s", action, target)


def log_audit_user(
    user,
    action: str,
    *,
    target: str = "",
    detail: str = "",
    request: HttpRequest | None = None,
) -> None:
    username = getattr(user, "username", None) or "system"
    log_audit(username, action, target=target, detail=detail, request=request)


def list_audit_events(
    *,
    limit: int = 100,
    offset: int = 0,
    action: str = "",
) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    qs = AuditEvent.objects.all()
    if action:
        qs = qs.filter(action=action)
    total = qs.count()
    rows = qs[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_audit_row_dict(row) for row in rows],
    }


def _audit_row_dict(row: AuditEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "username": row.username,
        "action": row.action,
        "target": row.target,
        "detail": row.detail,
        "ip_address": row.ip_address,
        "created_at": row.created_at,
    }


def audit_events_to_csv(
    *,
    limit: int = 10000,
    action: str = "",
) -> str:
    import csv
    import io

    limit = max(1, min(limit, 50000))
    qs = AuditEvent.objects.all()
    if action:
        qs = qs.filter(action=action)
    rows = qs.order_by("-created_at")[:limit]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "created_at", "username", "action", "target", "detail", "ip_address"]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat() if row.created_at else "",
                row.username,
                row.action,
                row.target,
                row.detail,
                row.ip_address,
            ]
        )
    return buf.getvalue()


def purge_old_audit_events() -> dict[str, int]:
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone as dj_tz

    retention_days = int(getattr(settings, "AUDIT_RETENTION_DAYS", 0) or 0)
    if retention_days <= 0:
        return {"deleted": 0, "retention_days": retention_days, "skipped": 1}
    cutoff = dj_tz.now() - timedelta(days=retention_days)
    deleted, _ = AuditEvent.objects.filter(created_at__lt=cutoff).delete()
    logger.info("audit | purge | deleted=%s retention_days=%s", deleted, retention_days)
    return {"deleted": deleted, "retention_days": retention_days}
