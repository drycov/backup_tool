"""Stage 3.4: NetBox/LibreNMS import, site hierarchy, tag filters."""

from __future__ import annotations

import json

import pytest

from core.models import Device as DeviceModel, Site
from services.compliance import compute_compliance_summary
from services.inventory_import import import_from_netbox
from services.sites import expand_site_slugs, site_matches_filter, upsert_site
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
def test_site_hierarchy_expand():
    upsert_site("msk", name="Moscow")
    upsert_site("msk-dc1", name="DC1", parent_slug="msk")
    upsert_site("msk-dc2", name="DC2", parent_slug="msk")

    expanded = expand_site_slugs("msk")
    assert "msk" in expanded
    assert "msk-dc1" in expanded
    assert "msk-dc2" in expanded
    assert site_matches_filter("msk-dc1", "msk") is True
    assert site_matches_filter("spb", "msk") is False


@pytest.mark.django_db
def test_compliance_tags_filter(db, monkeypatch):
    from services.schemas import Device, Inventory

    devices = [
        Device(name="a", ip="10.0.0.1", enabled=True, tags=["prod", "edge"]),
        Device(name="b", ip="10.0.0.2", enabled=True, tags=["lab"]),
    ]
    monkeypatch.setattr(
        "services.compliance.load_inventory",
        lambda: Inventory(devices=devices),
    )
    monkeypatch.setattr("services.compliance.get_nodes", lambda: ([], None))
    monkeypatch.setattr("services.compliance.get_latest_scan_reachability", lambda: {})

    summary = compute_compliance_summary(tags="prod")
    names = {n["name"] for n in summary["nodes"]}
    assert names == {"a"}


@pytest.mark.django_db
def test_netbox_import_mock(authed, monkeypatch):
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
    monkeypatch.setattr("services.inventory_import.get_config", lambda: cfg)

    sites = [{"slug": "dc1", "name": "DC1", "parent": None}]
    devices = [
        {
            "name": "sw-core",
            "primary_ip4": {"address": "10.1.1.1/24"},
            "site": {"slug": "dc1"},
            "role": {"slug": "core"},
            "device_type": {"slug": "cisco-ios"},
            "tags": [{"slug": "prod"}],
        }
    ]

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
                    if "sites" in url:
                        return {"results": sites, "next": None}
                    return {"results": devices, "next": None}

            return Resp()

    monkeypatch.setattr("services.inventory_import.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "services.inventory_import.update_oxidized_credentials",
        lambda inv: None,
    )

    result = import_from_netbox()
    assert result.created == 1
    row = DeviceModel.objects.get(name="sw-core")
    assert row.ip == "10.1.1.1"
    assert row.site == "dc1"
    assert "prod" in row.tags
    assert Site.objects.filter(slug="dc1").exists()


@pytest.mark.django_db
def test_netbox_import_api(authed, client, monkeypatch):
    from services.inventory_import import ImportResult

    monkeypatch.setattr(
        "services.inventory_import.import_from_netbox",
        lambda dry_run=False: ImportResult(created=2, updated=1, skipped=0),
    )
    monkeypatch.setattr("api.views.update_oxidized_credentials", lambda inv: None)

    res = client.post("/api/inventory/import/netbox")
    assert res.status_code == 200
    body = res.json()
    assert body["created"] == 2


@pytest.mark.django_db
def test_sites_api(authed, client):
    upsert_site("lab", name="Lab")
    res = client.get("/api/sites")
    assert res.status_code == 200
    slugs = [s["slug"] for s in res.json()["sites"]]
    assert "lab" in slugs
