"""API keys — аутентификация для CI/Ansible."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from core.models import ApiKey, User
from services.database import is_database_available, require_database
from services.rbac import ROLE_VIEWER, VALID_ROLES, has_permission

logger = logging.getLogger(__name__)

KEY_PREFIX = "bk_"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _display_prefix(raw_key: str) -> str:
    return raw_key[:12]


def create_api_key(
    *,
    name: str,
    role: str = ROLE_VIEWER,
    permissions: list[str] | None = None,
    allowed_groups: list[str] | None = None,
    allowed_sites: list[str] | None = None,
    expires_at: datetime | None = None,
    created_by: str = "",
) -> tuple[ApiKey, str]:
    require_database("API keys требуют базу данных")
    name = name.strip()
    if not name:
        raise ValueError("Имя ключа обязательно")
    if ApiKey.objects.filter(name=name).exists():
        raise ValueError(f"Ключ '{name}' уже существует")
    if role not in VALID_ROLES:
        raise ValueError(f"Недопустимая роль: {role}")

    raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
    row = ApiKey.objects.create(
        name=name,
        key_prefix=_display_prefix(raw_key),
        key_hash=_hash_key(raw_key),
        role=role,
        permissions=permissions or [],
        allowed_groups=allowed_groups or [],
        allowed_sites=allowed_sites or [],
        expires_at=expires_at,
        created_by=created_by[:64],
    )
    logger.info("api_key | created | name=%s role=%s", name, role)
    return row, raw_key


def list_api_keys() -> list[dict[str, Any]]:
    if not is_database_available():
        return []
    return [_public_row(k) for k in ApiKey.objects.all()]


def _public_row(row: ApiKey) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "key_prefix": row.key_prefix,
        "role": row.role,
        "permissions": row.permissions or [],
        "allowed_groups": row.allowed_groups or [],
        "allowed_sites": row.allowed_sites or [],
        "is_active": row.is_active,
        "last_used_at": row.last_used_at,
        "expires_at": row.expires_at,
        "created_by": row.created_by,
        "created_at": row.created_at,
    }


def revoke_api_key(key_id: int) -> None:
    require_database("API keys требуют базу данных")
    row = ApiKey.objects.filter(id=key_id).first()
    if not row:
        raise ValueError("Ключ не найден")
    row.is_active = False
    row.save(update_fields=["is_active"])
    logger.info("api_key | revoked | name=%s", row.name)


def delete_api_key(key_id: int) -> None:
    require_database("API keys требуют базу данных")
    deleted, _ = ApiKey.objects.filter(id=key_id).delete()
    if not deleted:
        raise ValueError("Ключ не найден")


def authenticate_api_key(raw_key: str) -> Optional[User]:
    """Проверить ключ и вернуть synthetic User для request.api_user."""
    if not raw_key or not raw_key.startswith(KEY_PREFIX):
        return None
    if not is_database_available():
        return None

    key_hash = _hash_key(raw_key.strip())
    row = ApiKey.objects.filter(key_hash=key_hash, is_active=True).first()
    if not row:
        return None

    now = datetime.now(timezone.utc)
    if row.expires_at:
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            return None

    row.last_used_at = now
    row.save(update_fields=["last_used_at"])

    user = User(
        id=-row.id,
        username=f"apikey:{row.name}",
        role=row.role,
        is_active=True,
        auth_source="apikey",
        allowed_groups=row.allowed_groups or [],
        allowed_sites=row.allowed_sites or [],
    )
    user._api_key_permissions = list(row.permissions or [])  # noqa: SLF001
    user._api_key_id = row.id  # noqa: SLF001
    return user


def api_key_has_permission(user: User, permission: str) -> bool:
    override = getattr(user, "_api_key_permissions", None)
    if override:
        return permission in override
    return has_permission(user.role, permission)
