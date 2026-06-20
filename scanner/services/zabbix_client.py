"""Клиент Zabbix JSON-RPC: теги хоста по имени объекта."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 300.0
_tags_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class ZabbixClientError(Exception):
    pass


class ZabbixNotConfigured(ZabbixClientError):
    pass


def _get_api_config() -> tuple[str, str]:
    from services.integration_settings import get_config

    cfg = get_config()
    url = (cfg.zabbix_api_url or "").strip().rstrip("/")
    token = (cfg.zabbix_api_token or "").strip()
    if not cfg.zabbix_api_enabled or not url or not token:
        raise ZabbixNotConfigured("Zabbix API не настроен (URL и token в Настройки → Интеграции)")
    if not url.endswith("/api_jsonrpc.php"):
        url = f"{url}/api_jsonrpc.php"
    return url, token


def _rpc(method: str, params: dict[str, Any] | None = None, *, auth: str | None = None) -> Any:
    url, token = _get_api_config()
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1,
    }
    if auth is not None:
        payload["auth"] = auth
    elif method != "apiinfo.version":
        payload["auth"] = token

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise ZabbixClientError(f"Zabbix HTTP: {exc}") from exc
    except ValueError as exc:
        raise ZabbixClientError("Zabbix: неверный JSON в ответе") from exc

    if "error" in data:
        err = data["error"]
        msg = err.get("message", "unknown error")
        if isinstance(err.get("data"), str) and err["data"]:
            msg = f"{msg}: {err['data']}"
        raise ZabbixClientError(msg)
    return data.get("result")


def tags_list_to_map(tags: list[dict[str, Any]] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in tags or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("tag") or "").strip()
        if not key:
            continue
        out[key] = str(item.get("value") or "")
    return out


def _find_host(object_name: str) -> dict[str, Any] | None:
    name = (object_name or "").strip()
    if not name:
        raise ValueError("name обязателен")

    base_params = {
        "output": ["hostid", "name", "host"],
        "selectTags": "extend",
        "limit": 1,
    }
    for field, value in (("name", name), ("host", name)):
        rows = _rpc("host.get", {**base_params, "filter": {field: value}})
        if rows:
            return rows[0]

    rows = _rpc(
        "host.get",
        {
            **base_params,
            "search": {"name": name},
            "searchWildcardsEnabled": True,
        },
    )
    if rows:
        return rows[0]

    rows = _rpc(
        "host.get",
        {
            **base_params,
            "search": {"host": name},
            "searchWildcardsEnabled": True,
        },
    )
    return rows[0] if rows else None


def get_host_tags(object_name: str, *, use_cache: bool = True) -> dict[str, Any]:
    """Теги Zabbix-хоста по имени объекта (visible name или technical host)."""
    name = (object_name or "").strip()
    if not name:
        raise ValueError("name обязателен")

    if use_cache:
        cached = _tags_cache.get(name.lower())
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SEC:
            return cached[1]

    host = _find_host(name)
    if not host:
        raise LookupError(f"Хост Zabbix '{name}' не найден")

    tags_raw = host.get("tags") if isinstance(host.get("tags"), list) else []
    tags_map = tags_list_to_map(tags_raw)
    result = {
        "name": name,
        "hostid": str(host.get("hostid") or ""),
        "visible_name": str(host.get("name") or ""),
        "host": str(host.get("host") or ""),
        "tags": [{"tag": k, "value": v} for k, v in sorted(tags_map.items())],
        "tags_map": tags_map,
    }
    _tags_cache[name.lower()] = (time.monotonic(), result)
    return result


def get_host_tags_map(object_name: str, *, use_cache: bool = True) -> dict[str, str]:
    try:
        return get_host_tags(object_name, use_cache=use_cache)["tags_map"]
    except (ZabbixNotConfigured, LookupError, ZabbixClientError, ValueError):
        return {}


def test_zabbix_api() -> dict[str, Any]:
    version = _rpc("apiinfo.version", auth=None)
    _, token = _get_api_config()
    rows = _rpc("host.get", {"output": ["hostid"], "limit": 1}, auth=token)
    return {
        "ok": True,
        "version": version,
        "hosts_sample": len(rows or []),
    }


def invalidate_tags_cache() -> None:
    _tags_cache.clear()
