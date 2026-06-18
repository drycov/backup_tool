"""Хранение и управление настройками LDAP / Active Directory."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from core.models import LdapConfig
from services.database import is_database_available, require_database, reset_availability_cache

logger = logging.getLogger(__name__)

PASSWORD_MASK = "********"
VALID_DIRECTORY_TYPES = {LdapConfig.DIRECTORY_LDAP, LdapConfig.DIRECTORY_AD}
VALID_ROLES = {"viewer", "operator", "admin"}


@dataclass(frozen=True)
class LdapConfigData:
    enabled: bool
    directory_type: str
    server: str
    use_ssl: bool
    start_tls: bool
    bind_dn: str
    bind_password: str
    user_base: str
    user_filter: str
    user_dn_template: str
    user_upn_suffix: str
    admin_groups: str
    operator_groups: str
    default_role: str
    fallback_local: bool
    connect_timeout: int
    scope_mappings: list[dict]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes")


def _defaults_from_env() -> dict[str, Any]:
    directory_type = LdapConfig.DIRECTORY_AD if _env_bool("LDAP_AD") else LdapConfig.DIRECTORY_LDAP
    user_filter = os.environ.get("LDAP_USER_FILTER", "")
    if not user_filter:
        user_filter = (
            "(sAMAccountName={username})"
            if directory_type == LdapConfig.DIRECTORY_AD
            else "(uid={username})"
        )
    default_role = os.environ.get("LDAP_DEFAULT_ROLE", "viewer").strip().lower()
    if default_role not in VALID_ROLES:
        default_role = "viewer"
    return {
        "enabled": _env_bool("LDAP_ENABLED"),
        "directory_type": directory_type,
        "server": os.environ.get("LDAP_SERVER", "").strip(),
        "use_ssl": _env_bool("LDAP_USE_SSL"),
        "start_tls": _env_bool("LDAP_START_TLS", default=True),
        "bind_dn": os.environ.get("LDAP_BIND_DN", "").strip(),
        "bind_password": os.environ.get("LDAP_BIND_PASSWORD", ""),
        "user_base": os.environ.get("LDAP_USER_BASE", "").strip(),
        "user_filter": user_filter,
        "user_dn_template": os.environ.get("LDAP_USER_DN_TEMPLATE", "").strip(),
        "user_upn_suffix": os.environ.get("LDAP_USER_UPN_SUFFIX", "").strip(),
        "admin_groups": os.environ.get("LDAP_ADMIN_GROUPS", "").strip(),
        "operator_groups": os.environ.get("LDAP_OPERATOR_GROUPS", "").strip(),
        "default_role": default_role,
        "fallback_local": _env_bool("LDAP_FALLBACK_LOCAL", default=True),
        "connect_timeout": max(1, int(os.environ.get("LDAP_CONNECT_TIMEOUT", "10"))),
    }


def _row_to_data(row: LdapConfig) -> LdapConfigData:
    return LdapConfigData(
        enabled=row.enabled,
        directory_type=row.directory_type or LdapConfig.DIRECTORY_LDAP,
        server=row.server or "",
        use_ssl=row.use_ssl,
        start_tls=row.start_tls,
        bind_dn=row.bind_dn or "",
        bind_password=row.bind_password or "",
        user_base=row.user_base or "",
        user_filter=row.user_filter or "(uid={username})",
        user_dn_template=row.user_dn_template or "",
        user_upn_suffix=row.user_upn_suffix or "",
        admin_groups=row.admin_groups or "",
        operator_groups=row.operator_groups or "",
        default_role=row.default_role or "viewer",
        fallback_local=row.fallback_local,
        connect_timeout=row.connect_timeout or 10,
        scope_mappings=list(row.scope_mappings or []),
    )


def ensure_initialized() -> None:
    if not is_database_available():
        return
    try:
        defaults = _defaults_from_env()
        row, created = LdapConfig.objects.get_or_create(pk=1, defaults=defaults)
        if created and row.enabled:
            logger.info("ldap | конфигурация инициализирована из .env")
    except Exception as exc:
        logger.warning("ldap | init failed: %s", exc)
        reset_availability_cache()


def get_config() -> LdapConfigData:
    if not is_database_available():
        return LdapConfigData(**{**_defaults_from_env(), "scope_mappings": []})
    try:
        row = LdapConfig.objects.filter(pk=1).first()
        if not row:
            ensure_initialized()
            row = LdapConfig.objects.get(pk=1)
        return _row_to_data(row)
    except Exception as exc:
        logger.warning("ldap | read failed: %s", exc)
        reset_availability_cache()
        return LdapConfigData(**{**_defaults_from_env(), "scope_mappings": []})


def ldap_configured() -> bool:
    cfg = get_config()
    return cfg.enabled and bool(cfg.server.strip())


def get_config_public() -> dict[str, Any]:
    cfg = get_config()
    return {
        "enabled": cfg.enabled,
        "directory_type": cfg.directory_type,
        "server": cfg.server,
        "use_ssl": cfg.use_ssl,
        "start_tls": cfg.start_tls,
        "bind_dn": cfg.bind_dn,
        "bind_password_set": bool(cfg.bind_password),
        "user_base": cfg.user_base,
        "user_filter": cfg.user_filter,
        "user_dn_template": cfg.user_dn_template,
        "user_upn_suffix": cfg.user_upn_suffix,
        "admin_groups": cfg.admin_groups,
        "operator_groups": cfg.operator_groups,
        "default_role": cfg.default_role,
        "fallback_local": cfg.fallback_local,
        "connect_timeout": cfg.connect_timeout,
        "scope_mappings": cfg.scope_mappings,
        "configured": ldap_configured(),
        "storage": "database" if is_database_available() else "env",
    }


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    require_database("Сохранение настроек LDAP невозможно")
    row = LdapConfig.objects.filter(pk=1).first()
    if not row:
        ensure_initialized()
        row = LdapConfig.objects.get(pk=1)

    directory_type = str(payload.get("directory_type", row.directory_type)).strip().lower()
    if directory_type not in VALID_DIRECTORY_TYPES:
        raise ValueError("directory_type должен быть ldap или ad")

    default_role = str(payload.get("default_role", row.default_role)).strip().lower()
    if default_role not in VALID_ROLES:
        raise ValueError("default_role должен быть viewer, operator или admin")

    timeout = int(payload.get("connect_timeout", row.connect_timeout))
    if timeout < 1 or timeout > 120:
        raise ValueError("connect_timeout должен быть от 1 до 120 секунд")

    bind_password = payload.get("bind_password")
    if bind_password in (None, "", PASSWORD_MASK):
        bind_password = row.bind_password
    else:
        bind_password = str(bind_password)

    row.enabled = bool(payload.get("enabled", row.enabled))
    row.directory_type = directory_type
    row.server = str(payload.get("server", row.server)).strip()
    row.use_ssl = bool(payload.get("use_ssl", row.use_ssl))
    row.start_tls = bool(payload.get("start_tls", row.start_tls))
    row.bind_dn = str(payload.get("bind_dn", row.bind_dn)).strip()
    row.bind_password = bind_password
    row.user_base = str(payload.get("user_base", row.user_base)).strip()
    row.user_filter = str(payload.get("user_filter", row.user_filter)).strip() or "(uid={username})"
    row.user_dn_template = str(payload.get("user_dn_template", row.user_dn_template)).strip()
    row.user_upn_suffix = str(payload.get("user_upn_suffix", row.user_upn_suffix)).strip()
    row.admin_groups = str(payload.get("admin_groups", row.admin_groups)).strip()
    row.operator_groups = str(payload.get("operator_groups", row.operator_groups)).strip()
    row.default_role = default_role
    row.fallback_local = bool(payload.get("fallback_local", row.fallback_local))
    row.connect_timeout = timeout
    if "scope_mappings" in payload:
        from services.ldap_scope import validate_scope_mappings

        row.scope_mappings = validate_scope_mappings(payload.get("scope_mappings") or [])
    row.save()
    logger.info("ldap | настройки сохранены через UI (enabled=%s)", row.enabled)
    return get_config_public()


def test_connection(
    mode: str = "bind",
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> dict[str, Any]:
    cfg = get_config()
    if not cfg.server.strip():
        return {"ok": False, "message": "Укажите адрес LDAP-сервера"}

    if mode == "auth":
        if not username or not password:
            return {"ok": False, "message": "Укажите логин и пароль для проверки"}
        from services.ldap_auth import authenticate_ldap

        result = authenticate_ldap(username.strip(), password)
        if result:
            groups = len(result.get("groups") or [])
            ag = result.get("allowed_groups") or []
            ast = result.get("allowed_sites") or []
            scope = ""
            if ag or ast:
                scope = f", scope groups={ag or 'all'}, sites={ast or 'all'}"
            return {
                "ok": True,
                "message": f"Вход успешен, роль: {result['role']}, групп: {groups}{scope}",
                "role": result["role"],
                "allowed_groups": ag,
                "allowed_sites": ast,
            }
        return {"ok": False, "message": "LDAP: неверный логин или пароль"}

    if not cfg.bind_dn:
        return {"ok": False, "message": "Укажите Bind DN сервисной учётной записи"}

    bind_password = cfg.bind_password
    if not bind_password:
        return {"ok": False, "message": "Укажите пароль сервисной учётной записи"}

    try:
        from ldap3 import Connection, Server

        server = Server(
            cfg.server,
            use_ssl=cfg.use_ssl,
            connect_timeout=cfg.connect_timeout,
        )
        conn = Connection(
            server,
            user=cfg.bind_dn,
            password=bind_password,
            auto_bind=False,
            receive_timeout=cfg.connect_timeout,
        )
        if cfg.start_tls and not cfg.use_ssl:
            conn.open()
            conn.start_tls()
        if not conn.bind():
            desc = conn.result.get("description") or "bind failed"
            conn.unbind()
            return {"ok": False, "message": f"Bind не удался: {desc}"}
        conn.unbind()
        return {"ok": True, "message": "Подключение к LDAP и bind сервисной учётной записи успешны"}
    except Exception as exc:
        logger.warning("ldap | test bind failed: %s", exc)
        return {"ok": False, "message": str(exc)}
