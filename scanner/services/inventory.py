import logging
import os
from pathlib import Path

import yaml
from django.conf import settings
from django.db import transaction

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

logger = logging.getLogger(__name__)

DEFAULT_ROUTEROS_SSH_PORT = settings.ROUTEROS_SSH_PORT
OXIDIZED_SOURCE_URL = settings.OXIDIZED_SOURCE_URL
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
        site=getattr(record, "site", "") or "",
        role=getattr(record, "role", "") or "",
        critical=bool(getattr(record, "critical", False)),
        maintenance=bool(getattr(record, "maintenance", False)),
    )


def _model_from_device(device: Device) -> DeviceModel:
    return DeviceModel(
        name=device.name,
        ip=device.ip,
        model=device.model,
        group=device.group,
        enabled=device.enabled,
        ports=device.ports,
        site=device.site or "",
        role=device.role or "",
        critical=device.critical,
        maintenance=device.maintenance,
    )


def _profile_from_model(record: CredentialProfileModel) -> CredentialProfile:
    return CredentialProfile(
        name=record.name,
        group_name=record.group_name,
        username=record.username,
        password=record.password,
        model=getattr(record, "model", "") or "",
    )


def _model_from_profile(profile: CredentialProfile) -> CredentialProfileModel:
    return CredentialProfileModel(
        name=profile.name,
        group_name=profile.group_name,
        username=profile.username,
        password=profile.password,
        model=getattr(profile, "model", "") or "",
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
    from services.database import is_database_available, reset_availability_cache

    if not is_database_available():
        logger.warning(
            "inventory | database unavailable — задайте DATABASE_URL "
            "(по умолчанию sqlite:////data/inventory/scanner.db)"
        )
        return
    try:
        call_command("migrate", interactive=False, verbosity=0, fake_initial=True)
        _migrate_device_ports()
        _seed_if_empty()
        from services.auth import seed_default_admin

        seed_default_admin()
    except Exception as exc:
        logger.exception("inventory | database init failed: %s", exc)
        reset_availability_cache()


def _migrate_device_ports() -> None:
    default_port = _default_ssh_port()
    legacy_ports = {22, 23}
    for record in DeviceModel.objects.all():
        ports = record.ports or []
        if not ports or all(p in legacy_ports for p in ports):
            record.ports = [default_port]
            record.save(update_fields=["ports"])


def _env_credentials() -> tuple[str, str, str, str]:
    from services.scan_settings import get_credentials

    return get_credentials()


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


def mask_inventory_for_role(inventory: Inventory, role: str, user=None) -> Inventory:
    from services.rbac import PERMISSION_VIEW_CREDENTIALS, has_permission

    if user is not None:
        from services.object_scope import filter_inventory_for_user

        inventory = filter_inventory_for_user(user, inventory)

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


def _upsert_device_record(device: Device, *, old_name: str | None = None) -> None:
    """Create or update a device row without delete+insert (avoids unique name races)."""
    DeviceModel.objects.filter(name=device.name).exclude(ip=device.ip).delete()
    record = None
    if old_name:
        record = DeviceModel.objects.filter(name=old_name).first()
    if record is None:
        record = DeviceModel.objects.filter(ip=device.ip).first()
    if record:
        record.name = device.name
        record.ip = device.ip
        record.model = device.model
        record.group = device.group
        record.enabled = device.enabled
        record.ports = device.ports
        record.site = device.site or ""
        record.role = device.role or ""
        record.critical = device.critical
        record.maintenance = device.maintenance
        record.save()
    else:
        _model_from_device(device).save()


def add_device(device: Device) -> Inventory:
    with transaction.atomic():
        _upsert_device_record(device)
    return load_inventory()


def rename_device(old_name: str, device: Device) -> Inventory:
    with transaction.atomic():
        _upsert_device_record(device, old_name=old_name)
    return load_inventory()


def remove_device(name: str) -> Inventory:
    DeviceModel.objects.filter(name=name).delete()
    return load_inventory()


def cleanup_discovered_devices() -> tuple[int, Inventory]:
    """Remove temporary discovery placeholders (discovered-*)."""
    deleted, _ = DeviceModel.objects.filter(name__startswith=DISCOVERED_NAME_PREFIX).delete()
    return deleted, load_inventory()


def bulk_update_devices(
    names: list[str],
    *,
    enabled: bool | None = None,
    maintenance: bool | None = None,
    group: str | None = None,
) -> Inventory:
    if not names:
        raise ValueError("names обязателен")
    if enabled is None and maintenance is None and group is None:
        raise ValueError("Укажите enabled, maintenance и/или group")

    unique_names = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    if not unique_names:
        raise ValueError("names обязателен")

    with transaction.atomic():
        rows = list(DeviceModel.objects.filter(name__in=unique_names))
        found = {row.name for row in rows}
        missing = [n for n in unique_names if n not in found]
        if missing:
            raise ValueError(f"Устройства не найдены: {', '.join(missing[:5])}")

        for row in rows:
            if enabled is not None:
                row.enabled = enabled
            if maintenance is not None:
                row.maintenance = maintenance
            if group is not None:
                row.group = group.strip() or row.group
            row.save()

    return load_inventory()


def update_credential_profile(name: str, creds: CredentialProfileUpdate) -> Inventory:
    profile = CredentialProfileModel.objects.filter(name=name).first()
    if not profile:
        raise ValueError(f"Profile '{name}' not found")
    if creds.group_name and creds.group_name != profile.group_name:
        if CredentialProfileModel.objects.filter(group_name=creds.group_name).exclude(name=name).exists():
            raise ValueError(f"Группа '{creds.group_name}' уже используется")
        profile.group_name = creds.group_name
    profile.username = creds.username
    profile.password = creds.password
    if creds.model:
        profile.model = creds.model.strip()
    profile.save()
    if creds.model:
        from services.oxidized_settings import set_group_model

        set_group_model(profile.group_name, creds.model)
    return load_inventory()


def add_credential_profile(profile: CredentialProfile) -> Inventory:
    name = profile.name.strip()
    group_name = profile.group_name.strip()
    if not name or not group_name:
        raise ValueError("Имя профиля и группа обязательны")
    if CredentialProfileModel.objects.filter(name=name).exists():
        raise ValueError(f"Профиль '{name}' уже существует")
    if CredentialProfileModel.objects.filter(group_name=group_name).exists():
        raise ValueError(f"Группа '{group_name}' уже существует")
    _model_from_profile(
        CredentialProfile(
            name=name,
            group_name=group_name,
            username=profile.username,
            password=profile.password,
            model=getattr(profile, "model", "") or "routeros",
        )
    ).save()
    model = getattr(profile, "model", None) or "routeros"
    if model:
        from services.oxidized_settings import set_group_model

        set_group_model(group_name, model)
    return load_inventory()


def delete_credential_profile(name: str) -> Inventory:
    profile = CredentialProfileModel.objects.filter(name=name).first()
    if not profile:
        raise ValueError(f"Profile '{name}' not found")
    devices_count = DeviceModel.objects.filter(group=profile.group_name).count()
    networks_count = NetworkModel.objects.filter(group_name=profile.group_name).count()
    if devices_count or networks_count:
        raise ValueError(
            f"Группа '{profile.group_name}' используется: "
            f"{devices_count} устройств, {networks_count} подсетей"
        )
    profile.delete()
    return load_inventory()


def list_group_names() -> list[str]:
    groups = set(
        CredentialProfileModel.objects.values_list("group_name", flat=True)
    )
    groups.update(DeviceModel.objects.values_list("group", flat=True))
    groups.update(NetworkModel.objects.values_list("group_name", flat=True))
    return sorted(g for g in groups if g)


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


DISCOVERED_NAME_PREFIX = "discovered-"


def devices_for_oxidized_source() -> list[dict]:
    inventory = load_inventory()
    default_port = _default_ssh_port()
    nodes: list[dict] = []
    for device in inventory.devices:
        if not device.enabled:
            continue
        if device.name.startswith(DISCOVERED_NAME_PREFIX):
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


def update_oxidized_credentials(inventory: Inventory) -> dict[str, str]:
    from django.conf import settings

    config_path = Path(settings.OXIDIZED_CONFIG_PATH)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        try:
            config = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            config = {}
    else:
        config = {}

    ssh_port = _default_ssh_port()

    if inventory.credential_profiles:
        first = inventory.credential_profiles[0]
        config["username"] = first.username
        config["password"] = first.password

    config["model"] = config.get("model", "routeros")
    config["resolve_dns"] = config.get("resolve_dns", True)
    config["interval"] = int(
        config.get("interval") or os.environ.get("OXIDIZED_INTERVAL", "3600")
    )
    config["threads"] = int(
        config.get("threads") or os.environ.get("OXIDIZED_THREADS", "10")
    )
    config["timeout"] = int(
        config.get("timeout") or os.environ.get("OXIDIZED_TIMEOUT", "20")
    )
    config["retries"] = int(
        config.get("retries") or os.environ.get("OXIDIZED_RETRIES", "3")
    )
    engine = getattr(settings, "OXIDIZED_ENGINE", "python").lower()
    if engine == "python":
        # Python engine logs via oxidized_logging.py; keep Ruby/config readers off the volume log.
        config["log"] = "/dev/null"
    else:
        config["log"] = getattr(
            settings, "OXIDIZED_LOG_PATH", "/var/lib/oxidized/oxidized.log"
        )
    config["input"] = {
        "default": "ssh",
        "ssh": {"secure": False, "port": ssh_port},
    }

    from services.git_settings import get_config as get_git_config

    git_cfg = get_git_config()

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
    if git_cfg.oxidized_source_token:
        http_source["headers"]["X-Auth-Token"] = git_cfg.oxidized_source_token

    config["source"] = {"default": "http", "debug": False, "http": http_source}

    existing_groups = config.get("groups") or {}
    default_model = config.get("model", "routeros")
    groups: dict = {}
    for profile in inventory.credential_profiles:
        prev = existing_groups.get(profile.group_name) or {}
        groups[profile.group_name] = {
            "username": profile.username,
            "password": profile.password,
            "model": prev.get("model") or default_model,
        }
    if groups:
        config["groups"] = groups

    if engine == "python":
        config.pop("rest", None)
        extensions = config.get("extensions")
        if isinstance(extensions, dict):
            extensions.pop("oxidized-web", None)
            if not extensions:
                config.pop("extensions", None)
    else:
        config.setdefault("rest", "0.0.0.0:8888")

    config["output"] = {
        "default": "git",
        "git": {
            "user": git_cfg.git_commit_user,
            "email": git_cfg.git_commit_email,
            "repo": "/var/lib/oxidized",
            "single_repo": True,
            "single_branch": True,
            "single_branch_name": git_cfg.git_branch,
        },
    }

    if git_cfg.git_remote_url:
        if engine == "python":
            # Python HookRunner pushes via subprocess with token from DB (not Rugged).
            config.pop("hooks", None)
        else:
            push_hook: dict = {
                "type": "githubrepo",
                "events": ["post_store"],
                "remote_repo": git_cfg.git_remote_url,
            }
            if git_cfg.gitea_token:
                push_hook["username"] = git_cfg.gitea_http_user
                push_hook["password"] = git_cfg.gitea_token
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

    from services.oxidized_reload import apply_engine_reload

    return apply_engine_reload()


from asgiref.sync import sync_to_async

load_inventory_async = sync_to_async(load_inventory, thread_sensitive=True)
add_device_async = sync_to_async(add_device, thread_sensitive=True)
rename_device_async = sync_to_async(rename_device, thread_sensitive=True)
