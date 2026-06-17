import os
from typing import Any, Optional

import httpx

OXIDIZED_URL = os.environ.get("OXIDIZED_URL", "http://oxidized:8888").rstrip("/")
OXIDIZED_PUBLIC_URL = os.environ.get(
    "OXIDIZED_PUBLIC_URL", "http://localhost:8888"
).rstrip("/")
TIMEOUT = 30.0


async def _request(
    method: str,
    path: str,
    **kwargs: Any,
) -> tuple[Optional[Any], Optional[str]]:
    url = f"{OXIDIZED_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(method, url, **kwargs)
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


async def get_nodes() -> tuple[Optional[list], Optional[str]]:
    data, err = await _request("GET", "/nodes.json")
    if err:
        return None, err
    if isinstance(data, list):
        return data, None
    return None, "Неверный формат ответа nodes.json"


async def get_node_config(name: str) -> tuple[Optional[str], Optional[str]]:
    return await _request("GET", f"/node/show/{name}.json")


async def fetch_node(name: str) -> tuple[Optional[Any], Optional[str]]:
    return await _request("GET", f"/node/fetch/{name}.json")


async def get_version() -> tuple[Optional[Any], Optional[str]]:
    return await _request("GET", "/version.json")


async def check_health() -> dict:
    data, err = await get_nodes()
    return {
        "reachable": err is None,
        "error": err,
        "nodes_count": len(data) if data else 0,
        "public_url": OXIDIZED_PUBLIC_URL,
        "internal_url": OXIDIZED_URL,
    }
