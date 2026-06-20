"""Тесты Zabbix API client (теги хоста)."""

from __future__ import annotations

import pytest

from services.zabbix import device_tags
from services.zabbix_client import (
    ZabbixNotConfigured,
    get_host_tags,
    tags_list_to_map,
)


def test_tags_list_to_map():
    assert tags_list_to_map([{"tag": "site", "value": "dc1"}, {"tag": "role", "value": "core"}]) == {
        "site": "dc1",
        "role": "core",
    }


@pytest.mark.django_db
def test_get_host_tags_not_configured(monkeypatch):
    monkeypatch.setattr(
        "services.zabbix_client._get_api_config",
        lambda: (_ for _ in ()).throw(ZabbixNotConfigured("no config")),
    )
    with pytest.raises(ZabbixNotConfigured):
        get_host_tags("router-01")


@pytest.mark.django_db
def test_get_host_tags_by_name(monkeypatch):
    calls = []

    def fake_rpc(method, params=None, *, auth=None):
        calls.append((method, params))
        if method == "host.get":
            filt = (params or {}).get("filter") or {}
            if filt.get("name") == "router-01":
                return [
                    {
                        "hostid": "10001",
                        "name": "router-01",
                        "host": "router-01.local",
                        "tags": [{"tag": "site", "value": "hex-dc1"}, {"tag": "env", "value": "prod"}],
                    }
                ]
        return []

    monkeypatch.setattr("services.zabbix_client._get_api_config", lambda: ("https://z/api_jsonrpc.php", "tok"))
    monkeypatch.setattr("services.zabbix_client._rpc", fake_rpc)

    result = get_host_tags("router-01", use_cache=False)
    assert result["hostid"] == "10001"
    assert result["tags_map"]["site"] == "hex-dc1"
    assert result["tags_map"]["env"] == "prod"
    assert calls[0][0] == "host.get"


@pytest.mark.django_db
def test_device_tags_service(monkeypatch):
    from services.schemas import Device, Inventory

    monkeypatch.setattr(
        "services.inventory.load_inventory",
        lambda: Inventory(devices=[Device(name="router-01", ip="10.0.0.1", model="routeros", group="hex")]),
    )
    monkeypatch.setattr(
        "services.zabbix_client.get_host_tags",
        lambda name, **kw: {
            "name": name,
            "hostid": "1",
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

    result = device_tags("router-01")
    assert result["id"] == "router-01"
    assert result["tags_map"]["site"] == "dc1"
