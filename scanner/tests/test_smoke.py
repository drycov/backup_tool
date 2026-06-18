"""Smoke tests: health, migrate, settings round-trip."""

from __future__ import annotations

import json
import os
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


def _login(client: Client) -> None:
    res = client.post(
        "/api/auth/login",
        data=json.dumps({"username": "admin", "password": "changeme"}),
        content_type="application/json",
    )
    if res.status_code != 200:
        res = client.post(
            "/api/auth/login",
            data=json.dumps({"username": "admin", "password": "pytest-admin-pass"}),
            content_type="application/json",
        )
    assert res.status_code == 200, res.content


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

    get2 = client.get("/api/settings/backup")
    assert get2.status_code == 200
    after = get2.json()
    assert after.get("stale_days_threshold") == 31
    assert after.get("maintenance_end_hour_utc") == 5


def test_maintenance_window_service():
    from services.maintenance_window import is_maintenance_window_active
    from datetime import datetime, timezone

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
