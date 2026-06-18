"""CRUD пользовательских ролей RBAC."""

from __future__ import annotations

import logging
import re
from typing import Any

from core.models import CustomRole, User
from services.database import is_database_available, require_database
from services.rbac import PERMISSION_LABELS, ROLE_COMPLIANCE_AUDITOR, permissions_for_role

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")


def _validate_permissions(perms: list[str]) -> list[str]:
    unknown = [p for p in perms if p not in PERMISSION_LABELS]
    if unknown:
        raise ValueError(f"Неизвестные permissions: {', '.join(unknown)}")
    return sorted(set(perms))


def _public_row(row: CustomRole) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "label": row.label,
        "description": row.description or "",
        "permissions": list(row.permissions or []),
        "is_system": bool(row.is_system),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def seed_system_roles() -> None:
    if not is_database_available():
        return
    CustomRole.objects.get_or_create(
        slug=ROLE_COMPLIANCE_AUDITOR,
        defaults={
            "label": "Аудитор compliance",
            "description": "Только просмотр compliance и журнала аудита",
            "permissions": permissions_for_role(ROLE_COMPLIANCE_AUDITOR),
            "is_system": True,
        },
    )


def list_custom_roles() -> list[dict[str, Any]]:
    if not is_database_available():
        return []
    return [_public_row(r) for r in CustomRole.objects.all()]


def create_custom_role(
    *,
    slug: str,
    label: str,
    description: str = "",
    permissions: list[str],
) -> dict[str, Any]:
    require_database("Custom roles требуют базу данных")
    slug = slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError("slug: латиница, 2–63 символа, a-z0-9_-")
    if slug in ("viewer", "operator", "admin", ROLE_COMPLIANCE_AUDITOR):
        raise ValueError("slug зарезервирован для встроенной роли")
    if CustomRole.objects.filter(slug=slug).exists():
        raise ValueError(f"Роль '{slug}' уже существует")
    perms = _validate_permissions(permissions)
    row = CustomRole.objects.create(
        slug=slug,
        label=label.strip() or slug,
        description=(description or "").strip(),
        permissions=perms,
    )
    logger.info("custom_role | created | slug=%s", slug)
    return _public_row(row)


def update_custom_role(
    role_id: int,
    *,
    label: str | None = None,
    description: str | None = None,
    permissions: list[str] | None = None,
) -> dict[str, Any]:
    require_database("Custom roles требуют базу данных")
    row = CustomRole.objects.filter(id=role_id).first()
    if not row:
        raise ValueError("Роль не найдена")
    if label is not None:
        row.label = label.strip() or row.slug
    if description is not None:
        row.description = description.strip()
    if permissions is not None:
        row.permissions = _validate_permissions(permissions)
    row.save()
    logger.info("custom_role | updated | slug=%s", row.slug)
    return _public_row(row)


def delete_custom_role(role_id: int) -> None:
    require_database("Custom roles требуют базу данных")
    row = CustomRole.objects.filter(id=role_id).first()
    if not row:
        raise ValueError("Роль не найдена")
    if row.is_system:
        raise ValueError("Системную роль нельзя удалить")
    if User.objects.filter(custom_role=row).exists():
        raise ValueError("Роль назначена пользователям — снимите назначение")
    row.delete()
    logger.info("custom_role | deleted | slug=%s", row.slug)
