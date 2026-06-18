"""Тесты backlog: RBAC, API key rotation, topology, OpenAPI."""

from __future__ import annotations

import json
import os

import pytest

from core.models import CustomRole, User
from services.auth import hash_password, seed_default_admin, upsert_ldap_user, user_permissions
from services.custom_roles import create_custom_role, seed_system_roles
from services.rbac import (
    PERMISSION_AUDIT_READ,
    PERMISSION_COMPLIANCE_READ,
    PERMISSION_RUN_SCAN,
    ROLE_COMPLIANCE_AUDITOR,
    user_has_role_permission,
)
from tests.helpers import login


@pytest.fixture
def authed(client, db):
    admin = User.objects.filter(username="admin").first()
    if not admin:
        seed_default_admin()
    else:
        admin.password_hash = hash_password(os.environ.get("ADMIN_PASSWORD", "pytest-admin-pass"))
        admin.must_change_password = False
        admin.save()
    login(client)
    return client


@pytest.mark.django_db
def test_scope_locked_preserves_ldap_scope():
    user = upsert_ldap_user("ldap1", "viewer", allowed_groups=["hex"], allowed_sites=["dc1"])
    user.scope_locked = True
    user.save()

    updated = upsert_ldap_user("ldap1", "operator", allowed_groups=["us"], allowed_sites=["dc2"])
    assert updated.allowed_groups == ["hex"]
    assert updated.allowed_sites == ["dc1"]
    assert updated.role == "operator"


@pytest.mark.django_db
def test_compliance_auditor_permissions():
    seed_system_roles()
    user = User(username="auditor", password_hash="x", role=ROLE_COMPLIANCE_AUDITOR, is_active=True)
    perms = user_permissions(user)
    assert PERMISSION_COMPLIANCE_READ in perms
    assert PERMISSION_AUDIT_READ in perms
    assert PERMISSION_RUN_SCAN not in perms


@pytest.mark.django_db
def test_custom_role_overrides_permissions():
    row = create_custom_role(
        slug="noc-read",
        label="NOC read",
        permissions=["inventory:read", "compliance:read"],
    )
    user = User(
        username="noc",
        password_hash="x",
        role="viewer",
        is_active=True,
        custom_role_id=row["id"],
    )
    user.custom_role = CustomRole.objects.get(id=row["id"])
    assert user_has_role_permission(user, PERMISSION_COMPLIANCE_READ)
    assert not user_has_role_permission(user, PERMISSION_RUN_SCAN)


@pytest.mark.django_db
def test_api_key_rotate(authed, client):
    from core.models import ApiKey
    from services.api_keys import KEY_PREFIX, _hash_key

    raw = KEY_PREFIX + "rotate-test-secret-value-xyz"
    ApiKey.objects.create(
        name="rotate-me",
        key_prefix=raw[:12],
        key_hash=_hash_key(raw),
        role="viewer",
    )
    row = ApiKey.objects.get(name="rotate-me")
    old_hash = row.key_hash

    res = client.post(f"/api/auth/api-keys/{row.id}/rotate")
    assert res.status_code == 200
    data = res.json()
    assert data["key"].startswith(KEY_PREFIX)

    row.refresh_from_db()
    assert row.key_hash != old_hash
    assert row.is_active is True


@pytest.mark.django_db
def test_netbox_topology_mock(authed, monkeypatch):
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
        audit_webhook_enabled=False,
        audit_webhook_url="",
        audit_webhook_secret="",
        audit_webhook_action_prefix="",
        netbox_url="https://netbox.test",
        netbox_token="token",
        netbox_default_group="hex",
        librenms_url="",
        librenms_token="",
        librenms_default_group="default",
        inventory_sync_enabled=False,
        inventory_sync_source="netbox",
        inventory_sync_interval_hours=24,
    )
    monkeypatch.setattr("services.netbox_topology.get_config", lambda: cfg)
    monkeypatch.setattr(
        "services.netbox_topology.load_inventory",
        lambda: type("Inv", (), {"devices": []})(),
    )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    if "devices" in url:
                        return {"results": [], "next": None}
                    return {"results": [{"id": 1, "a_terminations": [], "b_terminations": []}], "next": None}

            return Resp()

    monkeypatch.setattr("services.netbox_topology.httpx.Client", FakeClient)

    res = authed.get("/api/inventory/topology/netbox")
    assert res.status_code == 200
    body = res.json()
    assert "nodes" in body and "edges" in body


@pytest.mark.django_db
def test_openapi_snapshot_matches_runtime():
    from pathlib import Path

    from services.openapi_spec import build_openapi_spec

    snapshot = Path(__file__).resolve().parents[1] / "openapi.snapshot.json"
    if not snapshot.exists():
        pytest.skip("openapi.snapshot.json not generated yet")
    live = build_openapi_spec()
    stored = json.loads(snapshot.read_text(encoding="utf-8"))
    assert live["paths"].keys() == stored["paths"].keys()
