"""Zabbix HTTP agent API."""

from __future__ import annotations

import pytest

from services.api_keys import create_api_key
from services.compliance import STATE_OK
from services.schemas import Device, Inventory
from services.zabbix import device_last_status, list_devices, platform_summary


@pytest.fixture
def api_key(db):
    _, raw = create_api_key(name="zabbix", role="viewer", created_by="admin")
    return raw


def _device_row(name: str, *, critical: bool = False) -> Device:
    return Device(
        name=name,
        ip="10.0.0.1",
        model="routeros",
        group="hex",
        site="hex-dc1",
        critical=critical,
        enabled=True,
    )


@pytest.mark.django_db
def test_zabbix_list_devices_service(monkeypatch):
    monkeypatch.setattr(
        "services.zabbix.load_inventory",
        lambda: Inventory(
            devices=[
                _device_row("router-01"),
                _device_row("switch-01", critical=True),
            ]
        ),
    )
    devices = list_devices()
    assert devices == [
        {
            "id": "router-01",
            "name": "router-01",
            "ip": "10.0.0.1",
            "group": "hex",
            "site": "hex-dc1",
            "critical": "0",
        },
        {
            "id": "switch-01",
            "name": "switch-01",
            "ip": "10.0.0.1",
            "group": "hex",
            "site": "hex-dc1",
            "critical": "1",
        },
    ]


@pytest.mark.django_db
def test_zabbix_last_status_service(monkeypatch):
    monkeypatch.setattr(
        "services.zabbix.device_compliance_item",
        lambda name, **kwargs: {
            "name": name,
            "state": STATE_OK if name == "router-01" else "failed",
            "state_label": "Ошибка бэкапа" if name != "router-01" else "OK",
            "ip": "10.0.0.2",
            "group": "hex",
            "site": "hex-dc1",
            "critical": True,
            "reachability": "online",
            "last_backup_at": None,
        }
        if name in ("router-01", "switch-01")
        else None,
    )
    ok = device_last_status("router-01")
    assert ok["laststatus"] == "OK"
    assert ok["state"] == STATE_OK
    assert ok["critical"] == "1"

    bad = device_last_status("switch-01")
    assert bad["laststatus"] == "Ошибка бэкапа"
    assert bad["state"] == "failed"

    with pytest.raises(LookupError):
        device_last_status("missing")


@pytest.mark.django_db
def test_zabbix_platform_summary(monkeypatch):
    monkeypatch.setattr(
        "services.zabbix.compute_compliance_summary",
        lambda **kwargs: {
            "compliance_pct": 92.5,
            "total_enabled": 100,
            "counts": {STATE_OK: 92, "failed": 3, "unreachable": 5},
            "oxidized_error": "",
            "generated_at": None,
        },
    )
    monkeypatch.setattr(
        "services.database.is_database_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "services.oxidized_client.check_health",
        lambda: {"reachable": True, "engine": "python", "nodes_count": 50},
    )

    class _Worker:
        def queue_depth(self):
            return 4

    class _Manager:
        worker = _Worker()

    monkeypatch.setattr("services.oxidized_engine.get_manager", lambda: _Manager())

    summary = platform_summary()
    assert summary["status"] == "ok"
    assert summary["ready"] is True
    assert summary["compliance_pct"] == 92.5
    assert summary["devices_total"] == 100
    assert summary["oxidized_queue_depth"] == 4
    assert summary["counts"]["failed"] == 3


@pytest.mark.django_db
def test_zabbix_getalldevices_endpoint(client, api_key, monkeypatch):
    monkeypatch.setattr(
        "services.zabbix.load_inventory",
        lambda: Inventory(devices=[_device_row("sw1")]),
    )
    response = client.get("/device/getalldevices", HTTP_AUTHKEY=api_key)
    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == "sw1"
    assert body[0]["group"] == "hex"
    assert body[0]["critical"] == "0"


@pytest.mark.django_db
def test_zabbix_getsummary_endpoint(client, api_key, monkeypatch):
    monkeypatch.setattr(
        "services.zabbix.platform_summary",
        lambda **kwargs: {"status": "ok", "ready": True, "compliance_pct": 99.0},
    )
    response = client.get("/device/getsummary", HTTP_AUTHKEY=api_key)
    assert response.status_code == 200
    assert response.json()["compliance_pct"] == 99.0


@pytest.mark.django_db
def test_zabbix_getlaststatus_endpoint(client, api_key, monkeypatch):
    monkeypatch.setattr(
        "services.zabbix.device_compliance_item",
        lambda name, **kwargs: {
            "name": name,
            "state": "overdue",
            "state_label": "Просрочен бэкап",
            "ip": "10.0.0.9",
            "group": "hex",
            "site": "hex-dc1",
            "critical": False,
            "reachability": "online",
            "last_backup_at": None,
        },
    )
    response = client.get("/device/getlaststatus?id=sw1", HTTP_AUTHKEY=api_key)
    assert response.status_code == 200
    body = response.json()
    assert body["laststatus"] == "Просрочен бэкап"
    assert body["state"] == "overdue"
    assert body["ip"] == "10.0.0.9"


@pytest.mark.django_db
def test_zabbix_auth_required(client):
    assert client.get("/device/getalldevices").status_code == 401
    assert client.get("/device/getsummary").status_code == 401


@pytest.mark.django_db
def test_zabbix_static_auth_key(client, settings, monkeypatch):
    settings.ZABBIX_AUTH_KEY = "zabbix-test-secret"
    settings.ZABBIX_MONITORING_ENABLED = True
    monkeypatch.setattr(
        "services.zabbix.load_inventory",
        lambda: Inventory(devices=[_device_row("gw1")]),
    )
    assert client.get("/device/getalldevices").status_code == 401
    response = client.get("/device/getalldevices", HTTP_AUTHKEY="zabbix-test-secret")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "gw1"


@pytest.mark.django_db
def test_zabbix_gettags_endpoint(client, api_key, monkeypatch):
    monkeypatch.setattr(
        "services.inventory.load_inventory",
        lambda: Inventory(devices=[_device_row("router-01")]),
    )
    monkeypatch.setattr(
        "services.zabbix_client.get_host_tags",
        lambda name, **kw: {
            "name": name,
            "hostid": "42",
            "visible_name": name,
            "host": name,
            "tags": [{"tag": "site", "value": "dc1"}],
            "tags_map": {"site": "dc1"},
        },
    )
    monkeypatch.setattr(
        "services.zabbix_client._get_api_config",
        lambda: ("https://z/api_jsonrpc.php", "tok"),
    )
    response = client.get(
        "/device/gettags?id=router-01",
        HTTP_AUTHKEY=api_key,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tags_map"]["site"] == "dc1"
