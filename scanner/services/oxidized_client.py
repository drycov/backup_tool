from typing import Any, Optional

import httpx
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


def check_health() -> dict:
    data, err = get_nodes()
    return {
        "reachable": err is None,
        "error": err,
        "nodes_count": len(data) if data else 0,
        "public_url": settings.OXIDIZED_PUBLIC_URL,
        "internal_url": settings.OXIDIZED_URL,
    }
