"""Oxidized worker settings — read/write oxidized/config YAML."""

from __future__ import annotations

import logging
from typing import Any

import yaml
from django.conf import settings

from services.oxidized_config_loader import (
    config_path,
    default_ssh_port_from_yaml,
    groups_from_yaml,
    list_available_models,
    load_oxidized_yaml,
    resolve_model_name,
)
from services.oxidized_logging import engine_title, is_python_engine, oxidized_log_path

logger = logging.getLogger(__name__)


def _engine() -> str:
    return getattr(settings, "OXIDIZED_ENGINE", "python").lower()


def _write_yaml(cfg: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(cfg, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def group_models_from_yaml(yaml_cfg: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = yaml_cfg if yaml_cfg is not None else load_oxidized_yaml()
    default = str(cfg.get("model") or "routeros")
    result: dict[str, str] = {}
    for name, grp in (cfg.get("groups") or {}).items():
        if isinstance(grp, dict):
            result[str(name)] = str(grp.get("model") or default)
    return result


def set_group_model(group_name: str, model: str) -> None:
    if not group_name or not model:
        return
    cfg = load_oxidized_yaml()
    groups = cfg.setdefault("groups", {})
    entry = groups.setdefault(group_name, {})
    if not isinstance(entry, dict):
        entry = {}
        groups[group_name] = entry
    entry["model"] = resolve_model_name(model)
    _write_yaml(cfg)


def get_oxidized_settings() -> dict[str, Any]:
    yaml_cfg = load_oxidized_yaml()
    yaml_port = default_ssh_port_from_yaml(yaml_cfg)
    engine = _engine()
    health: dict[str, Any] = {}
    try:
        from services.oxidized_client import check_health

        health = check_health()
    except Exception as exc:
        health = {"reachable": False, "error": str(exc), "nodes_count": 0}

    return {
        "engine": engine,
        "engine_title": engine_title(),
        "interval": int(yaml_cfg.get("interval") or settings.OXIDIZED_INTERVAL),
        "threads": int(yaml_cfg.get("threads") or settings.OXIDIZED_THREADS),
        "timeout": int(yaml_cfg.get("timeout") or settings.OXIDIZED_TIMEOUT),
        "retries": int(yaml_cfg.get("retries") or settings.OXIDIZED_RETRIES),
        "default_model": resolve_model_name(str(yaml_cfg.get("model") or "routeros")),
        "ssh_port": yaml_port if yaml_port is not None else settings.ROUTEROS_SSH_PORT,
        "resolve_dns": str(yaml_cfg.get("resolve_dns", "true")).lower() in ("1", "true", "yes"),
        "log_path": str(oxidized_log_path()),
        "proxy_url": "/oxidized-proxy/nodes",
        "available_models": list_available_models(),
        "group_models": group_models_from_yaml(yaml_cfg),
        "health": {
            "reachable": health.get("reachable", False),
            "nodes_count": health.get("nodes_count", 0),
            "error": health.get("error"),
        },
        "editable": True,
        "env_note": "Движок задаётся в .env (OXIDIZED_ENGINE); worker — в oxidized/config; Git и scan — во вкладках настроек",
    }


def save_oxidized_settings(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = load_oxidized_yaml()
    cfg["interval"] = max(60, int(payload.get("interval") or settings.OXIDIZED_INTERVAL))
    cfg["threads"] = max(1, min(64, int(payload.get("threads") or settings.OXIDIZED_THREADS)))
    cfg["timeout"] = max(5, int(payload.get("timeout") or settings.OXIDIZED_TIMEOUT))
    cfg["retries"] = max(0, int(payload.get("retries") or settings.OXIDIZED_RETRIES))
    cfg["model"] = resolve_model_name(str(payload.get("default_model") or "routeros"))
    cfg["resolve_dns"] = bool(payload.get("resolve_dns", True))

    ssh_port = int(payload.get("ssh_port") or settings.ROUTEROS_SSH_PORT)
    cfg["input"] = {
        "default": "ssh",
        "ssh": {"secure": False, "port": ssh_port},
    }

    group_models = payload.get("group_models") or {}
    if isinstance(group_models, dict):
        groups = cfg.setdefault("groups", {})
        for group_name, model in group_models.items():
            if not group_name:
                continue
            entry = groups.setdefault(str(group_name), {})
            if isinstance(entry, dict):
                entry["model"] = resolve_model_name(str(model))

    _write_yaml(cfg)

    from services.inventory import load_inventory, update_oxidized_credentials

    reload_info = update_oxidized_credentials(load_inventory())
    logger.info("oxidized | settings | saved interval=%s threads=%s", cfg["interval"], cfg["threads"])
    result = get_oxidized_settings()
    result["reload"] = reload_info
    return result
