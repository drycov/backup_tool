from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings

from services.oxidized_engine.config import GroupConfig


def config_path() -> Path:
    return Path(getattr(settings, "OXIDIZED_CONFIG_PATH", "/data/oxidized/config"))


def oxidized_home() -> Path:
    import os

    env_home = os.environ.get("OXIDIZED_HOME")
    if env_home:
        return Path(env_home)
    path = config_path()
    return path.parent if path.name == "config" else path


def load_oxidized_yaml(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or config_path()
    if not cfg_path.exists():
        return {}
    try:
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def _map_value(model_map: dict[Any, Any], original: str) -> str:
    for key, mapped in model_map.items():
        if isinstance(key, str) and key.startswith("!ruby/regexp "):
            pattern = key.removeprefix("!ruby/regexp ").strip()
            if re.search(pattern, original):
                return str(mapped)
        elif str(key) == str(original):
            return str(mapped)
    return original


def _normalize_model_id(name: str) -> str:
    """Oxidized gem model ids are lowercase file names (e.g. routeros)."""
    key = name.strip().lower().replace(" ", "").replace("_", "-")
    aliases = {
        "routeros": "routeros",
        "mikrotik": "routeros",
        "mikrotik-routeros": "routeros",
        "ros": "routeros",
    }
    return aliases.get(key, key.lower())


def resolve_model_name(raw: str | None, yaml_cfg: dict[str, Any] | None = None) -> str:
    cfg = yaml_cfg if yaml_cfg is not None else load_oxidized_yaml()
    default = _normalize_model_id(str(cfg.get("model") or "routeros"))
    if not raw:
        return default
    model_map = cfg.get("model_map") or {}
    mapped = _map_value(model_map, str(raw))
    return _normalize_model_id(mapped)


def groups_from_yaml(
    yaml_cfg: dict[str, Any] | None = None,
    *,
    default_model: str | None = None,
) -> dict[str, GroupConfig]:
    cfg = yaml_cfg if yaml_cfg is not None else load_oxidized_yaml()
    fallback_model = default_model or str(cfg.get("model") or "routeros")
    groups: dict[str, GroupConfig] = {}
    for name, grp in (cfg.get("groups") or {}).items():
        if not isinstance(grp, dict):
            continue
        groups[str(name)] = GroupConfig(
            username=str(grp.get("username") or ""),
            password=str(grp.get("password") or ""),
            model=str(grp.get("model") or fallback_model),
        )
    return groups


def default_ssh_port_from_yaml(yaml_cfg: dict[str, Any] | None = None) -> int | None:
    cfg = yaml_cfg if yaml_cfg is not None else load_oxidized_yaml()
    input_cfg = cfg.get("input") or {}
    ssh_cfg = input_cfg.get("ssh") or {}
    port = ssh_cfg.get("port")
    return int(port) if port is not None else None


def list_available_models() -> list[str]:
    from services.oxidized_engine.model.registry import list_native_models

    native = list_native_models()
    try:
        from services.oxidized_engine.collector.ruby_bridge import list_models

        ruby = list_models()
        if ruby:
            merged = list(dict.fromkeys(ruby + native))
            return merged
    except Exception:
        pass
    return native
