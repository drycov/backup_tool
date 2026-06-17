from __future__ import annotations

import logging

import httpx
from django.conf import settings

from services.oxidized_logging import engine_title, is_python_engine

logger = logging.getLogger(__name__)


def reload_python_engine() -> None:
    from services.oxidized_engine import reload_engine

    reload_engine()
    logger.info("oxidized | sync | python engine reloaded")


def notify_ruby_engine() -> str:
    """Best-effort reload hint for external Ruby Oxidized after config write."""
    oxidized_url = getattr(settings, "OXIDIZED_URL", "http://oxidized:8888").rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{oxidized_url}/nodes.json")
            if response.status_code < 400:
                logger.info(
                    "oxidized | sync | ruby engine reachable; config updated (auto-reload via mtime)"
                )
                return "config-updated"
    except httpx.HTTPError as exc:
        logger.warning(
            "oxidized | sync | ruby engine unreachable (%s); config written to disk",
            exc,
        )
        return "config-only-unreachable"
    logger.warning("oxidized | sync | ruby engine returned HTTP error; config written")
    return "config-only"


def apply_engine_reload() -> dict[str, str]:
    if is_python_engine():
        reload_python_engine()
        return {"reload": "python-worker", "message": "Python Oxidized worker перезагружен"}
    status = notify_ruby_engine()
    if status == "config-updated":
        return {
            "reload": status,
            "message": "Ruby Oxidized: config обновлён, reload по mtime контейнера",
        }
    return {
        "reload": status,
        "message": (
            "Ruby Oxidized: config записан; контейнер oxidized недоступен — "
            "запустите profile external"
        ),
    }
