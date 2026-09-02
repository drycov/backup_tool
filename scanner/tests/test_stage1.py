"""Stage 1 API tests: settings tabs, policies, LDAP mock, readiness."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
from django.test import Client

from tests.helpers import login


@pytest.fixture
def authed(client: Client) -> Client:
    from core.models import User
    from services.auth import hash_password

    admin = User.objects.filter(username="admin").first()
    if not admin:
        from services.auth import seed_default_admin
        seed_default_admin()
    else:
        admin.password_hash = hash_password(os.environ.get("ADMIN_PASSWORD", "pytest-admin-pass"))
        admin.must_change_password = False
        admin.is_active = True
        admin.save()
    login(client)
    return client


@pytest.mark.django_db
def test_git_settings_round_trip(authed: Client):
    get_res = authed.get("/api/settings/git")
    assert get_res.status_code == 200
    before = get_res.json()
    payload = {**before, "git_branch": "stage1-test", "git_commit_user": "CI Bot"}
    put_res = authed.put(
        "/api/settings/git",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert put_res.status_code == 200, put_res.content
    saved = put_res.json()
    assert saved["git_branch"] == "stage1-test"
    assert saved["git_commit_user"] == "CI Bot"


@pytest.mark.django_db
def test_scan_settings_round_trip(authed: Client):
    get_res = authed.get("/api/settings/scan")
    assert get_res.status_code == 200
    before = get_res.json()
    payload = {**before, "scan_concurrency": 42}
    put_res = authed.put(
        "/api/settings/scan",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert put_res.status_code == 200, put_res.content
    assert put_res.json()["scan_concurrency"] == 42


@pytest.mark.django_db
def test_oxidized_settings_round_trip(authed: Client):
    get_res = authed.get("/api/settings/oxidized")
    assert get_res.status_code == 200
    before = get_res.json()
    payload = {**before, "interval": 7200, "threads": 4}
    put_res = authed.put(
        "/api/settings/oxidized",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert put_res.status_code == 200, put_res.content
    saved = put_res.json()
    assert saved["interval"] == 7200
    assert saved["threads"] == 4


@pytest.mark.django_db
def test_ldap_settings_round_trip(authed: Client):
    get_res = authed.get("/api/settings/ldap")
    assert get_res.status_code == 200
    before = get_res.json()
    payload = {
        **before,
        "enabled": True,
        "server": "ldap://test.example.com:389",
        "user_base": "DC=test,DC=local",
        "bind_dn": "CN=svc,DC=test,DC=local",
    }
    put_res = authed.put(
        "/api/settings/ldap",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert put_res.status_code == 200, put_res.content
    saved = put_res.json()
    assert saved["server"] == "ldap://test.example.com:389"
    assert saved["enabled"] is True


@pytest.mark.django_db
def test_ldap_test_bind_mock(authed: Client):
    with patch(
        "services.ldap_settings.test_connection",
        return_value={"ok": True, "message": "Bind OK"},
    ):
        res = authed.post(
            "/api/settings/ldap/test",
            data=json.dumps({"mode": "bind"}),
            content_type="application/json",
        )
    assert res.status_code == 200
    assert res.json().get("ok") is True


@pytest.mark.django_db
def test_radius_settings_round_trip(authed: Client):
    get_res = authed.get("/api/settings/radius")
    assert get_res.status_code == 200
    before = get_res.json()
    payload = {
        **before,
        "enabled": True,
        "server": "radius.example.com",
        "port": 1812,
        "secret": "testing-123",
        "role_attribute": "Filter-Id",
        "admin_values": "Backup-Admin",
        "operator_values": "NOC",
        "default_role": "operator",
    }
    put_res = authed.put(
        "/api/settings/radius",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert put_res.status_code == 200, put_res.content
    saved = put_res.json()
    assert saved["server"] == "radius.example.com"
    assert saved["enabled"] is True
    assert saved["secret_set"] is True
    assert saved["default_role"] == "operator"


@pytest.mark.django_db
def test_radius_test_connection_mock(authed: Client):
    with patch(
        "services.radius_settings.test_connection",
        return_value={"ok": True, "message": "RADIUS OK", "role": "operator"},
    ):
        res = authed.post(
            "/api/settings/radius/test",
            data=json.dumps({"username": "noc", "password": "pass"}),
            content_type="application/json",
        )
    assert res.status_code == 200
    assert res.json().get("ok") is True
    assert res.json().get("role") == "operator"


@pytest.mark.django_db
def test_group_policies_crud(authed: Client):
    payload = {
        "group_name": "hex",
        "backup_interval_sec": 1800,
        "model": "routeros",
        "mk_binary_enabled": True,
        "mk_export_enabled": None,
    }
    put_res = authed.put(
        "/api/policies/groups",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert put_res.status_code == 200, put_res.content
    saved = put_res.json()
    assert saved["group_name"] == "hex"
    assert saved["backup_interval_sec"] == 1800

    list_res = authed.get("/api/policies/groups")
    assert list_res.status_code == 200
    names = {p["group_name"] for p in list_res.json().get("policies", [])}
    assert "hex" in names

    del_res = authed.delete("/api/policies/groups/hex")
    assert del_res.status_code == 200


@pytest.mark.django_db
def test_bulk_device_update(authed: Client):
    from core.models import Device as DeviceModel

    DeviceModel.objects.create(name="bulk-a", ip="10.1.1.1", group="hex", enabled=True)
    DeviceModel.objects.create(name="bulk-b", ip="10.1.1.2", group="hex", enabled=True)
    res = authed.post(
        "/inventory/devices/bulk",
        data=json.dumps({"names": ["bulk-a", "bulk-b"], "maintenance": True, "enabled": False}),
        content_type="application/json",
    )
    assert res.status_code == 200, res.content
    devices = {d["name"]: d for d in res.json().get("devices", [])}
    assert devices["bulk-a"]["maintenance"] is True
    assert devices["bulk-a"]["enabled"] is False


@pytest.mark.django_db
def test_compliance_export_pdf(authed: Client):
    res = authed.get("/api/compliance/export?format=pdf")
    assert res.status_code == 200
    assert res["Content-Type"] == "application/pdf"
    assert res.content[:4] == b"%PDF"


@pytest.mark.django_db
def test_health_ready_endpoint(authed: Client):
    with patch("api.views.check_health", return_value={"reachable": True, "engine": "python", "nodes_count": 0}):
        res = authed.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] is True
    assert data["checks"]["oxidized_worker"] is True


@pytest.mark.django_db
def test_change_password_flow(client: Client):
    from core.models import User
    from services.auth import hash_password

    User.objects.filter(username="admin").delete()
    User.objects.create(
        username="admin",
        password_hash=hash_password("oldpass12"),
        role="admin",
        is_active=True,
        auth_source="local",
        must_change_password=True,
    )
    login(client, password="oldpass12")
    me = client.get("/api/auth/me").json()
    assert me.get("must_change_password") is True

    bad = client.post(
        "/api/auth/change-password",
        data=json.dumps({"current_password": "wrong", "new_password": "newpass123"}),
        content_type="application/json",
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/auth/change-password",
        data=json.dumps({"current_password": "oldpass12", "new_password": "newpass123"}),
        content_type="application/json",
    )
    assert ok.status_code == 200
    me2 = client.get("/api/auth/me").json()
    assert me2.get("must_change_password") is False
