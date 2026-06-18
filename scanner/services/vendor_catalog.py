"""Каталог вендоров / Oxidized-моделей: порты, алиасы, аудит, возможности бэкапа."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VendorModelInfo:
    """Метаданные модели Oxidized для UI, discovery и аудита."""

    id: str
    label: str
    vendor: str
    default_ports: tuple[int, ...]
    aliases: frozenset[str]
    native_python: bool = False
    mikrotik_binary: bool = False
    audit_profile: str = "generic"


def _info(
    model_id: str,
    label: str,
    vendor: str,
    ports: tuple[int, ...],
    *,
    aliases: tuple[str, ...] = (),
    native_python: bool = False,
    mikrotik_binary: bool = False,
    audit_profile: str | None = None,
) -> VendorModelInfo:
    audit = audit_profile or model_id
    all_aliases = frozenset({model_id, *aliases})
    return VendorModelInfo(
        id=model_id,
        label=label,
        vendor=vendor,
        default_ports=ports,
        aliases=all_aliases,
        native_python=native_python,
        mikrotik_binary=mikrotik_binary,
        audit_profile=audit,
    )


# Канонические модели: id = Oxidized model name
_VENDOR_MODELS: tuple[VendorModelInfo, ...] = (
    _info(
        "routeros",
        "RouterOS (MikroTik)",
        "MikroTik",
        (44333, 22),
        aliases=("mikrotik", "ros"),
        native_python=True,
        mikrotik_binary=True,
        audit_profile="routeros",
    ),
    _info(
        "ios",
        "Cisco IOS",
        "Cisco",
        (22,),
        aliases=("cisco",),
        native_python=True,
        audit_profile="ios",
    ),
    _info(
        "iosxe",
        "Cisco IOS-XE",
        "Cisco",
        (22,),
        aliases=("ios-xe",),
        audit_profile="ios",
    ),
    _info(
        "iosxr",
        "Cisco IOS-XR",
        "Cisco",
        (22,),
        aliases=("ios-xr",),
        audit_profile="ios",
    ),
    _info(
        "nxos",
        "Cisco NX-OS",
        "Cisco",
        (22,),
        aliases=("nx-os", "nexus"),
        audit_profile="ios",
    ),
    _info(
        "junos",
        "Juniper JunOS",
        "Juniper",
        (22,),
        aliases=("juniper",),
        native_python=True,
        audit_profile="junos",
    ),
    _info(
        "eos",
        "Arista EOS",
        "Arista",
        (22,),
        aliases=("arista",),
        native_python=True,
        audit_profile="eos",
    ),
    _info("fortios", "FortiOS", "Fortinet", (22,), aliases=("fortinet",)),
    _info("panos", "Palo Alto PAN-OS", "Palo Alto", (22,), aliases=("paloalto", "pan-os")),
    _info("ironware", "Brocade IronWare", "Brocade", (22,), aliases=("brocade",)),
    _info("procurve", "HP ProCurve", "HPE", (22,), aliases=("hp",)),
    _info("openwrt", "OpenWrt", "OpenWrt", (22,)),
    _info("vyos", "VyOS", "VyOS", (22,)),
    _info("linux", "Linux", "Generic", (22,)),
    _info("asa", "Cisco ASA", "Cisco", (22,), audit_profile="ios"),
)


def _alias_key(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("_", "-")


_ALIAS_INDEX: dict[str, str] = {}
for _entry in _VENDOR_MODELS:
    for alias in _entry.aliases:
        _ALIAS_INDEX[_alias_key(alias)] = _entry.id

_ID_INDEX: dict[str, VendorModelInfo] = {e.id: e for e in _VENDOR_MODELS}


def normalize_model(name: str | None, *, default: str = "routeros") -> str:
    """Привести произвольное имя модели к каноническому Oxidized id."""
    if not name or not str(name).strip():
        return default
    key = _alias_key(str(name))
    if key in _ID_INDEX:
        return key
    if key in _ALIAS_INDEX:
        return _ALIAS_INDEX[key]
    return key.replace("-", "")


def get_model_info(name: str | None) -> VendorModelInfo:
    model_id = normalize_model(name)
    if model_id in _ID_INDEX:
        return _ID_INDEX[model_id]
    return VendorModelInfo(
        id=model_id,
        label=model_id,
        vendor="Unknown",
        default_ports=(22,),
        aliases=frozenset({model_id}),
    )


def model_label(name: str | None) -> str:
    return get_model_info(name).label


def default_ports_for_model(name: str | None) -> list[int]:
    return list(get_model_info(name).default_ports)


def supports_mikrotik_binary(name: str | None) -> bool:
    return get_model_info(name).mikrotik_binary


def audit_profile_for_model(name: str | None) -> str:
    return get_model_info(name).audit_profile


def is_routeros_family(name: str | None) -> bool:
    return normalize_model(name) == "routeros"


def catalog_public() -> dict[str, dict[str, Any]]:
    """Публичные метаданные для UI/API."""
    return {
        entry.id: {
            "id": entry.id,
            "label": entry.label,
            "vendor": entry.vendor,
            "default_ports": list(entry.default_ports),
            "native_python": entry.native_python,
            "mikrotik_binary": entry.mikrotik_binary,
            "audit_profile": entry.audit_profile,
        }
        for entry in _VENDOR_MODELS
    }


def catalog_entry_public(name: str | None) -> dict[str, Any]:
    entry = get_model_info(name)
    return {
        "id": entry.id,
        "label": entry.label,
        "vendor": entry.vendor,
        "default_ports": list(entry.default_ports),
        "native_python": entry.native_python,
        "mikrotik_binary": entry.mikrotik_binary,
        "audit_profile": entry.audit_profile,
    }


def discovery_probe_plans(
    default_model: str,
    *,
    ssh_port_override: int | None = None,
) -> list[tuple[int, str]]:
    """Порты и модели для первичного discovery (по настройкам Oxidized)."""
    model = normalize_model(default_model)
    info = get_model_info(model)
    ports: list[int] = []
    if ssh_port_override:
        ports.append(int(ssh_port_override))
    for port in info.default_ports:
        if port not in ports:
            ports.append(port)
    return [(port, model) for port in ports]


def fallback_discovery_plans() -> list[tuple[int, str]]:
    """Резервные комбинации порт/модель для мультивендорного discovery."""
    seen: set[tuple[int, str]] = set()
    plans: list[tuple[int, str]] = []
    for entry in _VENDOR_MODELS:
        if not entry.native_python:
            continue
        for port in entry.default_ports:
            key = (port, entry.id)
            if key in seen:
                continue
            seen.add(key)
            plans.append(key)
    return plans
