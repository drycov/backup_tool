"""Импорт environments из network_inventory.yml."""

import ipaddress
from pathlib import Path
from typing import Any

import yaml

from .models import CredentialProfile, Device, Inventory, NetworkEntry

# hex → OVN_PASS, us → US_PASS
ENV_CREDENTIAL_MAP = {
    "hex": "ovn",
    "us": "us",
}


def _parse_environments(data: dict[str, Any]) -> list[dict[str, Any]]:
    environments = data.get("environments") or {}
    items: list[dict[str, Any]] = []

    for env_type, env_list in environments.items():
        if not isinstance(env_list, list):
            continue
        for entry in env_list:
            if not isinstance(entry, dict):
                continue
            items.append({**entry, "_env_type": env_type})

    return items


def import_network_inventory(
    path: Path,
    ovn_username: str,
    ovn_password: str,
    us_username: str,
    us_password: str,
) -> Inventory:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    profiles = [
        CredentialProfile(
            name="ovn",
            group_name="hex",
            username=ovn_username,
            password=ovn_password,
        ),
        CredentialProfile(
            name="us",
            group_name="us",
            username=us_username,
            password=us_password,
        ),
    ]

    networks: list[NetworkEntry] = []
    devices: list[Device] = []
    seen_device_names: set[str] = set()

    for entry in _parse_environments(data):
        env_type = entry.get("_env_type", "default")
        env_name = entry.get("name", "")
        group_name = env_type

        for net in entry.get("networks") or []:
            if not isinstance(net, dict):
                continue
            subnet = net.get("subnet")
            if not subnet:
                continue
            gateway = net.get("gateway")
            networks.append(
                NetworkEntry(
                    network=subnet,
                    group_name=group_name,
                    environment_name=env_name,
                    gateway=gateway,
                )
            )
            if gateway and env_name and env_name not in seen_device_names:
                seen_device_names.add(env_name)
                devices.append(
                    Device(
                        name=env_name,
                        ip=gateway,
                        model="routeros",
                        group=group_name,
                        enabled=True,
                        ports=[44333],
                    )
                )
            elif not gateway and env_name and env_name not in seen_device_names:
                try:
                    iface = ipaddress.ip_interface(subnet)
                    if iface.network.prefixlen >= 30:
                        host_ip = str(iface.ip)
                        seen_device_names.add(env_name)
                        devices.append(
                            Device(
                                name=env_name,
                                ip=host_ip,
                                model="routeros",
                                group=group_name,
                                enabled=True,
                                ports=[44333],
                            )
                        )
                except ValueError:
                    pass

    return Inventory(
        credential_profiles=profiles,
        networks=networks,
        devices=devices,
    )
