"""Object-level RBAC: ограничение видимости по site/group для operator/viewer."""

from __future__ import annotations

from typing import Iterable, TypeVar

from core.models import User
from services.rbac import ROLE_ADMIN
from services.schemas import Device, Inventory

T = TypeVar("T")


def _scope_lists(user: User) -> tuple[list[str], list[str]]:
    groups = list(getattr(user, "allowed_groups", None) or [])
    sites = list(getattr(user, "allowed_sites", None) or [])
    return [g.strip() for g in groups if str(g).strip()], [s.strip() for s in sites if str(s).strip()]


def has_object_scope(user: User) -> bool:
    """User has explicit site/group restrictions."""
    if user.role == ROLE_ADMIN:
        return False
    groups, sites = _scope_lists(user)
    return bool(groups or sites)


def device_in_scope(user: User, device: Device) -> bool:
    if user.role == ROLE_ADMIN:
        return True
    groups, sites = _scope_lists(user)
    if not groups and not sites:
        return True
    if groups and (device.group or "") not in groups:
        return False
    if sites and (device.site or "") not in sites:
        return False
    return True


def filter_devices(user: User, devices: Iterable[Device]) -> list[Device]:
    return [d for d in devices if device_in_scope(user, d)]


def filter_inventory_for_user(user: User, inventory: Inventory) -> Inventory:
    visible = filter_devices(user, inventory.devices)
    visible_groups = {d.group for d in visible}
    networks = [n for n in inventory.networks if n.group_name in visible_groups or not has_object_scope(user)]
    if user.role == ROLE_ADMIN or not has_object_scope(user):
        networks = inventory.networks
    else:
        networks = [n for n in inventory.networks if n.group_name in visible_groups]
    profiles = inventory.credential_profiles
    if has_object_scope(user):
        profiles = [p for p in profiles if p.group_name in visible_groups]
    return Inventory(credential_profiles=profiles, networks=networks, devices=visible)


def require_device_access(user: User, device_name: str) -> None:
    from services.inventory import load_inventory

    inv = load_inventory()
    device = next((d for d in inv.devices if d.name == device_name), None)
    if device is None:
        return
    if not device_in_scope(user, device):
        raise PermissionError(f"Нет доступа к устройству {device_name}")


def filter_node_dicts(user: User, nodes: list[dict]) -> list[dict]:
    if user.role == ROLE_ADMIN or not has_object_scope(user):
        return nodes
    from services.inventory import load_inventory

    allowed = {d.name for d in filter_devices(user, load_inventory().devices)}
    return [n for n in nodes if n.get("name") in allowed]


def scope_public(user: User) -> dict:
    groups, sites = _scope_lists(user)
    return {
        "allowed_groups": groups,
        "allowed_sites": sites,
        "scoped": has_object_scope(user),
    }
