"""RBAC: роли, права и метаданные для API/UI."""

from typing import Iterable

ROLE_VIEWER = "viewer"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"
ROLE_COMPLIANCE_AUDITOR = "compliance_auditor"
VALID_ROLES = {ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN, ROLE_COMPLIANCE_AUDITOR}

PERMISSION_VIEW_INVENTORY = "inventory:read"
PERMISSION_EDIT_DEVICES = "inventory:devices"
PERMISSION_EDIT_INVENTORY = "inventory:write"
PERMISSION_VIEW_CREDENTIALS = "credentials:read"
PERMISSION_EDIT_CREDENTIALS = "credentials:write"
PERMISSION_SCAN_READ = "scan:read"
PERMISSION_RUN_SCAN = "scan:run"
PERMISSION_OXIDIZED_READ = "oxidized:read"
PERMISSION_OXIDIZED_WRITE = "oxidized:write"
PERMISSION_MANAGE_USERS = "users:manage"
PERMISSION_COMPLIANCE_READ = "compliance:read"
PERMISSION_SETTINGS_NOTIFY = "settings:notify"
PERMISSION_AUDIT_READ = "audit:read"
PERMISSION_SECURITY_READ = "security:read"
PERMISSION_SECURITY_RUN = "security:run"
PERMISSION_API_KEYS_MANAGE = "api_keys:manage"
PERMISSION_SETTINGS_READ = "settings:read"
PERMISSION_PROVISION_READ = "provision:read"
PERMISSION_PROVISION_RUN = "provision:run"

PERMISSION_LABELS: dict[str, str] = {
    PERMISSION_VIEW_INVENTORY: "Инвентарь — чтение",
    PERMISSION_EDIT_DEVICES: "Устройства — добавление/изменение",
    PERMISSION_EDIT_INVENTORY: "Инвентарь — полное редактирование",
    PERMISSION_VIEW_CREDENTIALS: "Пароли SSH — просмотр",
    PERMISSION_EDIT_CREDENTIALS: "Пароли SSH — редактирование",
    PERMISSION_SCAN_READ: "Сканирование — результаты",
    PERMISSION_RUN_SCAN: "Сканирование — запуск",
    PERMISSION_OXIDIZED_READ: "Oxidized — чтение",
    PERMISSION_OXIDIZED_WRITE: "Oxidized — fetch/sync",
    PERMISSION_MANAGE_USERS: "Пользователи — управление",
    PERMISSION_COMPLIANCE_READ: "Compliance — чтение и экспорт",
    PERMISSION_SETTINGS_NOTIFY: "Настройки — тест уведомлений",
    PERMISSION_AUDIT_READ: "Аудит — чтение и экспорт",
    PERMISSION_SECURITY_READ: "Безопасность конфигов — чтение",
    PERMISSION_SECURITY_RUN: "Безопасность конфигов — запуск аудита",
    PERMISSION_API_KEYS_MANAGE: "API keys — управление",
    PERMISSION_SETTINGS_READ: "Настройки — чтение",
    PERMISSION_PROVISION_READ: "Провижионинг — шаблоны и preview",
    PERMISSION_PROVISION_RUN: "Провижионинг — применение на устройства",
}

ROLE_LABELS: dict[str, str] = {
    ROLE_VIEWER: "Наблюдатель",
    ROLE_OPERATOR: "Оператор",
    ROLE_ADMIN: "Администратор",
    ROLE_COMPLIANCE_AUDITOR: "Аудитор compliance",
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    ROLE_VIEWER: "Дашборд, инвентарь и Oxidized только для чтения",
    ROLE_OPERATOR: "Сканирование, устройства, бэкапы Oxidized",
    ROLE_ADMIN: "Полный доступ, включая пароли и пользователи",
    ROLE_COMPLIANCE_AUDITOR: "Compliance dashboard и журнал аудита (read-only)",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_VIEWER: {
        PERMISSION_VIEW_INVENTORY,
        PERMISSION_SCAN_READ,
        PERMISSION_OXIDIZED_READ,
        PERMISSION_COMPLIANCE_READ,
        PERMISSION_SECURITY_READ,
        PERMISSION_SETTINGS_READ,
        PERMISSION_PROVISION_READ,
    },
    ROLE_COMPLIANCE_AUDITOR: {
        PERMISSION_COMPLIANCE_READ,
        PERMISSION_AUDIT_READ,
    },
    ROLE_OPERATOR: {
        PERMISSION_VIEW_INVENTORY,
        PERMISSION_EDIT_DEVICES,
        PERMISSION_SCAN_READ,
        PERMISSION_RUN_SCAN,
        PERMISSION_OXIDIZED_READ,
        PERMISSION_OXIDIZED_WRITE,
        PERMISSION_COMPLIANCE_READ,
        PERMISSION_SECURITY_READ,
        PERMISSION_SECURITY_RUN,
        PERMISSION_SETTINGS_NOTIFY,
        PERMISSION_SETTINGS_READ,
        PERMISSION_PROVISION_READ,
        PERMISSION_PROVISION_RUN,
    },
    ROLE_ADMIN: set(PERMISSION_LABELS.keys()),
}

ROLE_RANK: dict[str, int] = {
    ROLE_VIEWER: 1,
    ROLE_COMPLIANCE_AUDITOR: 1,
    ROLE_OPERATOR: 2,
    ROLE_ADMIN: 3,
}


def permissions_for_user(user) -> set[str]:
    custom_role = getattr(user, "custom_role", None)
    if custom_role is not None and getattr(custom_role, "permissions", None) is not None:
        return set(custom_role.permissions or [])
    return ROLE_PERMISSIONS.get(getattr(user, "role", ""), set())


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def user_has_role_permission(user, permission: str) -> bool:
    return permission in permissions_for_user(user)


def has_any_permission(role: str, permissions: Iterable[str]) -> bool:
    role_perms = ROLE_PERMISSIONS.get(role, set())
    return any(p in role_perms for p in permissions)


def permissions_for_role(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, set()))


def rbac_matrix() -> dict:
    permissions = [
        {"id": pid, "label": PERMISSION_LABELS[pid]}
        for pid in sorted(PERMISSION_LABELS.keys())
    ]
    roles = []
    for role_id in (ROLE_VIEWER, ROLE_COMPLIANCE_AUDITOR, ROLE_OPERATOR, ROLE_ADMIN):
        perms = ROLE_PERMISSIONS.get(role_id, set())
        roles.append(
            {
                "id": role_id,
                "label": ROLE_LABELS[role_id],
                "description": ROLE_DESCRIPTIONS[role_id],
                "rank": ROLE_RANK[role_id],
                "permissions": sorted(perms),
                "builtin": True,
            }
        )
    try:
        from services.custom_roles import list_custom_roles

        for row in list_custom_roles():
            roles.append(
                {
                    "id": f"custom:{row['slug']}",
                    "slug": row["slug"],
                    "label": row["label"],
                    "description": row.get("description") or "",
                    "rank": 1,
                    "permissions": row.get("permissions") or [],
                    "builtin": False,
                    "is_system": row.get("is_system", False),
                }
            )
    except Exception:
        pass
    return {"roles": roles, "permissions": permissions}
