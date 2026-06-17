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
        AuditEvent.objects.create(
            username=username or "system",
            action=action,
            target=target[:256],
            detail=detail[:2000],
            ip_address=_client_ip(request)[:64],
        )
        logger.info("audit | %s | %s | %s | %s", username, action, target, detail)
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
        "items": [
            {
                "id": row.id,
                "username": row.username,
                "action": row.action,
                "target": row.target,
                "detail": row.detail,
                "ip_address": row.ip_address,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }
