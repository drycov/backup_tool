from typing import Any, Optional

import httpx
from urllib.parse import quote

from django.conf import settings

TIMEOUT = 30.0


def _use_python_engine() -> bool:
    return getattr(settings, "OXIDIZED_ENGINE", "python").lower() == "python"


def _external_request(method: str, path: str, **kwargs: Any) -> tuple[Optional[Any], Optional[str]]:
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
    if _use_python_engine():
        from services.oxidized_engine import get_manager

        return get_manager().list_nodes(), None

    data, err = _external_request("GET", "/nodes.json")
    if err:
        return None, err
    if isinstance(data, list):
        return data, None
    return None, "Неверный формат ответа nodes.json"


def get_node_config(name: str) -> tuple[Optional[str], Optional[str]]:
    if _use_python_engine():
        from services.oxidized_engine import get_manager

        text = get_manager().show_node(name)
        if text is None:
            return None, None
        return text, None

    return _external_request("GET", f"/node/show/{name}.json")


def fetch_node(name: str) -> tuple[Optional[Any], Optional[str]]:
    if _use_python_engine():
        from services.oxidized_engine import get_manager

        try:
            return get_manager().fetch_node(name), None
        except Exception as exc:
            return None, str(exc)

    return _external_request("GET", f"/node/fetch/{name}.json")


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
    if _use_python_engine():
        from services.oxidized_engine import get_manager
        from services.oxidized_engine.exceptions import NodeNotFound

        try:
            return get_manager().node_versions(name), None
        except NodeNotFound:
            return None, f"Узел '{name}' не найден"

    node, err = _find_node(name)
    if err:
        return None, err
    group = node.get("group") or ""
    node_full = _node_full_name(name, group)
    data, err = _external_request(
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
    if _use_python_engine():
        params = {"oid": oid}
        if oid2:
            params["oid2"] = oid2
        query = "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items())
        return f"/api/oxidized/nodes/{quote(name, safe='')}/diff?{query}"

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
    if _use_python_engine():
        return f"/api/oxidized/nodes/{quote(name, safe='')}/versions/{quote(oid, safe='')}"

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
    if _use_python_engine():
        return f"/api/oxidized/nodes/{quote(name, safe='')}/versions"

    node_full = _node_full_name(name, group)
    return (
        f"/oxidized-proxy/node/version?"
        f"node_full={quote(node_full, safe='')}"
    )


def check_health() -> dict:
    if _use_python_engine():
        from services.oxidized_engine import get_manager

        payload = get_manager().health()
        payload["public_url"] = settings.OXIDIZED_PUBLIC_URL
        payload["internal_url"] = "python-engine"
        return payload

    data, err = get_nodes()
    return {
        "reachable": err is None,
        "error": err,
        "nodes_count": len(data) if data else 0,
        "engine": "external",
        "public_url": settings.OXIDIZED_PUBLIC_URL,
        "internal_url": settings.OXIDIZED_URL,
    }
