"""LDAP authentication and role mapping."""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

LDAP_ENABLED = os.environ.get("LDAP_ENABLED", "").lower() in ("1", "true", "yes")
LDAP_SERVER = os.environ.get("LDAP_SERVER", "")
LDAP_USE_SSL = os.environ.get("LDAP_USE_SSL", "").lower() in ("1", "true", "yes")
LDAP_START_TLS = os.environ.get("LDAP_START_TLS", "").lower() in ("1", "true", "yes")
LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")
LDAP_USER_BASE = os.environ.get("LDAP_USER_BASE", "")
LDAP_USER_FILTER = os.environ.get("LDAP_USER_FILTER", "(uid={username})")
LDAP_USER_DN_TEMPLATE = os.environ.get("LDAP_USER_DN_TEMPLATE", "")
LDAP_USER_UPN_SUFFIX = os.environ.get("LDAP_USER_UPN_SUFFIX", "")
LDAP_ADMIN_GROUPS = os.environ.get("LDAP_ADMIN_GROUPS", "")
LDAP_OPERATOR_GROUPS = os.environ.get("LDAP_OPERATOR_GROUPS", "")
LDAP_DEFAULT_ROLE = os.environ.get("LDAP_DEFAULT_ROLE", "viewer")
LDAP_FALLBACK_LOCAL = os.environ.get("LDAP_FALLBACK_LOCAL", "true").lower() in (
    "1",
    "true",
    "yes",
)
LDAP_CONNECT_TIMEOUT = int(os.environ.get("LDAP_CONNECT_TIMEOUT", "10"))


def ldap_configured() -> bool:
    return LDAP_ENABLED and LDAP_SERVER.strip()


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


def _map_role_from_groups(member_of: list[str]) -> str:
    admin_groups = _parse_group_list(LDAP_ADMIN_GROUPS)
    operator_groups = _parse_group_list(LDAP_OPERATOR_GROUPS)

    if _group_matches(member_of, admin_groups):
        return "admin"
    if _group_matches(member_of, operator_groups):
        return "operator"

    default = LDAP_DEFAULT_ROLE.strip().lower()
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


def _build_user_bind_id(username: str) -> str:
    if LDAP_USER_DN_TEMPLATE:
        return LDAP_USER_DN_TEMPLATE.replace("{username}", username)
    if LDAP_USER_UPN_SUFFIX:
        suffix = LDAP_USER_UPN_SUFFIX
        if not suffix.startswith("@"):
            suffix = f"@{suffix}"
        return f"{username}{suffix}"
    return username


def _ldap_server():
    from ldap3 import Server

    return Server(
        LDAP_SERVER,
        use_ssl=LDAP_USE_SSL,
        connect_timeout=LDAP_CONNECT_TIMEOUT,
    )


def _search_user_dn(username: str) -> tuple[Optional[str], list[str]]:
    from ldap3 import Connection, SUBTREE

    if not LDAP_USER_BASE:
        logger.warning("ldap | LDAP_USER_BASE не задан")
        return None, []

    server = _ldap_server()
    search_filter = LDAP_USER_FILTER.replace("{username}", username)
    conn = Connection(
        server,
        user=LDAP_BIND_DN or None,
        password=LDAP_BIND_PASSWORD or None,
        auto_bind=True,
        receive_timeout=LDAP_CONNECT_TIMEOUT,
    )
    if LDAP_START_TLS and not LDAP_USE_SSL:
        conn.start_tls()

    ok = conn.search(
        LDAP_USER_BASE,
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


def _bind_as_user(bind_id: str, password: str) -> bool:
    from ldap3 import Connection

    server = _ldap_server()
    conn = Connection(
        server,
        user=bind_id,
        password=password,
        auto_bind=False,
        receive_timeout=LDAP_CONNECT_TIMEOUT,
    )
    if LDAP_START_TLS and not LDAP_USE_SSL:
        conn.open()
        conn.start_tls()

    if conn.bind():
        conn.unbind()
        return True
    logger.info("ldap | bind failed for %s: %s", bind_id, conn.result.get("description"))
    conn.unbind()
    return False


def authenticate_ldap(username: str, password: str) -> Optional[dict]:
    """Проверка LDAP. Возвращает {username, role} или None."""
    if not ldap_configured():
        return None
    if not username or not password:
        return None

    username = username.strip()
    member_of: list[str] = []

    try:
        if LDAP_BIND_DN and LDAP_USER_BASE:
            user_dn, member_of = _search_user_dn(username)
            if not user_dn:
                logger.info("ldap | пользователь не найден: %s", username)
                return None
            if not _bind_as_user(user_dn, password):
                return None
        else:
            bind_id = _build_user_bind_id(username)
            if not _bind_as_user(bind_id, password):
                return None
            if LDAP_BIND_DN and LDAP_USER_BASE:
                _, member_of = _search_user_dn(username)

        role = _map_role_from_groups(member_of)
        logger.info("ldap | вход %s, role=%s, groups=%d", username, role, len(member_of))
        return {"username": username, "role": role, "groups": member_of}
    except Exception as exc:
        logger.warning("ldap | ошибка для %s: %s", username, exc)
        return None


def auth_methods() -> dict:
    return {
        "ldap_enabled": ldap_configured(),
        "local_enabled": not ldap_configured() or LDAP_FALLBACK_LOCAL,
    }
