"""Тесты провижионинга (шаблоны Jinja2, preview, dry-run)."""

from __future__ import annotations

import pytest

from core.models import Device as DeviceModel, ProvisionRun, ProvisionTemplate
from services.provisioning import (
    ProvisioningError,
    build_render_context,
    preview_provision,
    render_template_body,
    run_provision,
    seed_default_templates,
)
from services.schemas import Device


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


@pytest.mark.django_db
def test_render_template_with_device_context():
    device = Device(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    ctx = build_render_context(device)
    out = render_template_body("/system identity set name={{ device.name }}\n", ctx)
    assert "name=r1" in out


@pytest.mark.django_db
def test_preview_provision_model_mismatch():
    ProvisionTemplate.objects.create(
        slug="ios-base",
        name="IOS",
        model="ios",
        body="hostname {{ name }}\n",
    )
    DeviceModel.objects.create(name="mk1", ip="10.0.0.1", model="routeros", group="hex")
    with pytest.raises(ProvisioningError, match="не совпадает"):
        preview_provision(template_slug="ios-base", device_name="mk1")


@pytest.mark.django_db
def test_dry_run_creates_run_record():
    ProvisionTemplate.objects.create(
        slug="ros-id",
        name="ROS",
        model="routeros",
        body="/system identity set name={{ device.name }}\n",
    )
    DeviceModel.objects.create(name="mk1", ip="10.0.0.1", model="routeros", group="hex")
    result = run_provision(template_slug="ros-id", device_name="mk1", dry_run=True, triggered_by="test")
    assert result["status"] == ProvisionRun.STATUS_DRY_RUN
    assert "name=mk1" in result["rendered_config"]
    assert ProvisionRun.objects.filter(device_name="mk1").exists()


@pytest.mark.django_db
def test_seed_default_templates():
    seed_default_templates()
    assert ProvisionTemplate.objects.filter(slug="routeros-identity").exists()
    seed_default_templates()
    assert ProvisionTemplate.objects.filter(slug="routeros-identity").count() == 1


@pytest.mark.django_db
def test_provision_preview_api(authed, client):
    ProvisionTemplate.objects.create(
        slug="ros-id",
        name="ROS",
        model="routeros",
        body="/system identity set name={{ device.name }}\n",
    )
    DeviceModel.objects.create(name="mk1", ip="10.0.0.1", model="routeros", group="hex")
    tpl = ProvisionTemplate.objects.get(slug="ros-id")
    res = client.post(
        "/api/provisioning/preview",
        data='{"template_id": %d, "device_name": "mk1"}' % tpl.id,
        content_type="application/json",
    )
    assert res.status_code == 200
    assert "mk1" in res.json()["rendered_config"]


@pytest.mark.django_db
def test_provision_analysis_api_handles_missing_config(authed, client):
    from unittest.mock import patch

    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="hex", site="dc1")

    with patch(
        "services.provision_template_builder.get_node_config",
        side_effect=lambda n: (None, f"Узел '{n}' не найден в Oxidized"),
    ):
        res = client.get("/api/provisioning/analysis?threshold=0.85&min_devices=2&group=hex")

    assert res.status_code == 200
    body = res.json()
    assert "clusters" in body
    assert body["clusters"][0]["skipped_reason"]
    assert body.get("log")


@pytest.mark.django_db
def test_provision_analysis_async_run(authed, client):
    from unittest.mock import patch

    from services.provision_analysis_runner import get_provision_analysis_run

    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="hex", site="dc1")

    with patch(
        "services.provision_template_builder.get_node_config",
        side_effect=lambda n: (f"/system identity set name={n}\n", None),
    ):
        start = client.post(
            "/api/provisioning/analysis/run",
            data='{"group": "hex", "threshold": 0.85, "min_devices": 2}',
            content_type="application/json",
        )
        assert start.status_code == 200
        run_id = start.json()["run_id"]

        for _ in range(50):
            run = get_provision_analysis_run(run_id)
            assert run is not None
            if run["status"] in ("completed", "failed"):
                break
            import time

            time.sleep(0.05)

        detail = client.get(f"/api/provisioning/analysis/runs/{run_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["status"] == "completed", body.get("error")
        assert body["result"]["clusters"]
        assert len(body["log"]) >= 2


@pytest.mark.django_db
def test_provision_filters_api(authed, client):
    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="ios", group="us", site="dc2", enabled=False)

    res = client.get("/api/provisioning/filters")
    assert res.status_code == 200
    body = res.json()
    assert body["device_count"] == 1
    assert [g["id"] for g in body["groups"]] == ["hex"]
    assert [s["id"] for s in body["sites"]] == ["dc1"]
    assert [m["id"] for m in body["models"]] == ["routeros"]
    assert body["template_models"][0]["id"] == "*"
    assert [d["name"] for d in body["devices"]] == ["r1"]
