"""Хранение и управление настройками RADIUS SSO."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from core.models import RadiusConfig
from services.database import is_database_available, require_database, reset_availability_cache

logger = logging.getLogger(__name__)

PASSWORD_MASK = "********"
VALID_ROLES = {"viewer", "operator", "admin"}


@dataclass(frozen=True)
class RadiusConfigData:
    enabled: bool
    server: str
    port: int
    secret: str
    timeout: int
    retries: int
    nas_identifier: str
    role_attribute: str
    admin_values: str
    operator_values: str
    default_role: str
    fallback_local: bool


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes")


def _normalize_list(raw: str) -> str:
    """Разбить значение по запятой/пробелу/новой строке, склеить через запятую."""
    parts = [p.strip() for p in raw.replace("\n", ",").replace(";", ",").split(",")]
    return ",".join([p for p in parts if p])


def _defaults_from_env() -> dict[str, Any]:
    default_role = os.environ.get("RADIUS_DEFAULT_ROLE", "viewer").strip().lower()
    if default_role not in VALID_ROLES:
        default_role = "viewer"
    return {
        "enabled": _env_bool("RADIUS_ENABLED"),
        "server": os.environ.get("RADIUS_SERVER", "").strip(),
        "port": max(1, int(os.environ.get("RADIUS_PORT", "1812"))),
        "secret": os.environ.get("RADIUS_SECRET", ""),
        "timeout": max(1, int(os.environ.get("RADIUS_TIMEOUT", "5"))),
        "retries": max(0, int(os.environ.get("RADIUS_RETRIES", "3"))),
        "nas_identifier": os.environ.get("RADIUS_NAS_IDENTIFIER", "").strip(),
        "role_attribute": (
            os.environ.get("RADIUS_ROLE_ATTRIBUTE", "Filter-Id").strip() or "Filter-Id"
        ),
        "admin_values": _normalize_list(os.environ.get("RADIUS_ADMIN_VALUES", "")),
        "operator_values": _normalize_list(os.environ.get("RADIUS_OPERATOR_VALUES", "")),
        "default_role": default_role,
        "fallback_local": _env_bool("RADIUS_FALLBACK_LOCAL", default=True),
    }


def _row_to_data(row: RadiusConfig) -> RadiusConfigData:
    return RadiusConfigData(
        enabled=row.enabled,
        server=row.server or "",
        port=row.port or 1812,
        secret=row.secret or "",
        timeout=row.timeout or 5,
        retries=row.retries or 3,
        nas_identifier=row.nas_identifier or "",
        role_attribute=row.role_attribute or "Filter-Id",
        admin_values=row.admin_values or "",
        operator_values=row.operator_values or "",
        default_role=row.default_role or "viewer",
        fallback_local=row.fallback_local,
    )


def ensure_initialized() -> None:
    if not is_database_available():
        return
    try:
        defaults = _defaults_from_env()
        row, created = RadiusConfig.objects.get_or_create(pk=1, defaults=defaults)
        if created and row.enabled:
            logger.info("radius | конфигурация инициализирована из .env")
    except Exception as exc:
        logger.warning("radius | init failed: %s", exc)
        reset_availability_cache()


def get_config() -> RadiusConfigData:
    if not is_database_available():
        return RadiusConfigData(**_defaults_from_env())
    try:
        row = RadiusConfig.objects.filter(pk=1).first()
        if not row:
            ensure_initialized()
            row = RadiusConfig.objects.get(pk=1)
        return _row_to_data(row)
    except Exception as exc:
        logger.warning("radius | read failed: %s", exc)
        reset_availability_cache()
        return RadiusConfigData(**_defaults_from_env())


def radius_configured() -> bool:
    cfg = get_config()
    return cfg.enabled and bool(cfg.server.strip()) and bool(cfg.secret)


def get_config_public() -> dict[str, Any]:
    cfg = get_config()
    return {
        "enabled": cfg.enabled,
        "server": cfg.server,
        "port": cfg.port,
        "secret_set": bool(cfg.secret),
        "timeout": cfg.timeout,
        "retries": cfg.retries,
        "nas_identifier": cfg.nas_identifier,
        "role_attribute": cfg.role_attribute,
        "admin_values": cfg.admin_values,
        "operator_values": cfg.operator_values,
        "default_role": cfg.default_role,
        "fallback_local": cfg.fallback_local,
        "configured": radius_configured(),
        "storage": "database" if is_database_available() else "env",
    }


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    require_database("Сохранение настроек RADIUS невозможно")
    row = RadiusConfig.objects.filter(pk=1).first()
    if not row:
        ensure_initialized()
        row = RadiusConfig.objects.get(pk=1)

    default_role = str(payload.get("default_role", row.default_role)).strip().lower()
    if default_role not in VALID_ROLES:
        raise ValueError("default_role должен быть viewer, operator или admin")

    port = int(payload.get("port", row.port))
    if port < 1 or port > 65535:
        raise ValueError("port должен быть от 1 до 65535")

    timeout = int(payload.get("timeout", row.timeout))
    if timeout < 1 or timeout > 60:
        raise ValueError("timeout должен быть от 1 до 60 секунд")

    retries = int(payload.get("retries", row.retries))
    if retries < 0 or retries > 10:
        raise ValueError("retries должен быть от 0 до 10")

    secret = payload.get("secret")
    if secret in (None, "", PASSWORD_MASK):
        secret = row.secret
    else:
        secret = str(secret)

    row.enabled = bool(payload.get("enabled", row.enabled))
    row.server = str(payload.get("server", row.server)).strip()
    row.port = port
    row.secret = secret
    row.timeout = timeout
    row.retries = retries
    row.nas_identifier = str(payload.get("nas_identifier", row.nas_identifier)).strip()
    row.role_attribute = str(payload.get("role_attribute", row.role_attribute)).strip() or "Filter-Id"
    row.admin_values = _normalize_list(str(payload.get("admin_values", row.admin_values)))
    row.operator_values = _normalize_list(str(payload.get("operator_values", row.operator_values)))
    row.default_role = default_role
    row.fallback_local = bool(payload.get("fallback_local", row.fallback_local))
    row.save()
    logger.info("radius | настройки сохранены через UI (enabled=%s)", row.enabled)
    return get_config_public()


def test_connection(
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> dict[str, Any]:
    cfg = get_config()
    if not cfg.server.strip():
        return {"ok": False, "message": "Укажите адрес RADIUS-сервера"}
    if not cfg.secret:
        return {"ok": False, "message": "Укажите shared secret"}

    if not username or not password:
        return {"ok": False, "message": "Укажите логин и пароль для проверки"}

    from services.radius_auth import authenticate_radius

    result = authenticate_radius(username.strip(), password)
    if result:
        vauth = ""
        if result.get("role_attribute") and result.get("role_attribute_value"):
            vauth = f", атрибут {result['role_attribute']}={result['role_attribute_value']!r}"
        return {
            "ok": True,
            "message": f"RADIUS: вход успешен, роль: {result['role']}{vauth}",
            "role": result["role"],
        }
    return {"ok": False, "message": "RADIUS: неверный логин или пароль (Access-Reject)"}
