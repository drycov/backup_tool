"""Stage 3.2b custom roles + OpenAPI CI snapshot."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from django.test import Client

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "openapi.snapshot.json"


@pytest.fixture
def authed(client: Client):
    from core.models import User
    from services.auth import hash_password, seed_default_admin
    from services.custom_roles import seed_system_roles

    seed_default_admin()
    seed_system_roles()
    User.objects.filter(username="admin").update(password_hash=hash_password("adminpass"))
    res = client.post(
        "/api/auth/login",
        data=json.dumps({"username": "admin", "password": "adminpass"}),
        content_type="application/json",
    )
    assert res.status_code == 200
    return client


@pytest.mark.django_db
def test_compliance_auditor_builtin_permissions(client):
    from core.models import User
    from services.auth import hash_password, user_has_permission
    from services.rbac import PERMISSION_AUDIT_READ, PERMISSION_COMPLIANCE_READ, PERMISSION_RUN_SCAN

    user = User.objects.create(
        username="auditor1",
        password_hash=hash_password("x"),
        role="compliance_auditor",
        is_active=True,
    )
    assert user_has_permission(user, PERMISSION_COMPLIANCE_READ)
    assert user_has_permission(user, PERMISSION_AUDIT_READ)
    assert not user_has_permission(user, PERMISSION_RUN_SCAN)


@pytest.mark.django_db
def test_custom_role_overrides_permissions(client):
    from core.models import CustomRole, User
    from services.auth import hash_password, user_has_permission
    from services.custom_roles import create_custom_role, seed_system_roles
    from services.rbac import PERMISSION_COMPLIANCE_READ, PERMISSION_RUN_SCAN

    seed_system_roles()
    row = create_custom_role(
        slug="noc_readonly",
        label="NOC read",
        permissions=[PERMISSION_COMPLIANCE_READ],
    )
    cr = CustomRole.objects.get(id=row["id"])
    user = User.objects.create(
        username="noc1",
        password_hash=hash_password("x"),
        role="operator",
        custom_role=cr,
        is_active=True,
    )
    assert user_has_permission(user, PERMISSION_COMPLIANCE_READ)
    assert not user_has_permission(user, PERMISSION_RUN_SCAN)


@pytest.mark.django_db
def test_ldap_scope_locked_preserves_scope(client):
    from core.models import User
    from services.auth import upsert_ldap_user

    User.objects.create(
        username="ldapscope",
        password_hash="x",
        role="viewer",
        is_active=True,
        auth_source="ldap",
        allowed_groups=["hex"],
        allowed_sites=["dc1"],
        scope_locked=True,
    )
    upsert_ldap_user("ldapscope", "operator", allowed_groups=["us"], allowed_sites=["dc2"])
    user = User.objects.get(username="ldapscope")
    assert user.allowed_groups == ["hex"]
    assert user.allowed_sites == ["dc1"]


@pytest.mark.django_db
def test_custom_roles_api_crud(authed):
    res = authed.get("/api/auth/custom-roles")
    assert res.status_code == 200
    items = res.json().get("items") or []
    assert any(r.get("slug") == "compliance_auditor" for r in items)

    created = authed.post(
        "/api/auth/custom-roles",
        data=json.dumps(
            {
                "slug": "ci_role",
                "label": "CI Role",
                "permissions": ["compliance:read", "audit:read"],
            }
        ),
        content_type="application/json",
    )
    assert created.status_code == 201
    role_id = created.json()["id"]

    updated = authed.put(
        f"/api/auth/custom-roles/{role_id}",
        data=json.dumps({"label": "CI Role v2"}),
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "CI Role v2"

    deleted = authed.delete(f"/api/auth/custom-roles/{role_id}")
    assert deleted.status_code == 200


@pytest.mark.django_db
def test_user_custom_role_assignment(authed):
    from core.models import User
    from services.auth import hash_password
    from services.custom_roles import create_custom_role

    row = create_custom_role(
        slug="assign_test",
        label="Assign",
        permissions=["compliance:read"],
    )
    target = User.objects.create(
        username="assignee",
        password_hash=hash_password("secret12"),
        role="viewer",
        is_active=True,
    )
    res = authed.put(
        f"/api/auth/users/{target.id}",
        data=json.dumps({"custom_role_id": row["id"]}),
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.json().get("custom_role_id") == row["id"]

    clear = authed.put(
        f"/api/auth/users/{target.id}",
        data=json.dumps({"custom_role_id": 0, "clear_custom_role": True}),
        content_type="application/json",
    )
    assert clear.status_code == 200
    assert clear.json().get("custom_role_id") is None


def test_openapi_snapshot_matches_live():
    assert SNAPSHOT.is_file(), "Run: python scripts/check_openapi_drift.py --write"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_openapi_drift.py"), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.django_db
def test_openapi_includes_custom_roles_path(client):
    res = client.get("/api/openapi.json")
    assert res.status_code == 200
    paths = res.json().get("paths") or {}
    assert "/api/auth/custom-roles" in paths
    schemas = res.json().get("components", {}).get("schemas") or {}
    assert "Device" in schemas
    assert "LoginRequest" in schemas
