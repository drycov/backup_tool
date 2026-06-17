import os
from pathlib import Path

import yaml
from django.conf import settings

from core.models import CredentialProfile as CredentialProfileModel
from core.models import Device as DeviceModel
from core.models import Network as NetworkModel
from services.network_importer import import_network_inventory
from services.schemas import (
    CredentialProfile,
    CredentialProfileUpdate,
    Device,
    Inventory,
    NetworkEntry,
)

DEFAULT_ROUTEROS_SSH_PORT = settings.ROUTEROS_SSH_PORT
OXIDIZED_SOURCE_URL = settings.OXIDIZED_SOURCE_URL
OXIDIZED_SOURCE_TOKEN = settings.OXIDIZED_SOURCE_TOKEN
GIT_REMOTE_URL = settings.GIT_REMOTE_URL
GITEA_TOKEN = settings.GITEA_TOKEN
GITEA_HTTP_USER = settings.GITEA_HTTP_USER
GIT_SSH_PRIVATE_KEY = os.environ.get(
    "GIT_SSH_PRIVATE_KEY", "/home/oxidized/.ssh/id_rsa"
)
GIT_SSH_PUBLIC_KEY = os.environ.get(
    "GIT_SSH_PUBLIC_KEY", "/home/oxidized/.ssh/id_rsa.pub"
)


def _router_db_path() -> Path:
    return Path(settings.ROUTER_DB_PATH)


def _default_ssh_port() -> int:
    return DEFAULT_ROUTEROS_SSH_PORT


def _device_from_model(record: DeviceModel) -> Device:
    return Device(
        name=record.name,
        ip=record.ip,
        model=record.model,
        group=record.group,
        enabled=record.enabled,
        ports=record.ports or [_default_ssh_port()],
    )


def _model_from_device(device: Device) -> DeviceModel:
    return DeviceModel(
        name=device.name,
        ip=device.ip,
        model=device.model,
        group=device.group,
        enabled=device.enabled,
        ports=device.ports,
    )


def _profile_from_model(record: CredentialProfileModel) -> CredentialProfile:
    return CredentialProfile(
        name=record.name,
        group_name=record.group_name,
        username=record.username,
        password=record.password,
    )


def _model_from_profile(profile: CredentialProfile) -> CredentialProfileModel:
    return CredentialProfileModel(
        name=profile.name,
        group_name=profile.group_name,
        username=profile.username,
        password=profile.password,
    )


def _network_from_model(record: NetworkModel) -> NetworkEntry:
    return NetworkEntry(
        network=record.network,
        group_name=record.group_name,
        environment_name=record.environment_name,
        gateway=record.gateway,
    )


def init_db() -> None:
    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0, fake_initial=True)
    _migrate_device_ports()
    _seed_if_empty()
    from services.auth import seed_default_admin

    seed_default_admin()


def _migrate_device_ports() -> None:
    default_port = _default_ssh_port()
    legacy_ports = {22, 23}
    for record in DeviceModel.objects.all():
        ports = record.ports or []
        if not ports or all(p in legacy_ports for p in ports):
            record.ports = [default_port]
            record.save(update_fields=["ports"])


def _env_credentials() -> tuple[str, str, str, str]:
    return settings.OVN_USER, settings.OVN_PASS, settings.US_USER, settings.US_PASS


