"""Audit SIEM webhook — HMAC-подпись, async через task queue."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from core.models import AuditEvent, BackgroundTask
from services.integration_settings import get_config

logger = logging.getLogger(__name__)

TIMEOUT = 15.0


def matches_action_prefix(action: str, prefix: str) -> bool:
    needle = (prefix or "").strip()
    if not needle:
        return True
    return (action or "").startswith(needle)


def build_payload(row: AuditEvent) -> dict[str, Any]:
    return {
        "source": "backup-tools",
        "id": row.id,
        "username": row.username,
        "action": row.action,
        "target": row.target,
        "detail": row.detail,
        "ip_address": row.ip_address,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _sign_body(secret: str, body: bytes) -> str:
    if not secret:
        return ""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def deliver_audit_webhook(audit_event_id: int) -> dict[str, Any]:
    cfg = get_config()
    if not cfg.audit_webhook_enabled or not cfg.audit_webhook_url:
        return {"skipped": 1, "reason": "disabled"}

    row = AuditEvent.objects.filter(pk=audit_event_id).first()
    if not row:
        return {"skipped": 1, "reason": "not_found"}
    if not matches_action_prefix(row.action, cfg.audit_webhook_action_prefix):
        return {"skipped": 1, "reason": "prefix"}

    payload = build_payload(row)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    signature = _sign_body(cfg.audit_webhook_secret, body)
    if signature:
        headers["X-Backup-Tools-Signature"] = signature

    try:
        resp = httpx.post(
            cfg.audit_webhook_url.strip(),
            content=body,
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.is_success:
            logger.info("audit_webhook | delivered | id=%s action=%s", row.id, row.action)
            return {"ok": True, "status_code": resp.status_code}
        logger.warning(
            "audit_webhook | failed | id=%s http=%s", row.id, resp.status_code
        )
        return {"ok": False, "status_code": resp.status_code}
    except Exception as exc:
        logger.warning("audit_webhook | error | id=%s %s", row.id, exc)
        raise


def schedule_audit_webhook(audit_event_id: int) -> None:
    cfg = get_config()
    if not cfg.audit_webhook_enabled or not cfg.audit_webhook_url:
        return
    from services.database import is_database_available
    from services.task_queue import enqueue

    if not is_database_available():
        return
    enqueue(
        BackgroundTask.TASK_AUDIT_WEBHOOK,
        payload={"audit_event_id": audit_event_id},
        dedupe=False,
    )


def send_test_audit_webhook() -> dict[str, Any]:
    """POST тестового события на webhook (без записи в audit)."""
    cfg = get_config()
    if not cfg.audit_webhook_url:
        return {"ok": False, "message": "Webhook URL не задан"}
    payload = {
        "source": "backup-tools",
        "id": 0,
        "username": "test",
        "action": "test.webhook",
        "target": "",
        "detail": "Backup Tools integration test",
        "ip_address": "127.0.0.1",
        "created_at": None,
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    signature = _sign_body(cfg.audit_webhook_secret, body)
    if signature:
        headers["X-Backup-Tools-Signature"] = signature
    try:
        resp = httpx.post(
            cfg.audit_webhook_url.strip(),
            content=body,
            headers=headers,
            timeout=TIMEOUT,
        )
        ok = resp.is_success
        return {
            "ok": ok,
            "message": f"HTTP {resp.status_code}" if ok else f"Ошибка: HTTP {resp.status_code}",
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
