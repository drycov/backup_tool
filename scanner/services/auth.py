import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from django.conf import settings

from core.models import User
from services.rbac import ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER, VALID_ROLES, has_permission

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


def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
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
    return User.objects.filter(id=user_id).first()


def get_user_by_username(username: str) -> Optional[User]:
    return User.objects.filter(username=username).first()


def authenticate_user(username: str, password: str) -> Optional[User]:
    from services.ldap_auth import authenticate_ldap, ldap_configured
    from services.ldap_settings import get_config

    if ldap_configured():
        ldap_info = authenticate_ldap(username, password)
        if ldap_info:
            return upsert_ldap_user(ldap_info["username"], ldap_info["role"])
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


def upsert_ldap_user(username: str, role: str) -> User:
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
        },
    )
    if not created:
        user.auth_source = "ldap"
        user.role = role
        user.is_active = True
        user.password_hash = placeholder_hash
        user.save()
    return user


def seed_default_admin() -> None:
    password = settings.ADMIN_PASSWORD or "changeme"
    username = settings.ADMIN_USERNAME

    if not User.objects.exists():
        if not settings.ADMIN_PASSWORD:
            logger.warning(
                "auth | ADMIN_PASSWORD не задан — создан %s / changeme",
                username,
            )
        User.objects.create(
            username=username,
            password_hash=hash_password(password),
            role=ROLE_ADMIN,
            is_active=True,
            auth_source="local",
        )
        logger.info("auth | создан администратор: %s", username)
        return

    env_admin = get_user_by_username(username)
    if env_admin and settings.ADMIN_PASSWORD and env_admin.auth_source != "ldap":
        env_admin.password_hash = hash_password(settings.ADMIN_PASSWORD)
        env_admin.role = ROLE_ADMIN
        env_admin.is_active = True
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
        )
        logger.info("auth | создан администратор из .env: %s", username)


def list_users() -> list[User]:
    return list(User.objects.order_by("id"))


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
    if password and user.auth_source == "ldap":
        raise ValueError("LDAP-пользователи не могут иметь локальный пароль")
    if password:
        user.password_hash = hash_password(password)
    user.save()
    return user


def delete_user(user_id: int) -> None:
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    user.delete()


def user_has_permission(user: User, permission: str) -> bool:
    return has_permission(user.role, permission)
