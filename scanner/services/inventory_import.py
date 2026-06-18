"""Импорт устройств из NetBox и LibreNMS."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from services.integration_settings import get_config
from services.inventory import _upsert_device_record, update_oxidized_credentials
from services.schemas import Device
from services.sites import upsert_site

logger = logging.getLogger(__name__)

TIMEOUT = 60.0
PAGE_SIZE = 100

def _map_model_hint(hint: str) -> str:
    from services.vendor_catalog import normalize_model

    raw = (hint or "").strip().lower()
    if not raw:
        return "ios"
    for key in (
        "routeros", "mikrotik", "ios", "cisco", "junos", "juniper",
        "eos", "arista", "nxos", "asa", "fortios", "panos", "linux",
    ):
        if key in raw:
            return normalize_model(key)
    cleaned = raw.replace(" ", "-")[:32]
    return normalize_model(cleaned) if cleaned else "ios"


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    sites_upserted: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "sites_upserted": self.sites_upserted,
            "errors": self.errors,
        }


def _paginate(client: httpx.Client, url: str, *, params: dict | None = None) -> list[dict]:
    items: list[dict] = []
    offset = 0
    base_params = dict(params or {})
    while True:
        page_params = {**base_params, "limit": PAGE_SIZE, "offset": offset}
        resp = client.get(url, params=page_params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "results" in data:
            batch = data.get("results") or []
            items.extend(batch)
            if not data.get("next"):
                break
            offset += len(batch)
            if not batch:
                break
        elif isinstance(data, list):
            items.extend(data)
            break
        else:
            break
    return items


def _netbox_ip(device: dict) -> str:
    for key in ("primary_ip4", "primary_ip6", "primary_ip"):
        val = device.get(key)
        if isinstance(val, dict):
            addr = str(val.get("address") or "").split("/")[0].strip()
            if addr:
                return addr
        elif isinstance(val, str) and val:
            return val.split("/")[0].strip()
    return ""


def _netbox_tags(device: dict) -> list[str]:
    tags: list[str] = []
    for tag in device.get("tags") or []:
        if isinstance(tag, dict):
            name = str(tag.get("slug") or tag.get("name") or "").strip()
            if name:
                tags.append(name)
        elif tag:
            tags.append(str(tag).strip())
    return tags


def import_from_netbox(*, dry_run: bool = False) -> ImportResult:
    cfg = get_config()
    base = (cfg.netbox_url or "").strip().rstrip("/")
    token = (cfg.netbox_token or "").strip()
    if not base or not token:
        raise ValueError("NetBox URL и token обязательны")

    result = ImportResult()
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    with httpx.Client(timeout=TIMEOUT, headers=headers) as client:
        sites = _paginate(client, f"{base}/api/dcim/sites/")
        site_parent: dict[str, str] = {}
        for site in sites:
            slug = str(site.get("slug") or "").strip()
            if not slug:
                continue
            parent = site.get("parent")
            parent_slug = ""
            if isinstance(parent, dict):
                parent_slug = str(parent.get("slug") or "").strip()
            site_parent[slug] = parent_slug
            if not dry_run:
                upsert_site(slug, name=str(site.get("name") or slug), parent_slug=parent_slug)
            result.sites_upserted += 1

        devices = _paginate(client, f"{base}/api/dcim/devices/")

    existing_names = set()
    if not dry_run:
        from core.models import Device as DeviceModel

        existing_names = set(DeviceModel.objects.values_list("name", flat=True))

    default_group = cfg.netbox_default_group or "default"

    for row in devices:
        name = str(row.get("name") or "").strip()
        ip = _netbox_ip(row)
        if not name or not ip:
            result.skipped += 1
            continue

        site_obj = row.get("site") if isinstance(row.get("site"), dict) else {}
        site_slug = str(site_obj.get("slug") or "").strip()
        role_obj = row.get("role") if isinstance(row.get("role"), dict) else {}
        role_slug = str(role_obj.get("slug") or role_obj.get("name") or "").strip()
        dtype = row.get("device_type") if isinstance(row.get("device_type"), dict) else {}
        model_hint = str(dtype.get("slug") or dtype.get("model") or dtype.get("display") or "")

        device = Device(
            name=name,
            ip=ip,
            model=_map_model_hint(model_hint),
            group=default_group,
            enabled=True,
            site=site_slug,
            role=role_slug,
            tags=_netbox_tags(row),
        )

        if dry_run:
            if name in existing_names:
                result.updated += 1
            else:
                result.created += 1
            continue

        is_new = name not in existing_names
        _upsert_device_record(device)
        existing_names.add(name)
        if is_new:
            result.created += 1
        else:
            result.updated += 1

    if not dry_run:
        from services.inventory import load_inventory

        update_oxidized_credentials(load_inventory())
    logger.info(
        "inventory_import | netbox | created=%s updated=%s skipped=%s",
        result.created,
        result.updated,
        result.skipped,
    )
    return result


def import_from_librenms(*, dry_run: bool = False) -> ImportResult:
    cfg = get_config()
    base = (cfg.librenms_url or "").strip().rstrip("/")
    token = (cfg.librenms_token or "").strip()
    if not base or not token:
        raise ValueError("LibreNMS URL и token обязательны")

    result = ImportResult()
    headers = {"X-Auth-Token": token, "Accept": "application/json"}

    with httpx.Client(timeout=TIMEOUT, headers=headers) as client:
        resp = client.get(f"{base}/api/v0/devices")
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("devices") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("LibreNMS: неожиданный формат ответа")

    existing_names = set()
    if not dry_run:
        from core.models import Device as DeviceModel

        existing_names = set(DeviceModel.objects.values_list("name", flat=True))

    default_group = cfg.librenms_default_group or "default"

    for row in rows:
        if not isinstance(row, dict):
            result.skipped += 1
            continue
        name = str(row.get("hostname") or row.get("sysName") or "").strip()
        ip = str(row.get("ip") or row.get("overwrite_ip") or "").strip()
        if not name or not ip:
            result.skipped += 1
            continue

        location = str(row.get("location") or row.get("site") or "").strip()
        site_slug = location.lower().replace(" ", "-")[:128] if location else ""
        if site_slug and not dry_run:
            upsert_site(site_slug, name=location)
            result.sites_upserted += 1

        model_hint = str(row.get("os") or row.get("hardware") or row.get("sysDescr") or "")
        tags: list[str] = []
        if row.get("type"):
            tags.append(str(row["type"]))

        device = Device(
            name=name,
            ip=ip,
            model=_map_model_hint(model_hint),
            group=default_group,
            enabled=True,
            site=site_slug,
            role=str(row.get("type") or "").strip(),
            tags=tags,
        )

        if dry_run:
            if name in existing_names:
                result.updated += 1
            else:
                result.created += 1
            continue

        is_new = name not in existing_names
        _upsert_device_record(device)
        existing_names.add(name)
        if is_new:
            result.created += 1
        else:
            result.updated += 1

    if not dry_run:
        from services.inventory import load_inventory

        update_oxidized_credentials(load_inventory())
    logger.info(
        "inventory_import | librenms | created=%s updated=%s skipped=%s",
        result.created,
        result.updated,
        result.skipped,
    )
    return result


def run_scheduled_inventory_sync() -> dict[str, Any]:
    from django.utils import timezone as dj_tz

    from core.models import IntegrationConfig

    cfg = get_config()
    if not cfg.inventory_sync_enabled:
        return {"skipped": 1, "reason": "disabled"}

    source = (cfg.inventory_sync_source or "netbox").strip().lower()
    if source == "librenms":
        result = import_from_librenms()
    else:
        result = import_from_netbox()

    row = IntegrationConfig.objects.filter(pk=1).first()
    if row:
        row.inventory_sync_last_run_at = dj_tz.now()
        row.save(update_fields=["inventory_sync_last_run_at"])

    return {"source": source, **result.to_dict()}
