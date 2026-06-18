"""Stage 2: task queue, metrics, audit extensions."""

from __future__ import annotations

import json

import pytest
from django.core.management import call_command
from django.test import Client

from core.models import AuditEvent, BackgroundTask, ScanConfig
from services.audit import ACTION_AUTH_LOGIN, ACTION_SETTINGS_UPDATE, purge_old_audit_events
from services.task_queue import enqueue, process_next_task, schedule_periodic_tasks
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
        admin.is_active = True
        admin.save()
    login(client)
    return client


@pytest.fixture
def admin_client(authed):
    return authed


@pytest.mark.django_db
def test_background_task_enqueue_and_process(db):
    task = enqueue(BackgroundTask.TASK_DEGRADE_CHECK, dedupe=False)
    assert task is not None
    assert task.status == BackgroundTask.STATUS_PENDING

    assert process_next_task() is True
    task.refresh_from_db()
    assert task.status == BackgroundTask.STATUS_COMPLETED


@pytest.mark.django_db
def test_schedule_periodic_scan(db):
    ScanConfig.objects.update_or_create(
        pk=1,
        defaults={
            "schedule_enabled": True,
            "schedule_interval_hours": 1,
            "schedule_discover": False,
        },
    )
    count = schedule_periodic_tasks()
    assert count >= 1
    assert BackgroundTask.objects.filter(
        task_type=BackgroundTask.TASK_SCHEDULED_SCAN,
        status=BackgroundTask.STATUS_PENDING,
    ).exists()


@pytest.mark.django_db
def test_metrics_endpoint(client, db):
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.content.decode()
    assert "compliance_pct" in body
    assert "backup_success_total" in body


@pytest.mark.django_db
def test_correlation_id_header(client, db):
    response = client.get("/health", HTTP_X_CORRELATION_ID="test-corr-123")
    assert response["X-Correlation-ID"] == "test-corr-123"


@pytest.mark.django_db
def test_audit_login_logged(authed, db):
    assert AuditEvent.objects.filter(action=ACTION_AUTH_LOGIN).exists()


@pytest.mark.django_db
def test_audit_settings_scan(admin_client, db):
    response = admin_client.put(
        "/api/settings/scan",
        data=json.dumps({"scan_concurrency": 40, "schedule_enabled": True}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert AuditEvent.objects.filter(
        action=ACTION_SETTINGS_UPDATE, target="scan"
    ).exists()


@pytest.mark.django_db
def test_audit_export_requires_admin(authed, db):
    response = authed.get("/api/audit/export")
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    assert "username" in response.content.decode()


@pytest.mark.django_db
def test_purge_audit(db, settings):
    settings.AUDIT_RETENTION_DAYS = 1
    AuditEvent.objects.create(username="u", action="test", target="t")
    result = purge_old_audit_events()
    assert "deleted" in result


@pytest.mark.django_db
def test_run_task_worker_once(db):
    enqueue(BackgroundTask.TASK_DEGRADE_CHECK, dedupe=False)
    call_command("run_task_worker", "--once")
    assert BackgroundTask.objects.filter(status=BackgroundTask.STATUS_COMPLETED).exists()


@pytest.mark.django_db
def test_scan_schedule_api_roundtrip(admin_client, db):
    payload = {
        "scan_concurrency": 50,
        "discover_max_hosts": 4096,
        "discover_ping_workers": 100,
        "schedule_enabled": True,
        "schedule_interval_hours": 12,
        "schedule_discover": True,
        "ovn_user": "satcoadm",
        "us_user": "satcoadm",
    }
    response = admin_client.put(
        "/api/settings/scan",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["schedule_enabled"] is True
    assert data["schedule_interval_hours"] == 12
