"""LDAP / Active Directory authentication and role mapping."""

import logging
from typing import Optional

from services.ldap_settings import LdapConfigData, get_config, ldap_configured

logger = logging.getLogger(__name__)


def _parse_group_list(raw: str) -> list[str]:
    return [g.strip().lower() for g in raw.split(",") if g.strip()]


def _group_matches(member_values: list[str], configured: list[str]) -> bool:
    if not configured:
        return False
    normalized = [m.lower() for m in member_values if m]
    for member in normalized:
        for needle in configured:
            if member == needle or needle in member:
                return True
    return False


def _map_role_from_groups(cfg: LdapConfigData, member_of: list[str]) -> str:
    admin_groups = _parse_group_list(cfg.admin_groups)
    operator_groups = _parse_group_list(cfg.operator_groups)

    if _group_matches(member_of, admin_groups):
        return "admin"
    if _group_matches(member_of, operator_groups):
        return "operator"

    default = cfg.default_role.strip().lower()
    if default in ("viewer", "operator", "admin"):
        return default
    return "viewer"


def _extract_member_of(entry) -> list[str]:
    values: list[str] = []
    if not hasattr(entry, "memberOf"):
        return values
    raw = entry.memberOf
    if raw is None:
        return values
    if isinstance(raw, list):
        for item in raw:
            values.append(str(item))
    else:
        values.append(str(raw))
    return values


def _build_user_bind_id(cfg: LdapConfigData, username: str) -> str:
    if cfg.user_dn_template:
        return cfg.user_dn_template.replace("{username}", username)
    if cfg.user_upn_suffix:
        suffix = cfg.user_upn_suffix
        if not suffix.startswith("@"):
            suffix = f"@{suffix}"
        return f"{username}{suffix}"
    return username


def _ldap_server(cfg: LdapConfigData):
    from ldap3 import Server

    return Server(
        cfg.server,
        use_ssl=cfg.use_ssl,
        connect_timeout=cfg.connect_timeout,
    )


def _search_user_dn(cfg: LdapConfigData, username: str) -> tuple[Optional[str], list[str]]:
    from ldap3 import Connection, SUBTREE

    if not cfg.user_base:
        logger.warning("ldap | user_base не задан")
        return None, []

    server = _ldap_server(cfg)
    search_filter = cfg.user_filter.replace("{username}", username)
    conn = Connection(
        server,
        user=cfg.bind_dn or None,
        password=cfg.bind_password or None,
        auto_bind=True,
        receive_timeout=cfg.connect_timeout,
    )
    if cfg.start_tls and not cfg.use_ssl:
        conn.start_tls()

    ok = conn.search(
        cfg.user_base,
        search_filter,
        search_scope=SUBTREE,
        attributes=["memberOf", "cn", "sAMAccountName"],
    )
    if not ok or not conn.entries:
        conn.unbind()
        return None, []

    entry = conn.entries[0]
    user_dn = entry.entry_dn
    member_of = _extract_member_of(entry)
    conn.unbind()
    return user_dn, member_of


def _bind_as_user(cfg: LdapConfigData, bind_id: str, password: str) -> bool:
    from ldap3 import Connection

    server = _ldap_server(cfg)
    conn = Connection(
        server,
        user=bind_id,
        password=password,
        auto_bind=False,
        receive_timeout=cfg.connect_timeout,
    )
    if cfg.start_tls and not cfg.use_ssl:
        conn.open()
        conn.start_tls()

    if conn.bind():
        conn.unbind()
        return True
    logger.info("ldap | bind failed for %s: %s", bind_id, conn.result.get("description"))
    conn.unbind()
    return False


def authenticate_ldap(username: str, password: str) -> Optional[dict]:
    """Проверка LDAP. Возвращает {username, role, groups} или None."""
    if not ldap_configured():
        return None
    if not username or not password:
        return None

    cfg = get_config()
    username = username.strip()
    member_of: list[str] = []

    try:
        if cfg.bind_dn and cfg.user_base:
            user_dn, member_of = _search_user_dn(cfg, username)
            if not user_dn:
                logger.info("ldap | пользователь не найден: %s", username)
                return None
            if not _bind_as_user(cfg, user_dn, password):
                return None
        else:
            bind_id = _build_user_bind_id(cfg, username)
            if not _bind_as_user(cfg, bind_id, password):
                return None
            if cfg.bind_dn and cfg.user_base:
                _, member_of = _search_user_dn(cfg, username)

        role = _map_role_from_groups(cfg, member_of)
        logger.info("ldap | вход %s, role=%s, groups=%d", username, role, len(member_of))
        return {"username": username, "role": role, "groups": member_of}
    except Exception as exc:
        logger.warning("ldap | ошибка для %s: %s", username, exc)
        return None


def auth_methods() -> dict:
    cfg = get_config()
    configured = ldap_configured()
    return {
        "ldap_enabled": configured,
        "local_enabled": not configured or cfg.fallback_local,
        "directory_type": cfg.directory_type if configured else None,
    }
