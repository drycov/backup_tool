from typing import Any, Optional

import httpx
from urllib.parse import quote

from django.conf import settings

TIMEOUT = 30.0


def _request(method: str, path: str, **kwargs: Any) -> tuple[Optional[Any], Optional[str]]:
    url = f"{settings.OXIDIZED_URL}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.request(method, url, **kwargs)
            if response.status_code >= 400:
                return None, f"Oxidized HTTP {response.status_code}: {response.text[:200]}"
            if not response.content:
                return None, None
            if "application/json" in response.headers.get("content-type", ""):
                return response.json(), None
            return response.text, None
    except httpx.ConnectError:
        return None, "Oxidized недоступен — проверьте контейнер oxidized"
    except httpx.TimeoutException:
        return None, "Таймаут запроса к Oxidized"
    except Exception as exc:
        return None, str(exc)


def get_nodes() -> tuple[Optional[list], Optional[str]]:
    data, err = _request("GET", "/nodes.json")
    if err:
        return None, err
    if isinstance(data, list):
        return data, None
    return None, "Неверный формат ответа nodes.json"


def get_node_config(name: str) -> tuple[Optional[str], Optional[str]]:
    return _request("GET", f"/node/show/{name}.json")


def fetch_node(name: str) -> tuple[Optional[Any], Optional[str]]:
    return _request("GET", f"/node/fetch/{name}.json")


def _find_node(name: str) -> tuple[Optional[dict], Optional[str]]:
    nodes, err = get_nodes()
    if err:
        return None, err
    for node in nodes or []:
        if node.get("name") == name:
            return node, None
    return None, f"Узел '{name}' не найден"


def _node_full_name(name: str, group: Optional[str] = None) -> str:
    if group and group not in ("", "default"):
        return f"{group}/{name}"
    return name


def get_node_versions(name: str) -> tuple[Optional[dict], Optional[str]]:
    node, err = _find_node(name)
    if err:
        return None, err
    group = node.get("group") or ""
    node_full = _node_full_name(name, group)
    data, err = _request(
        "GET",
        f"/node/version.json?node_full={quote(node_full, safe='')}",
    )
    if err:
        return None, err
    if not isinstance(data, list):
        return None, "Неверный формат ответа version.json"
    return {
        "node": name,
        "group": group,
        "node_full": node_full,
        "versions": data,
    }, None


def build_diff_proxy_path(
    name: str,
    group: str,
    oid: str,
    epoch: int,
    num: int,
    oid2: Optional[str] = None,
) -> str:
    params = {
        "node": name,
        "group": group or "",
        "oid": oid,
        "epoch": str(epoch),
        "num": str(num),
    }
    if oid2:
        params["oid2"] = oid2
    query = "&".join(f"{key}={quote(str(value), safe='')}" for key, value in params.items())
    return f"/oxidized-proxy/node/version/diffs?{query}"


def build_version_view_proxy_path(
    name: str,
    group: str,
    oid: str,
    epoch: int,
    num: int,
) -> str:
    params = {
        "node": name,
        "group": group or "",
        "oid": oid,
        "epoch": str(epoch),
        "num": str(num),
    }
    query = "&".join(f"{key}={quote(str(value), safe='')}" for key, value in params.items())
    return f"/oxidized-proxy/node/version/view?{query}"


def build_versions_proxy_path(name: str, group: str = "") -> str:
    node_full = _node_full_name(name, group)
    return (
        f"/oxidized-proxy/node/version?"
        f"node_full={quote(node_full, safe='')}"
    )


def check_health() -> dict:
    data, err = get_nodes()
    return {
        "reachable": err is None,
        "error": err,
        "nodes_count": len(data) if data else 0,
        "public_url": settings.OXIDIZED_PUBLIC_URL,
        "internal_url": settings.OXIDIZED_URL,
    }
