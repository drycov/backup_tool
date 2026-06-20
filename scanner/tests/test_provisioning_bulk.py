"""Тесты bulk provision через task queue."""

from __future__ import annotations

import pytest

from core.models import BackgroundTask, Device as DeviceModel, ProvisionBulkRun, ProvisionRun, ProvisionTemplate
from services.provisioning import ProvisioningError
from services.provisioning_bulk import (
    create_bulk_run,
    list_bulk_targets,
    preview_bulk_provision,
)
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


@pytest.mark.django_db
def test_list_bulk_targets_filters_group_site():
    tpl = ProvisionTemplate.objects.create(
        slug="ros-id",
        name="ROS",
        model="routeros",
        body="/system identity set name={{ device.name }}\n",
    )
    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="hex", site="dc2")
    DeviceModel.objects.create(name="r3", ip="10.0.0.3", model="ios", group="hex", site="dc1")

    devices = list_bulk_targets(template=tpl, group="hex", site="dc1")
    assert [d.name for d in devices] == ["r1"]


@pytest.mark.django_db
def test_preview_all_devices_when_no_scope_filter():
    tpl = ProvisionTemplate.objects.create(
        slug="ros-id",
        name="ROS",
        model="routeros",
        body="/system identity set name={{ device.name }}\n",
    )
    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="us", site="dc2")

    preview = preview_bulk_provision(template_id=tpl.id)
    assert preview["device_count"] == 2
    assert {d["name"] for d in preview["devices"]} == {"r1", "r2"}


@pytest.mark.django_db
def test_bulk_run_via_task_queue_dry_run():
    tpl = ProvisionTemplate.objects.create(
        slug="ros-id",
        name="ROS",
        model="routeros",
        body="/system identity set name={{ device.name }}\n",
    )
    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="hex", site="dc1")

    bulk = create_bulk_run(
        template_id=tpl.id,
        group="hex",
        site="dc1",
        dry_run=True,
        triggered_by="test",
    )
    task = enqueue(
        BackgroundTask.TASK_PROVISION_BULK,
        payload={"bulk_run_id": bulk.id},
        dedupe=False,
    )
    assert task is not None
    assert process_next_task() is True

    bulk.refresh_from_db()
    assert bulk.status == ProvisionBulkRun.STATUS_COMPLETED
    assert bulk.devices_total == 2
    assert bulk.devices_completed == 2
    assert bulk.devices_failed == 0
    assert isinstance(bulk.log, list)
    assert len(bulk.log) >= 3
    assert any("r1" in line.get("text", "") for line in bulk.log)
    assert ProvisionRun.objects.filter(bulk_run=bulk).count() == 2


@pytest.mark.django_db
def test_exclude_complex_devices():
    tpl = ProvisionTemplate.objects.create(
        slug="gen-hex",
        name="Gen",
        model="routeros",
        body="/system identity set name={{ device.name }}\n",
        meta={"complex_devices": [{"name": "r2", "complex": True}]},
    )
    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="hex", site="dc1")

    devices = list_bulk_targets(template=tpl, group="hex", site="dc1", exclude_complex=True)
    assert [d.name for d in devices] == ["r1"]


@pytest.mark.django_db
def test_bulk_provision_api(authed, client):
    tpl = ProvisionTemplate.objects.create(
        slug="ros-id",
        name="ROS",
        model="routeros",
        body="/system identity set name={{ device.name }}\n",
    )
    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")

    preview = client.get(
        f"/api/provisioning/bulk?action=preview&template_id={tpl.id}&group=hex&site=dc1"
    )
    assert preview.status_code == 200
    assert preview.json()["device_count"] == 1

    res = client.post(
        "/api/provisioning/bulk/run",
        data='{"template_id": %d, "group": "hex", "site": "dc1", "dry_run": true, "async": false}'
        % tpl.id,
        content_type="application/json",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == ProvisionBulkRun.STATUS_COMPLETED
    assert body["devices_completed"] == 1

    detail = client.get(f"/api/provisioning/bulk/{body['id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["status"] == ProvisionBulkRun.STATUS_COMPLETED
    assert detail_body.get("log")


@pytest.mark.django_db
def test_provision_generate_async_run(authed, client):
    from unittest.mock import patch

    from services.provision_generate_runner import get_provision_generate_run
    from services.task_queue import process_next_task

    DeviceModel.objects.create(name="r1", ip="10.0.0.1", model="routeros", group="hex", site="dc1")
    DeviceModel.objects.create(name="r2", ip="10.0.0.2", model="routeros", group="hex", site="dc1")

    with patch(
        "services.provision_template_builder.get_node_config",
        side_effect=lambda n: (f"/system identity set name={n}\n", None),
    ):
        start = client.post(
            "/api/provisioning/templates/generate/run",
            data='{"group": "hex", "threshold": 0.85, "min_devices": 2, "upsert": true}',
            content_type="application/json",
        )
        assert start.status_code == 200
        run_id = start.json()["run_id"]

        for _ in range(50):
            process_next_task()
            run = get_provision_generate_run(run_id)
            assert run is not None
            if run["status"] in ("completed", "failed"):
                break

        detail = client.get(f"/api/provisioning/templates/generate/runs/{run_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["status"] == "completed", body.get("error")
        assert body["result"]["created"] or body["result"]["updated"]
        assert len(body["log"]) >= 2
