"""Топология сети из NetBox cables (readonly)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from services.integration_settings import get_config
from services.inventory import load_inventory
from services.inventory_import import _paginate

logger = logging.getLogger(__name__)

TIMEOUT = 60.0


def fetch_netbox_topology() -> dict[str, Any]:
    """Граф узлов (инвентарь) и рёбер (NetBox cables)."""
    cfg = get_config()
    base = (cfg.netbox_url or "").strip().rstrip("/")
    token = (cfg.netbox_token or "").strip()
    if not base or not token:
        raise ValueError("NetBox URL и token обязательны")

    inventory = load_inventory()
    nodes = [
        {
            "id": d.name,
            "name": d.name,
            "ip": d.ip,
            "site": d.site or "",
            "group": d.group or "",
            "critical": bool(d.critical),
        }
        for d in inventory.devices
        if d.enabled
    ]
    node_ids = {n["id"] for n in nodes}
    name_by_netbox_id: dict[int, str] = {}

    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    with httpx.Client(base_url=base, headers=headers, timeout=TIMEOUT, verify=True) as client:
        devices = _paginate(client, "/api/dcim/devices/", params={"status": "active"})
        for dev in devices:
            nb_id = dev.get("id")
            name = str(dev.get("name") or "").strip()
            if nb_id and name and name in node_ids:
                name_by_netbox_id[int(nb_id)] = name

        cables = _paginate(client, "/api/dcim/cables/")
        for cable in cables:
            a_terms = cable.get("a_terminations") or []
            b_terms = cable.get("b_terminations") or []
            a_names = _termination_device_names(a_terms, name_by_netbox_id)
            b_names = _termination_device_names(b_terms, name_by_netbox_id)
            for a in a_names:
                for b in b_names:
                    if a == b:
                        continue
                    key = tuple(sorted((a, b)))
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(
                        {
                            "source": a,
                            "target": b,
                            "cable_id": str(cable.get("id") or ""),
                            "label": str(cable.get("label") or cable.get("type") or ""),
                        }
                    )

    logger.info("topology | netbox | nodes=%d edges=%d", len(nodes), len(edges))
    return {"nodes": nodes, "edges": edges, "source": "netbox"}


def _termination_device_names(terms: list, name_by_id: dict[int, str]) -> list[str]:
    names: list[str] = []
    for term in terms:
        if not isinstance(term, dict):
            continue
        dev = term.get("device")
        if isinstance(dev, dict):
            nb_id = dev.get("id")
            name = str(dev.get("name") or "").strip()
            if name:
                names.append(name)
            elif nb_id and int(nb_id) in name_by_id:
                names.append(name_by_id[int(nb_id)])
        elif isinstance(dev, int) and dev in name_by_id:
            names.append(name_by_id[dev])
    return names
