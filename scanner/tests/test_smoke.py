"""Smoke tests: health, migrate, settings round-trip, RBAC scope."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import Client

from tests.conftest import DB_FILE


@pytest.fixture(scope="session", autouse=True)
def _cleanup_db():
    if DB_FILE.is_file():
        DB_FILE.unlink()
    yield
    if DB_FILE.is_file():
        DB_FILE.unlink(missing_ok=True)


@pytest.fixture
def client(db):
    from services.auth import seed_default_admin

    seed_default_admin()
    return Client()


def _login(client: Client, username: str = "admin", password: str | None = None) -> None:
    if password is not None:
        attempts = [password]
    elif username == "admin":
        attempts = [
            os.environ.get("ADMIN_PASSWORD"),
            "changeme",
            "pytest-admin-pass",
        ]
        attempts = [p for p in attempts if p]
    else:
        attempts = [password or "changeme"]

    res = None
    for pwd in attempts:
        res = client.post(
            "/api/auth/login",
            data=json.dumps({"username": username, "password": pwd}),
            content_type="application/json",
        )
        if res.status_code == 200:
            return
    assert res is not None and res.status_code == 200, res.content if res else "login failed"


@pytest.mark.django_db
def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "ok"


@pytest.mark.django_db
def test_migrate_idempotent():
    call_command("migrate", verbosity=0)
    call_command("migrate", verbosity=0)


@pytest.mark.django_db
def test_backup_settings_round_trip(client):
    _login(client)
    get_res = client.get("/api/settings/backup")
    assert get_res.status_code == 200
    before = get_res.json()
    assert "binary_enabled" in before

    payload = {
        **before,
        "stale_days_threshold": 31,
        "maintenance_start_hour_utc": 23,
        "maintenance_end_hour_utc": 5,
        "maintenance_window_enabled": True,
        "maintenance_days": [0, 1, 2, 3, 4],
    }
    put_res = client.put(
        "/api/settings/backup",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert put_res.status_code == 200, put_res.content
    saved = put_res.json()
    assert saved.get("stale_days_threshold") == 31
    assert saved.get("maintenance_start_hour_utc") == 23
    assert saved.get("maintenance_days") == [0, 1, 2, 3, 4]

    get2 = client.get("/api/settings/backup")
    assert get2.status_code == 200
    after = get2.json()
    assert after.get("stale_days_threshold") == 31
    assert after.get("maintenance_end_hour_utc") == 5
    assert after.get("maintenance_days") == [0, 1, 2, 3, 4]


def test_maintenance_window_service():
    from services.maintenance_window import is_maintenance_window_active

    assert is_maintenance_window_active(
        now=datetime(2026, 6, 17, 23, 0, tzinfo=timezone.utc),
        start_hour_utc=22,
        end_hour_utc=6,
    )
    assert not is_maintenance_window_active(
        now=datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc),
        start_hour_utc=22,
        end_hour_utc=6,
    )
    assert not is_maintenance_window_active(
        now=datetime(2026, 6, 20, 23, 0, tzinfo=timezone.utc),
        start_hour_utc=22,
        end_hour_utc=6,
        days=[0, 1, 2],
    )


@pytest.mark.django_db(transaction=True)
def test_persist_scan_run_from_async_context():
    import asyncio
    from datetime import datetime, timezone

    from services.scan_history import get_scan_history, persist_scan_run_async
    from services.schemas import ScanResult, ScanStatus, ScanSummary

    now = datetime.now(timezone.utc)
    summary = ScanSummary(
        total=2,
        online=1,
        offline=1,
        partial=0,
        scanned_at=now,
        results=[
            ScanResult(name="a", ip="1.1.1.1", status=ScanStatus.ONLINE, ping_ok=True, scanned_at=now),
            ScanResult(name="b", ip="2.2.2.2", status=ScanStatus.OFFLINE, ping_ok=False, scanned_at=now),
        ],
    )

    async def _persist():
        await persist_scan_run_async(summary, job_id="test-job", discover=False)

    asyncio.run(_persist())
    history = get_scan_history(limit=5)
    assert history["items"]
    assert history["items"][0]["job_id"] == "test-job"
    assert history["items"][0]["total"] == 2


@pytest.mark.django_db
def test_object_scope_filter():
    from core.models import User
    from services.object_scope import device_in_scope, filter_devices
    from services.schemas import Device

    user = User(username="op", password_hash="x", role="operator", allowed_groups=["hex"])
    devices = [
        Device(name="a", ip="1.1.1.1", group="hex"),
        Device(name="b", ip="2.2.2.2", group="us"),
    ]
    filtered = filter_devices(user, devices)
    assert len(filtered) == 1
    assert filtered[0].name == "a"
    assert device_in_scope(user, devices[1]) is False


@pytest.mark.django_db
def test_auth_me_includes_scope(client):
    _login(client)
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert "allowed_groups" in data
    assert "scoped" in data
    assert data.get("role") == "admin"


@pytest.mark.django_db
def test_inventory_scoped_operator(client):
    from core.models import Device as DeviceModel
    from core.models import User

    DeviceModel.objects.create(name="hex-r1", ip="10.0.0.1", group="hex")
    DeviceModel.objects.create(name="us-r1", ip="10.0.0.2", group="us")
    User.objects.create(
        username="hexop",
        password_hash="unused",
        role="operator",
        is_active=True,
        allowed_groups=["hex"],
    )
    from services.auth import hash_password

    User.objects.filter(username="hexop").update(password_hash=hash_password("hexpass"))
    _login(client, username="hexop", password="hexpass")
    res = client.get("/inventory")
    assert res.status_code == 200
    devices = res.json().get("devices") or []
    names = {d["name"] for d in devices}
    assert "hex-r1" in names
    assert "us-r1" not in names


@pytest.mark.django_db
def test_ldap_role_locked_preserves_role(client):
    from core.models import User
    from services.auth import upsert_ldap_user

    User.objects.create(
        username="ldapuser",
        password_hash="x",
        role="admin",
        is_active=True,
        auth_source="ldap",
        role_locked=True,
    )
    upsert_ldap_user("ldapuser", "viewer")
    user = User.objects.get(username="ldapuser")
    assert user.role == "admin"


@pytest.mark.django_db
def test_oxidized_backups_scope_forbidden(client):
    from core.models import Device as DeviceModel
    from core.models import User
    from services.auth import hash_password

    DeviceModel.objects.create(name="secret-r1", ip="10.0.0.9", group="secret")
    User.objects.create(
        username="hexonly",
        password_hash=hash_password("pass"),
        role="viewer",
        is_active=True,
        allowed_groups=["hex"],
    )
    _login(client, username="hexonly", password="pass")
    res = client.get("/api/oxidized/nodes/secret-r1/backups")
    assert res.status_code == 403
