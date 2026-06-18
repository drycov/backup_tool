"""System settings API (env → UI / SystemConfig)."""

from __future__ import annotations

import json
import os

import pytest

from core.models import AuditEvent
from services.audit import ACTION_SETTINGS_UPDATE
from tests.helpers import login


@pytest.fixture
def authed(client, db):
    from core.models import User
    from services.auth import hash_password, seed_default_admin

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
def test_system_settings_api_roundtrip(admin_client, db):
    response = admin_client.get("/api/settings/system")
    assert response.status_code == 200
    data = response.json()
    assert "oxidized_engine" in data
    assert "zabbix_auth_key_set" in data

    payload = {
        "oxidized_engine": "python",
        "zabbix_auth_key": "test-zabbix-secret",
        "zabbix_monitoring_enabled": True,
        "audit_retention_days": 180,
        "access_token_expire_minutes": 240,
        "backup_data_dir": "/data/backups",
        "task_worker_poll_sec": 45,
        "metrics_enabled": True,
        "task_worker_enabled": True,
        "behind_https_proxy": False,
    }
    response = admin_client.put(
        "/api/settings/system",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    saved = response.json()
    assert saved["audit_retention_days"] == 180
    assert saved["zabbix_auth_key_set"] is True
    assert saved["access_token_expire_minutes"] == 240
    assert AuditEvent.objects.filter(
        action=ACTION_SETTINGS_UPDATE, target="system"
    ).exists()


@pytest.mark.django_db
def test_system_settings_apply_runtime_overrides(admin_client, db, settings):
    admin_client.put(
        "/api/settings/system",
        data=json.dumps(
            {
                "zabbix_auth_key": "runtime-key",
                "zabbix_monitoring_enabled": False,
                "audit_retention_days": 90,
            }
        ),
        content_type="application/json",
    )
    from services.system_settings import get_config

    cfg = get_config()
    assert cfg.zabbix_auth_key == "runtime-key"
    assert cfg.zabbix_monitoring_enabled is False
    assert cfg.audit_retention_days == 90

    from services.system_settings import apply_runtime_overrides

    apply_runtime_overrides()
    assert settings.ZABBIX_AUTH_KEY == "runtime-key"
    assert settings.ZABBIX_MONITORING_ENABLED is False
    assert settings.AUDIT_RETENTION_DAYS == 90
