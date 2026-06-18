"""Stage 3.3: Slack/Teams, ServiceNow/Jira tickets, audit SIEM webhook."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from core.models import AlertState, AuditEvent, BackgroundTask
from services.audit_webhook import build_payload, deliver_audit_webhook, matches_action_prefix
from services.integration_tickets import create_ticket
from services.notification_channels import send_slack, send_teams
from services.task_queue import enqueue, process_next_task
from tests.helpers import login


@pytest.fixture
def authed(client, db):
    from core.models import User
    from services.auth import hash_password, seed_default_admin
    import os

    admin = User.objects.filter(username="admin").first()
    if not admin:
        seed_default_admin()
    else:
        admin.password_hash = hash_password(os.environ.get("ADMIN_PASSWORD", "pytest-admin-pass"))
        admin.must_change_password = False
        admin.save()
    login(client)
    return client


def test_slack_teams_webhook_format(monkeypatch):
    posted = []

    class FakeResp:
        is_success = True
        status_code = 200

    def fake_post(url, **kwargs):
        posted.append({"url": url, "json": kwargs.get("json")})
        return FakeResp()

    monkeypatch.setattr("services.notification_channels.httpx.post", fake_post)

    ok, msg = send_slack("https://hooks.slack.com/test", "Subject", "Body line", kind="error")
    assert ok is True
    assert "blocks" in posted[0]["json"]

    ok, msg = send_teams("https://teams.webhook/test", "Subject", "Body line", kind="report")
    assert ok is True
    assert posted[1]["json"]["@type"] == "MessageCard"


@pytest.mark.django_db
def test_audit_webhook_hmac_and_prefix(db, monkeypatch):
    from services import integration_settings

    cfg = integration_settings.IntegrationConfigData(
        snow_enabled=False,
        snow_instance_url="",
        snow_username="",
        snow_password="",
        snow_assignment_group="",
        jira_enabled=False,
        jira_url="",
        jira_username="",
        jira_api_token="",
        jira_project_key="",
        jira_issue_type="Task",
        ticket_on_backup_failed=True,
        ticket_on_device_offline=True,
        ticket_cooldown_hours=24,
        audit_webhook_enabled=True,
        audit_webhook_url="https://siem.example/hook",
        audit_webhook_secret="test-secret",
        audit_webhook_action_prefix="auth.",
    )
    monkeypatch.setattr("services.audit_webhook.get_config", lambda: cfg)

    row = AuditEvent.objects.create(
        username="admin",
        action="auth.login",
        target="",
        detail="",
        ip_address="127.0.0.1",
    )
    assert matches_action_prefix("auth.login", "auth.") is True
    assert matches_action_prefix("scan.run", "auth.") is False

    captured = {}

    class FakeResp:
        is_success = True
        status_code = 200

    def fake_post(url, *, content, headers, timeout):
        captured["url"] = url
        captured["body"] = content
        captured["headers"] = headers
        return FakeResp()

    monkeypatch.setattr("services.audit_webhook.httpx.post", fake_post)

    result = deliver_audit_webhook(row.id)
    assert result["ok"] is True
    expected_sig = hmac.new(
        b"test-secret",
        captured["body"],
        hashlib.sha256,
    ).hexdigest()
    assert captured["headers"]["X-Backup-Tools-Signature"] == f"sha256={expected_sig}"
    payload = json.loads(captured["body"].decode("utf-8"))
    assert payload["action"] == "auth.login"
    assert build_payload(row)["username"] == "admin"


@pytest.mark.django_db
def test_ticket_dedupe(db, monkeypatch):
    from services import integration_settings

    cfg = integration_settings.IntegrationConfigData(
        snow_enabled=True,
        snow_instance_url="https://snow.example",
        snow_username="u",
        snow_password="p",
        snow_assignment_group="",
        jira_enabled=False,
        jira_url="",
        jira_username="",
        jira_api_token="",
        jira_project_key="",
        jira_issue_type="Task",
        ticket_on_backup_failed=True,
        ticket_on_device_offline=False,
        ticket_cooldown_hours=24,
        audit_webhook_enabled=False,
        audit_webhook_url="",
        audit_webhook_secret="",
        audit_webhook_action_prefix="",
    )
    monkeypatch.setattr("services.integration_tickets.get_config", lambda: cfg)

    calls = {"n": 0}

    def fake_snow(cfg, summary, description):
        calls["n"] += 1
        return True, "ServiceNow: INC001"

    monkeypatch.setattr("services.integration_tickets._create_snow_incident", fake_snow)

    device = {"name": "router1", "ip": "10.0.0.1", "status": "failed"}
    create_ticket("backup_failed", device)
    create_ticket("backup_failed", device)
    assert calls["n"] == 1
    assert AlertState.objects.filter(alert_key="ticket:backup_failed:router1").exists()


@pytest.mark.django_db
def test_audit_webhook_task_queue(db, monkeypatch):
    from services import integration_settings

    cfg = integration_settings.IntegrationConfigData(
        snow_enabled=False,
        snow_instance_url="",
        snow_username="",
        snow_password="",
        snow_assignment_group="",
        jira_enabled=False,
        jira_url="",
        jira_username="",
        jira_api_token="",
        jira_project_key="",
        jira_issue_type="Task",
        ticket_on_backup_failed=True,
        ticket_on_device_offline=True,
        ticket_cooldown_hours=24,
        audit_webhook_enabled=True,
        audit_webhook_url="https://siem.example/hook",
        audit_webhook_secret="",
        audit_webhook_action_prefix="",
    )
    monkeypatch.setattr("services.audit_webhook.get_config", lambda: cfg)

    row = AuditEvent.objects.create(
        username="u",
        action="settings.update",
        target="integrations",
    )

    class FakeResp:
        is_success = True
        status_code = 200

    monkeypatch.setattr(
        "services.audit_webhook.httpx.post",
        lambda *a, **k: FakeResp(),
    )

    task = enqueue(
        BackgroundTask.TASK_AUDIT_WEBHOOK,
        payload={"audit_event_id": row.id},
        dedupe=False,
    )
    assert task is not None
    assert process_next_task() is True
    task.refresh_from_db()
    assert task.status == BackgroundTask.STATUS_COMPLETED


@pytest.mark.django_db
def test_integrations_settings_api(authed, client):
    res = client.get("/api/settings/integrations")
    assert res.status_code == 200
    assert "snow_enabled" in res.json()

    res = client.put(
        "/api/settings/integrations",
        data=json.dumps(
            {
                "snow_enabled": True,
                "snow_instance_url": "https://dev.service-now.com",
                "ticket_cooldown_hours": 12,
            }
        ),
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.json()["snow_enabled"] is True