def _seed_if_empty() -> None:
    if DeviceModel.objects.exists() or NetworkModel.objects.exists():
        return

    network_path = Path(settings.NETWORK_INVENTORY_PATH)
    if network_path.exists():
        ovn_user, ovn_pass, us_user, us_pass = _env_credentials()
        inventory = import_network_inventory(
            network_path, ovn_user, ovn_pass, us_user, us_pass
        )
        _save_inventory_to_db(inventory)
        return

    legacy_path = Path(settings.INVENTORY_PATH)
    if legacy_path.exists():
        with open(legacy_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _save_legacy_yaml(data)


def _save_legacy_yaml(data: dict) -> None:
    creds = data.get("credentials") or {}
    if creds:
        CredentialProfileModel.objects.create(
            name="default",
            group_name="default",
            username=creds.get("username", "admin"),
            password=creds.get("password", "changeme"),
        )
    for net in data.get("networks") or []:
        NetworkModel.objects.create(network=net, group_name="default")
    for d in data.get("devices") or []:
        DeviceModel.objects.create(
            name=d["name"],
            ip=d["ip"],
            model=d.get("model", "routeros"),
            group=d.get("group", "default"),
            enabled=d.get("enabled", True),
            ports=d.get("ports", [_default_ssh_port()]),
        )


def _save_inventory_to_db(inventory: Inventory) -> None:
    CredentialProfileModel.objects.all().delete()
    NetworkModel.objects.all().delete()
    DeviceModel.objects.all().delete()

    CredentialProfileModel.objects.bulk_create(
        [_model_from_profile(p) for p in inventory.credential_profiles]
    )
    NetworkModel.objects.bulk_create(
        [
            NetworkModel(
                network=net.network,
                group_name=net.group_name,
                environment_name=net.environment_name,
                gateway=net.gateway,
            )
            for net in inventory.networks
        ]
    )
    DeviceModel.objects.bulk_create(
        [_model_from_device(d) for d in inventory.devices]
    )


def load_inventory() -> Inventory:
    profiles = [
        _profile_from_model(p)
        for p in CredentialProfileModel.objects.order_by("id")
    ]
    networks = [
        _network_from_model(n) for n in NetworkModel.objects.order_by("id")
    ]
    devices = [
        _device_from_model(d) for d in DeviceModel.objects.order_by("id")
    ]
    return Inventory(
        credential_profiles=profiles,
        networks=networks,
        devices=devices,
    )


def mask_inventory_for_role(inventory: Inventory, role: str) -> Inventory:
    from services.rbac import PERMISSION_VIEW_CREDENTIALS, has_permission

    if has_permission(role, PERMISSION_VIEW_CREDENTIALS):
        return inventory
    masked_profiles = [
        CredentialProfile(
            name=p.name,
            group_name=p.group_name,
            username=p.username,
            password="********",
        )
        for p in inventory.credential_profiles
    ]
    return Inventory(
        credential_profiles=masked_profiles,
        networks=inventory.networks,
        devices=inventory.devices,
    )


def save_inventory(inventory: Inventory) -> None:
    _save_inventory_to_db(inventory)


def add_device(device: Device) -> Inventory:
    DeviceModel.objects.filter(name=device.name).delete()
    DeviceModel.objects.filter(ip=device.ip).delete()
    _model_from_device(device).save()
    return load_inventory()


def rename_device(old_name: str, device: Device) -> Inventory:
    DeviceModel.objects.filter(name=old_name).delete()
    DeviceModel.objects.filter(name=device.name).exclude(name=old_name).delete()
    _model_from_device(device).save()
    return load_inventory()


def remove_device(name: str) -> Inventory:
    DeviceModel.objects.filter(name=name).delete()
    return load_inventory()


def update_credential_profile(name: str, creds: CredentialProfileUpdate) -> Inventory:
    profile = CredentialProfileModel.objects.filter(name=name).first()
    if not profile:
        raise ValueError(f"Profile '{name}' not found")
    profile.username = creds.username
    profile.password = creds.password
    profile.save(update_fields=["username", "password"])
    return load_inventory()


def reimport_network_inventory() -> Inventory:
    path = Path(settings.NETWORK_INVENTORY_PATH)
    if not path.exists():
        raise FileNotFoundError(f"network_inventory not found: {path}")

    ovn_user, ovn_pass, us_user, us_pass = _env_credentials()
    inventory = import_network_inventory(
        path, ovn_user, ovn_pass, us_user, us_pass
    )
    save_inventory(inventory)
    return inventory


def devices_for_oxidized_source() -> list[dict]:
    inventory = load_inventory()
    default_port = _default_ssh_port()
    nodes: list[dict] = []
    for device in inventory.devices:
        if not device.enabled:
            continue
        port = device.ports[0] if device.ports else default_port
        nodes.append(
            {
                "hostname": device.name,
                "ip": device.ip,
                "os": device.model,
                "group": device.group,
                "ssh_port": port,
            }
        )
    return nodes


def update_oxidized_credentials(inventory: Inventory) -> None:
    config_path = Path(settings.OXIDIZED_CONFIG_PATH)
    if not config_path.exists():
        return

    raw = config_path.read_text(encoding="utf-8")
    try:
        config = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        config = {}

    ssh_port = _default_ssh_port()

    if inventory.credential_profiles:
        first = inventory.credential_profiles[0]
        config["username"] = first.username
        config["password"] = first.password

    config["model"] = config.get("model", "routeros")
    config["input"] = {
        "default": "ssh",
        "ssh": {"secure": False, "port": ssh_port},
    }

    http_source: dict = {
        "url": OXIDIZED_SOURCE_URL,
        "map": {
            "name": "hostname",
            "model": "os",
            "group": "group",
            "ip": "ip",
        },
        "vars_map": {"ssh_port": "ssh_port"},
        "headers": {"Accept": "application/json"},
    }
    if OXIDIZED_SOURCE_TOKEN:
        http_source["headers"]["X-Auth-Token"] = OXIDIZED_SOURCE_TOKEN

    config["source"] = {"default": "http", "debug": False, "http": http_source}

    groups: dict = {}
    for profile in inventory.credential_profiles:
        groups[profile.group_name] = {
            "username": profile.username,
            "password": profile.password,
            "model": "routeros",
        }
    if groups:
        config["groups"] = groups

    config["output"] = {
        "default": "git",
        "git": {
            "user": os.environ.get("GIT_COMMIT_USER", "Oxidized"),
            "email": os.environ.get("GIT_COMMIT_EMAIL", "oxidized@localhost"),
            "repo": "/var/lib/oxidized",
            "single_repo": True,
            "single_branch": True,
            "single_branch_name": os.environ.get("GIT_BRANCH", "main"),
        },
    }

    if GIT_REMOTE_URL:
        push_hook: dict = {
            "type": "githubrepo",
            "events": ["post_store"],
            "remote_repo": GIT_REMOTE_URL,
        }
        if GITEA_TOKEN:
            push_hook["username"] = GITEA_HTTP_USER
            push_hook["password"] = ""
        else:
            push_hook["privatekey"] = GIT_SSH_PRIVATE_KEY
            push_hook["publickey"] = GIT_SSH_PUBLIC_KEY
        config["hooks"] = {"push_to_git": push_hook}
    else:
        config.pop("hooks", None)

    config_path.write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
