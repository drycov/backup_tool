import os
from pathlib import Path

import yaml

from .db import (
    Base,
    CredentialProfile as CredentialProfileRecord,
    Network,
    DeviceRecord,
    engine,
    get_session,
)
from .models import (
    Inventory,
    Device,
    CredentialProfile,
    NetworkEntry,
    CredentialProfileUpdate,
)
from .network_importer import import_network_inventory

DEFAULT_INVENTORY_PATH = os.environ.get(
    "INVENTORY_PATH", "/data/inventory/inventory.yaml"
)
DEFAULT_NETWORK_INVENTORY_PATH = os.environ.get(
    "NETWORK_INVENTORY_PATH", "/data/inventory/network_inventory.yml"
)
DEFAULT_ROUTER_DB_PATH = os.environ.get(
    "ROUTER_DB_PATH", "/data/oxidized/router.db"
)
DEFAULT_ROUTEROS_SSH_PORT = int(os.environ.get("ROUTEROS_SSH_PORT", "44333"))
OXIDIZED_SOURCE_URL = os.environ.get(
    "OXIDIZED_SOURCE_URL",
    os.environ.get(
        "LIBRENMS_OXIDIZED_URL",
        "http://scanner:8000/api/oxidized/source",
    ),
)
OXIDIZED_SOURCE_TOKEN = os.environ.get(
    "OXIDIZED_SOURCE_TOKEN", os.environ.get("LIBRENMS_API_TOKEN", "")
)
GIT_REMOTE_URL = os.environ.get("GIT_REMOTE_URL", "")
GIT_SSH_PRIVATE_KEY = os.environ.get(
    "GIT_SSH_PRIVATE_KEY", "/home/oxidized/.ssh/id_rsa"
)
GIT_SSH_PUBLIC_KEY = os.environ.get(
    "GIT_SSH_PUBLIC_KEY", "/home/oxidized/.ssh/id_rsa.pub"
)


def _router_db_path() -> Path:
    return Path(DEFAULT_ROUTER_DB_PATH)


def _default_ssh_port() -> int:
    return DEFAULT_ROUTEROS_SSH_PORT


def _device_ssh_port(device: Device) -> int:
    return device.ports[0] if device.ports else _default_ssh_port()


def _device_from_record(record: DeviceRecord) -> Device:
    return Device(
        name=record.name,
        ip=record.ip,
        model=record.model,
        group=record.group,
        enabled=record.enabled,
        ports=record.ports or [_default_ssh_port()],
    )


def _record_from_device(device: Device) -> DeviceRecord:
    return DeviceRecord(
        name=device.name,
        ip=device.ip,
        model=device.model,
        group=device.group,
        enabled=device.enabled,
        ports=device.ports,
    )


def _profile_from_record(record: CredentialProfileRecord) -> CredentialProfile:
    return CredentialProfile(
        name=record.name,
        group_name=record.group_name,
        username=record.username,
        password=record.password,
    )


def _record_from_profile(profile: CredentialProfile) -> CredentialProfileRecord:
    return CredentialProfileRecord(
        name=profile.name,
        group_name=profile.group_name,
        username=profile.username,
        password=profile.password,
    )


def _network_from_record(record: Network) -> NetworkEntry:
    return NetworkEntry(
        network=record.network,
        group_name=record.group_name,
        environment_name=record.environment_name,
        gateway=record.gateway,
    )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    _migrate_device_ports()
    _seed_if_empty()
    from .auth import seed_default_admin

    seed_default_admin()


def _migrate_schema() -> None:
    from sqlalchemy import text

    statements = [
        "ALTER TABLE networks ADD COLUMN IF NOT EXISTS group_name VARCHAR(64) DEFAULT 'default'",
        "ALTER TABLE networks ADD COLUMN IF NOT EXISTS environment_name VARCHAR(128)",
        "ALTER TABLE networks ADD COLUMN IF NOT EXISTS gateway VARCHAR(64)",
    ]
    with engine.connect() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.commit()


