import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from django.conf import settings

from core.models import User
from services.rbac import ROLE_ADMIN, ROLE_VIEWER, VALID_ROLES, has_permission

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"

PERMISSION_VIEW_INVENTORY = "inventory:read"
PERMISSION_EDIT_DEVICES = "inventory:devices"
PERMISSION_EDIT_INVENTORY = "inventory:write"
PERMISSION_VIEW_CREDENTIALS = "credentials:read"
PERMISSION_EDIT_CREDENTIALS = "credentials:write"
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


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def permissions_for_role(role: str) -> list[str]:
    from services.rbac import permissions_for_role as _perms

    return _perms(role)


def user_permissions(user: User) -> list[str]:
    from services.rbac import permissions_for_user

    return sorted(permissions_for_user(user))


def create_access_token(user_id: int, username: str, role: str) -> str:
    from services.system_settings import get_config

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=get_config().access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise ValueError("Сессия истекла или токен недействителен") from exc


def get_user_by_id(user_id: int) -> Optional[User]:
    return User.objects.select_related("custom_role").filter(id=user_id).first()


def get_user_by_username(username: str) -> Optional[User]:
    return User.objects.select_related("custom_role").filter(username=username).first()


def authenticate_user(username: str, password: str) -> Optional[User]:
    from services.ldap_auth import authenticate_ldap, ldap_configured
    from services.ldap_settings import get_config

    if ldap_configured():
        ldap_info = authenticate_ldap(username, password)
        if ldap_info:
            return upsert_ldap_user(
                ldap_info["username"],
                ldap_info["role"],
                allowed_groups=ldap_info.get("allowed_groups"),
                allowed_sites=ldap_info.get("allowed_sites"),
            )
        if not get_config().fallback_local:
            return None

    user = get_user_by_username(username)
    if not user or not user.is_active:
        return None
    if user.auth_source == "ldap":
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def upsert_ldap_user(
    username: str,
    role: str,
    *,
    allowed_groups: list[str] | None = None,
    allowed_sites: list[str] | None = None,
) -> User:
    if role not in VALID_ROLES:
        role = ROLE_VIEWER
    placeholder_hash = hash_password(secrets.token_hex(32))
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "password_hash": placeholder_hash,
            "role": role,
            "is_active": True,
            "auth_source": "ldap",
            "allowed_groups": allowed_groups or [],
            "allowed_sites": allowed_sites or [],
        },
    )
    if not created:
        user.auth_source = "ldap"
        if not getattr(user, "role_locked", False):
            user.role = role
        if not getattr(user, "scope_locked", False):
            if allowed_groups is not None:
                user.allowed_groups = allowed_groups
            if allowed_sites is not None:
                user.allowed_sites = allowed_sites
        user.is_active = True
        user.password_hash = placeholder_hash
        user.save()
    return user


def seed_default_admin() -> None:
    password = settings.ADMIN_PASSWORD or "changeme"
    username = settings.ADMIN_USERNAME
    default_password = not settings.ADMIN_PASSWORD

    if not User.objects.exists():
        if default_password:
            logger.warning(
                "auth | ADMIN_PASSWORD не задан — создан %s / changeme (смена при первом входе)",
                username,
            )
        User.objects.create(
            username=username,
            password_hash=hash_password(password),
            role=ROLE_ADMIN,
            is_active=True,
            auth_source="local",
            must_change_password=default_password,
        )
        logger.info("auth | создан администратор: %s", username)
        return

    env_admin = get_user_by_username(username)
    if env_admin and settings.ADMIN_PASSWORD and env_admin.auth_source != "ldap":
        env_admin.password_hash = hash_password(settings.ADMIN_PASSWORD)
        env_admin.role = ROLE_ADMIN
        env_admin.is_active = True
        env_admin.must_change_password = False
        env_admin.save()
        logger.info("auth | учётная запись %s синхронизирована из .env", username)
        return

    if not env_admin and settings.ADMIN_PASSWORD:
        User.objects.create(
            username=username,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            role=ROLE_ADMIN,
            is_active=True,
            auth_source="local",
            must_change_password=False,
        )
        logger.info("auth | создан администратор из .env: %s", username)


def change_password(user: User, current_password: str, new_password: str) -> None:
    if user.auth_source == "ldap":
        raise ValueError("Смена пароля недоступна для LDAP-пользователей")
    if not verify_password(current_password, user.password_hash):
        raise ValueError("Неверный текущий пароль")
    if len(new_password) < 8:
        raise ValueError("Новый пароль должен быть не короче 8 символов")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.save(update_fields=["password_hash", "must_change_password"])


def list_users() -> list[User]:
    return list(User.objects.select_related("custom_role").order_by("id"))


def user_public_dict(user: User) -> dict:
    from services.object_scope import scope_public
    from services.rbac import permissions_for_user

    custom_role = None
    if getattr(user, "custom_role_id", None) and user.custom_role:
        custom_role = {
            "id": user.custom_role.id,
            "slug": user.custom_role.slug,
            "label": user.custom_role.label,
        }
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "auth_source": user.auth_source or "local",
        "role_locked": bool(getattr(user, "role_locked", False)),
        "scope_locked": bool(getattr(user, "scope_locked", False)),
        "custom_role_id": user.custom_role_id,
        "custom_role": custom_role,
        "permissions": sorted(permissions_for_user(user)),
        **scope_public(user),
    }


def create_user(username: str, password: str, role: str) -> User:
    if role not in VALID_ROLES:
        raise ValueError(f"Недопустимая роль: {role}")
    if get_user_by_username(username):
        raise ValueError("Пользователь уже существует")
    return User.objects.create(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        auth_source="local",
    )


def update_user(
    user_id: int,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    password: Optional[str] = None,
    role_locked: Optional[bool] = None,
    scope_locked: Optional[bool] = None,
    allowed_groups: Optional[list[str]] = None,
    allowed_sites: Optional[list[str]] = None,
    custom_role_id: Optional[int] = None,
    clear_custom_role: bool = False,
) -> User:
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    if role is not None:
        if role not in VALID_ROLES:
            raise ValueError(f"Недопустимая роль: {role}")
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if role_locked is not None:
        user.role_locked = role_locked
    if scope_locked is not None:
        user.scope_locked = scope_locked
    if password and user.auth_source == "ldap":
        raise ValueError("LDAP-пользователи не могут иметь локальный пароль")
    if password:
        user.password_hash = hash_password(password)
    if allowed_groups is not None:
        user.allowed_groups = [g.strip() for g in allowed_groups if str(g).strip()]
    if allowed_sites is not None:
        user.allowed_sites = [s.strip() for s in allowed_sites if str(s).strip()]
    if clear_custom_role:
        user.custom_role_id = None
    elif custom_role_id is not None:
        from core.models import CustomRole

        if custom_role_id == 0:
            user.custom_role_id = None
        else:
            cr = CustomRole.objects.filter(id=custom_role_id).first()
            if not cr:
                raise ValueError("Пользовательская роль не найдена")
            user.custom_role_id = cr.id
    user.save()
    return get_user_by_id(user.id) or user


def delete_user(user_id: int) -> None:
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    user.delete()


def user_has_permission(user: User, permission: str) -> bool:
    if getattr(user, "auth_source", "") == "apikey":
        from services.api_keys import api_key_has_permission

        return api_key_has_permission(user, permission)
    from services.rbac import user_has_role_permission

    return user_has_role_permission(user, permission)
