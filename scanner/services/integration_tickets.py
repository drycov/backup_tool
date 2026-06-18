"""Создание тикетов ServiceNow / Jira с dedupe через AlertState."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from core.models import AlertState
from services.integration_settings import get_config

logger = logging.getLogger(__name__)

TIMEOUT = 30.0

_EVENT_LABELS = {
    "backup_failed": "Backup failed",
    "device_offline": "Device offline",
}


def _should_create_ticket(alert_key: str, cooldown_hours: int) -> bool:
    now = datetime.now(timezone.utc)
    row = AlertState.objects.filter(alert_key=alert_key).first()
    if not row:
        return True
    cooldown = timedelta(hours=max(1, cooldown_hours))
    return now - row.last_notified_at >= cooldown


def _mark_ticket(alert_key: str) -> None:
    now = datetime.now(timezone.utc)
    AlertState.objects.update_or_create(
        alert_key=alert_key,
        defaults={"last_notified_at": now, "device_count": 1},
    )


def _ticket_summary(event: str, device: dict[str, Any]) -> str:
    name = device.get("name") or device.get("device") or "unknown"
    ip = device.get("ip") or ""
    label = _EVENT_LABELS.get(event, event)
    if ip:
        return f"[Backup Tools] {label}: {name} ({ip})"
    return f"[Backup Tools] {label}: {name}"


def _ticket_description(event: str, device: dict[str, Any]) -> str:
    lines = [
        f"Event: {event}",
        f"Device: {device.get('name') or device.get('device', '')}",
        f"IP: {device.get('ip', '')}",
    ]
    if device.get("status"):
        lines.append(f"Status: {device['status']}")
    if device.get("detail"):
        lines.append(f"Detail: {device['detail']}")
    if device.get("state_label"):
        lines.append(f"State: {device['state_label']}")
    if device.get("group"):
        lines.append(f"Group: {device['group']}")
    return "\n".join(lines)


def _create_snow_incident(cfg, summary: str, description: str) -> tuple[bool, str]:
    base = (cfg.snow_instance_url or "").strip().rstrip("/")
    if not base or not cfg.snow_username or not cfg.snow_password:
        return False, "ServiceNow: не заданы URL/credentials"
    url = f"{base}/api/now/table/incident"
    body: dict[str, Any] = {
        "short_description": summary[:160],
        "description": description[:4000],
        "urgency": "2",
        "impact": "2",
    }
    if cfg.snow_assignment_group:
        body["assignment_group"] = cfg.snow_assignment_group
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                url,
                json=body,
                auth=(cfg.snow_username, cfg.snow_password),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            if resp.is_success:
                data = resp.json()
                num = (data.get("result") or {}).get("number") or "created"
                return True, f"ServiceNow: {num}"
            return False, f"ServiceNow: HTTP {resp.status_code}"
    except Exception as exc:
        logger.warning("integration | snow failed: %s", exc)
        return False, f"ServiceNow: {exc}"


def _create_jira_issue(cfg, summary: str, description: str) -> tuple[bool, str]:
    base = (cfg.jira_url or "").strip().rstrip("/")
    if not base or not cfg.jira_username or not cfg.jira_api_token:
        return False, "Jira: не заданы URL/credentials"
    if not cfg.jira_project_key:
        return False, "Jira: не задан project key"
    url = f"{base}/rest/api/2/issue"
    body = {
        "fields": {
            "project": {"key": cfg.jira_project_key},
            "summary": summary[:255],
            "description": description[:32000],
            "issuetype": {"name": cfg.jira_issue_type or "Task"},
        }
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                url,
                json=body,
                auth=(cfg.jira_username, cfg.jira_api_token),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            if resp.is_success:
                data = resp.json()
                key = data.get("key") or "created"
                return True, f"Jira: {key}"
            return False, f"Jira: HTTP {resp.status_code}"
    except Exception as exc:
        logger.warning("integration | jira failed: %s", exc)
        return False, f"Jira: {exc}"


def create_ticket(event: str, device: dict[str, Any]) -> list[str]:
    """Создать тикет(ы) для события. Возвращает строки лога."""
    cfg = get_config()
    if event == "backup_failed" and not cfg.ticket_on_backup_failed:
        return []
    if event == "device_offline" and not cfg.ticket_on_device_offline:
        return []
    if not cfg.snow_enabled and not cfg.jira_enabled:
        return []

    name = str(device.get("name") or device.get("device") or "").strip()
    if not name:
        return []
    alert_key = f"ticket:{event}:{name}"
    if not _should_create_ticket(alert_key, cfg.ticket_cooldown_hours):
        logger.debug("integration | ticket skip cooldown | %s", alert_key)
        return []

    summary = _ticket_summary(event, device)
    description = _ticket_description(event, device)
    messages: list[str] = []
    if cfg.snow_enabled:
        ok, msg = _create_snow_incident(cfg, summary, description)
        messages.append(msg if ok else f"Ошибка: {msg}")
    if cfg.jira_enabled:
        ok, msg = _create_jira_issue(cfg, summary, description)
        messages.append(msg if ok else f"Ошибка: {msg}")

    if messages and any(not m.startswith("Ошибка:") for m in messages):
        _mark_ticket(alert_key)
    for msg in messages:
        level = logging.WARNING if msg.startswith("Ошибка:") else logging.INFO
        logger.log(level, "integration | ticket | %s", msg)
    return messages


def maybe_create_backup_failed_ticket(
    device: str,
    ip: str,
    status: str,
    detail: str = "",
    *,
    group: str = "",
) -> None:
    create_ticket(
        "backup_failed",
        {
            "name": device,
            "ip": ip,
            "status": status,
            "detail": detail,
            "group": group,
        },
    )


def maybe_create_tickets_for_degradation(kind: str, devices: list[dict[str, Any]]) -> None:
    if kind not in ("backup_failed", "device_offline"):
        return
    for device in devices[:20]:
        create_ticket(kind, device)
