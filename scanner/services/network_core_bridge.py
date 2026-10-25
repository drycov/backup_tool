"""Bridge to shared network-core library (ops platform).

Prefer these imports in new code instead of duplicating MikroTik / vendor helpers.
"""
from __future__ import annotations

from network_core.geo import distance_m
from network_core.mikrotik import discover_subnets, read_resource
from network_core.vendor_identity import (
    infer_vendor,
    manufacturer_for_display,
    normalize_vendor,
)

__all__ = [
    "distance_m",
    "discover_subnets",
    "read_resource",
    "infer_vendor",
    "manufacturer_for_display",
    "normalize_vendor",
    "routeros_identity",
]


async def routeros_identity(
    host: str,
    username: str,
    password: str,
    port: int = 8728,
    use_ssl: bool = False,
) -> str | None:
    """Return RouterOS system identity via API (not SSH)."""
    rows = await read_resource(
        host, username, password, port=port, use_ssl=use_ssl, resource="/system/identity"
    )
    if not rows:
        return None
    name = rows[0].get("name")
    return str(name).strip() if name else None
