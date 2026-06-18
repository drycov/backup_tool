"""Unified Oxidized diff — python engine и external Ruby."""

from __future__ import annotations

import difflib
from typing import Any, Optional
from urllib.parse import quote

import httpx
from django.conf import settings

TIMEOUT = 30.0


def get_node_diff(name: str, oid: str, oid2: Optional[str] = None) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() == "python":
        from services.oxidized_engine import get_manager
        from services.oxidized_engine.exceptions import NodeNotFound

        try:
            return get_manager().get_diff(name, oid, oid2), None
        except NodeNotFound:
            return None, f"Node '{name}' not found"

    return _external_diff(name, oid, oid2)


def get_node_version_text(name: str, oid: str) -> tuple[Optional[str], Optional[str]]:
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() == "python":
        from services.oxidized_engine import get_manager
        from services.oxidized_engine.exceptions import NodeNotFound

        try:
            text = get_manager().get_version(name, oid)
            if text == "version not found":
                return None, "version not found"
            return text, None
        except NodeNotFound:
            return None, f"Node '{name}' not found"

    from services.oxidized_client import get_node_versions

    meta, err = get_node_versions(name)
    if err:
        return None, err
    version = _find_version_entry(meta, oid)
    if not version:
        return None, "version not found"
    return _fetch_external_version_text(
        name,
        meta.get("group") or "",
        oid,
        int(version.get("epoch") or 0),
        int(version.get("num") or 0),
    )


def _external_diff(name: str, oid: str, oid2: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
    new_text, err = get_node_version_text(name, oid)
    if err:
        return None, err
    if not oid2:
        from services.oxidized_client import get_node_versions

        meta, err = get_node_versions(name)
        if err:
            return None, err
        versions = meta.get("versions") or []
        prev = None
        for idx, ver in enumerate(versions):
            if str(ver.get("oid")) == str(oid) and idx + 1 < len(versions):
                prev = versions[idx + 1]
                break
        if prev:
            oid2 = str(prev.get("oid"))

    if not oid2:
        return {"patch": "", "stat": {"insertions": 0, "deletions": 0}}, None

    old_text, err = get_node_version_text(name, oid2)
    if err:
        return None, err
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    patch = "\n".join(
        difflib.unified_diff(old_lines, new_lines, fromfile=oid2, tofile=oid, lineterm="")
    )
    insertions = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
    return {"patch": patch, "stat": {"insertions": insertions, "deletions": deletions}}, None


def _find_version_entry(meta: dict, oid: str) -> Optional[dict]:
    for ver in meta.get("versions") or []:
        if str(ver.get("oid")) == str(oid):
            return ver
    return None


def _fetch_external_version_text(
    name: str,
    group: str,
    oid: str,
    epoch: int,
    num: int,
) -> tuple[Optional[str], Optional[str]]:
    params = {
        "node": name,
        "group": group or "",
        "oid": oid,
        "epoch": str(epoch),
        "num": str(num),
    }
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    url = f"{settings.OXIDIZED_URL}/node/version/view?{query}"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(url)
            if response.status_code >= 400:
                return None, f"Oxidized HTTP {response.status_code}"
            return response.text, None
    except httpx.HTTPError as exc:
        return None, str(exc)