def _migrate_device_ports() -> None:
    """Обновить устройства с legacy-портом 22 на ROUTEROS_SSH_PORT."""
    default_port = _default_ssh_port()
    legacy_ports = {22, 23}
    with get_session() as session:
        for record in session.query(DeviceRecord).all():
            ports = record.ports or []
            if not ports or all(p in legacy_ports for p in ports):
                record.ports = [default_port]
        session.commit()


def _env_credentials() -> tuple[str, str, str, str]:
    ovn_user = os.environ.get("OVN_USER", "satcoadm")
    ovn_pass = os.environ.get("OVN_PASS", "")
    us_user = os.environ.get("US_USER", "satcoadm")
    us_pass = os.environ.get("US_PASS", "")
    return ovn_user, ovn_pass, us_user, us_pass


def _seed_if_empty() -> None:
    with get_session() as session:
        has_data = (
            session.query(DeviceRecord).count() > 0
            or session.query(Network).count() > 0
        )
        if has_data:
            return

        network_path = Path(DEFAULT_NETWORK_INVENTORY_PATH)
        if network_path.exists():
            ovn_user, ovn_pass, us_user, us_pass = _env_credentials()
            inventory = import_network_inventory(
                network_path, ovn_user, ovn_pass, us_user, us_pass
            )
            _save_inventory_to_db(session, inventory)
            session.commit()
            return

        legacy_path = Path(DEFAULT_INVENTORY_PATH)
        if legacy_path.exists():
            with open(legacy_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            _save_legacy_yaml(session, data)
            session.commit()


def _save_legacy_yaml(session, data: dict) -> None:
    creds = data.get("credentials") or {}
    if creds:
        session.add(
            CredentialProfileRecord(
                name="default",
                group_name="default",
                username=creds.get("username", "admin"),
                password=creds.get("password", "changeme"),
            )
        )
    for net in data.get("networks") or []:
        session.add(Network(network=net, group_name="default"))
    for d in data.get("devices") or []:
        session.add(
            DeviceRecord(
                name=d["name"],
                ip=d["ip"],
                model=d.get("model", "routeros"),
                group=d.get("group", "default"),
                enabled=d.get("enabled", True),
                ports=d.get("ports", [_default_ssh_port()]),
            )
        )


def _save_inventory_to_db(session, inventory: Inventory) -> None:
    session.query(CredentialProfileRecord).delete()
    session.query(Network).delete()
    session.query(DeviceRecord).delete()

    for profile in inventory.credential_profiles:
        session.add(_record_from_profile(profile))

    for net in inventory.networks:
        session.add(
            Network(
                network=net.network,
                group_name=net.group_name,
                environment_name=net.environment_name,
                gateway=net.gateway,
            )
        )

    for device in inventory.devices:
        session.add(_record_from_device(device))


def load_inventory() -> Inventory:
    with get_session() as session:
        profiles = [
            _profile_from_record(p)
            for p in session.query(CredentialProfileRecord).order_by(
                CredentialProfileRecord.id
            )
        ]
        networks = [
            _network_from_record(n)
            for n in session.query(Network).order_by(Network.id)
        ]
        devices = [
            _device_from_record(d)
            for d in session.query(DeviceRecord).order_by(DeviceRecord.id)
        ]
        session.commit()

        return Inventory(
            credential_profiles=profiles,
            networks=networks,
            devices=devices,
        )


def mask_inventory_for_role(inventory: Inventory, role: str) -> Inventory:
    from .auth import PERMISSION_VIEW_CREDENTIALS, has_permission

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
    with get_session() as session:
        _save_inventory_to_db(session, inventory)
        session.commit()


def add_device(device: Device) -> Inventory:
    with get_session() as session:
        existing = session.query(DeviceRecord).filter_by(name=device.name).first()
        if existing:
            session.delete(existing)
            session.flush()
        by_ip = session.query(DeviceRecord).filter_by(ip=device.ip).first()
        if by_ip:
            session.delete(by_ip)
            session.flush()
        session.add(_record_from_device(device))
        session.commit()
    return load_inventory()


def rename_device(old_name: str, device: Device) -> Inventory:
    with get_session() as session:
        record = session.query(DeviceRecord).filter_by(name=old_name).first()
        if record:
            session.delete(record)
            session.flush()
        conflict = session.query(DeviceRecord).filter_by(name=device.name).first()
        if conflict:
            session.delete(conflict)
            session.flush()
        session.add(_record_from_device(device))
        session.commit()
    return load_inventory()


def remove_device(name: str) -> Inventory:
    with get_session() as session:
        record = session.query(DeviceRecord).filter_by(name=name).first()
        if record:
            session.delete(record)
            session.commit()
    return load_inventory()


def update_credential_profile(name: str, creds: CredentialProfileUpdate) -> Inventory:
    with get_session() as session:
        profile = session.query(CredentialProfileRecord).filter_by(name=name).first()
        if not profile:
            raise ValueError(f"Profile '{name}' not found")
        profile.username = creds.username
        profile.password = creds.password
        session.commit()
    return load_inventory()


def reimport_network_inventory() -> Inventory:
    path = Path(DEFAULT_NETWORK_INVENTORY_PATH)
    if not path.exists():
        raise FileNotFoundError(f"network_inventory not found: {path}")

    ovn_user, ovn_pass, us_user, us_pass = _env_credentials()
    inventory = import_network_inventory(
        path, ovn_user, ovn_pass, us_user, us_pass
    )
    save_inventory(inventory)
    return inventory


def get_networks_for_discovery() -> list[str]:
    inventory = load_inventory()
    return [n.network for n in inventory.networks]


def get_group_for_ip(ip: str) -> str:
    import ipaddress

    inventory = load_inventory()
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "default"

    for net in inventory.networks:
        try:
            if addr in ipaddress.ip_network(net.network, strict=False):
                return net.group_name
        except ValueError:
            continue
    return "default"


def generate_router_db(inventory: Inventory, scan_results: list | None = None) -> str:
    online_ips: set[str] = set()
    if scan_results:
        from .models import ScanStatus

        for result in scan_results:
            if result.status in (ScanStatus.ONLINE, ScanStatus.PARTIAL):
                online_ips.add(result.ip)

    lines: list[str] = []
    for device in inventory.devices:
        if not device.enabled:
            continue
        if scan_results and device.ip not in online_ips:
            continue
        port = _device_ssh_port(device)
        lines.append(f"{device.name}:{device.ip}:{device.model}:{device.group}:{port}")

    content = "\n".join(lines) + ("\n" if lines else "")

    router_path = _router_db_path()
    router_path.parent.mkdir(parents=True, exist_ok=True)
    router_path.write_text(content, encoding="utf-8")

    return content


def devices_for_oxidized_source() -> list[dict]:
    """Список узлов в формате LibreNMS /api/v0/oxidized для HTTP source Oxidized."""
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
    config_path = Path(
        os.environ.get("OXIDIZED_CONFIG_PATH", "/data/oxidized/config")
    )
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
        "ssh": {
            "secure": False,
            "port": ssh_port,
        },
    }

    http_source: dict = {
        "url": OXIDIZED_SOURCE_URL,
        "map": {
            "name": "hostname",
            "model": "os",
            "group": "group",
            "ip": "ip",
        },
        "vars_map": {
            "ssh_port": "ssh_port",
        },
        "headers": {
            "Accept": "application/json",
        },
    }
    if OXIDIZED_SOURCE_TOKEN:
        http_source["headers"]["X-Auth-Token"] = OXIDIZED_SOURCE_TOKEN

    config["source"] = {
        "default": "http",
        "debug": False,
        "http": http_source,
    }

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
        config["hooks"] = {
            "push_to_git": {
                "type": "githubrepo",
                "events": ["post_store"],
                "remote_repo": GIT_REMOTE_URL,
                "privatekey": GIT_SSH_PRIVATE_KEY,
                "publickey": GIT_SSH_PUBLIC_KEY,
            }
        }
    else:
        config.pop("hooks", None)

    config_path.write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def import_network_inventory_file() -> Inventory:
    return reimport_network_inventory()
