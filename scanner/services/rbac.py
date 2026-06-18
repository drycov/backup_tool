"""RBAC: роли, права и метаданные для API/UI."""

from typing import Iterable

ROLE_VIEWER = "viewer"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"
VALID_ROLES = {ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN}

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
PERMISSION_API_KEYS_MANAGE = "api_keys:manage"
PERMISSION_SETTINGS_READ = "settings:read"

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
    PERMISSION_API_KEYS_MANAGE: "API keys — управление",
    PERMISSION_SETTINGS_READ: "Настройки — чтение",
}

ROLE_LABELS: dict[str, str] = {
    ROLE_VIEWER: "Наблюдатель",
    ROLE_OPERATOR: "Оператор",
    ROLE_ADMIN: "Администратор",
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    ROLE_VIEWER: "Дашборд, инвентарь и Oxidized только для чтения",
    ROLE_OPERATOR: "Сканирование, устройства, бэкапы Oxidized",
    ROLE_ADMIN: "Полный доступ, включая пароли и пользователи",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_VIEWER: {
        PERMISSION_VIEW_INVENTORY,
        PERMISSION_SCAN_READ,
        PERMISSION_OXIDIZED_READ,
        PERMISSION_COMPLIANCE_READ,
        PERMISSION_SETTINGS_READ,
    },
    ROLE_OPERATOR: {
        PERMISSION_VIEW_INVENTORY,
        PERMISSION_EDIT_DEVICES,
        PERMISSION_SCAN_READ,
        PERMISSION_RUN_SCAN,
        PERMISSION_OXIDIZED_READ,
        PERMISSION_OXIDIZED_WRITE,
        PERMISSION_COMPLIANCE_READ,
        PERMISSION_SETTINGS_NOTIFY,
        PERMISSION_SETTINGS_READ,
    },
    ROLE_ADMIN: set(PERMISSION_LABELS.keys()),
}

ROLE_RANK: dict[str, int] = {
    ROLE_VIEWER: 1,
    ROLE_OPERATOR: 2,
    ROLE_ADMIN: 3,
}


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


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
    for role_id in (ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN):
        perms = ROLE_PERMISSIONS.get(role_id, set())
        roles.append(
            {
                "id": role_id,
                "label": ROLE_LABELS[role_id],
                "description": ROLE_DESCRIPTIONS[role_id],
                "rank": ROLE_RANK[role_id],
                "permissions": sorted(perms),
            }
        )
    return {"roles": roles, "permissions": permissions}
