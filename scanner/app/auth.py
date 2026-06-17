import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session

from .db import User, get_session, engine
from .rbac import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    VALID_ROLES,
    PERMISSION_VIEW_CREDENTIALS,
    PERMISSION_EDIT_CREDENTIALS,
    PERMISSION_VIEW_INVENTORY,
    PERMISSION_EDIT_DEVICES,
    PERMISSION_EDIT_INVENTORY,
    PERMISSION_SCAN_READ,
    PERMISSION_RUN_SCAN,
    PERMISSION_OXIDIZED_READ,
    PERMISSION_OXIDIZED_WRITE,
    PERMISSION_MANAGE_USERS,
    has_permission,
    has_any_permission,
    permissions_for_role,
    rbac_matrix,
)

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
AUTH_COOKIE_NAME = os.environ.get("AUTH_COOKIE_NAME", "backup_tools_token")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла или токен недействителен",
        )


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    return session.query(User).filter(User.id == user_id).first()


def get_user_by_username(session: Session, username: str) -> Optional[User]:
    return session.query(User).filter(User.username == username).first()


def count_active_admins(session: Session, exclude_id: Optional[int] = None) -> int:
    q = session.query(User).filter(User.role == ROLE_ADMIN, User.is_active.is_(True))
    if exclude_id is not None:
        q = q.filter(User.id != exclude_id)
    return q.count()


def authenticate_user(session: Session, username: str, password: str) -> Optional[User]:
    from .ldap_auth import authenticate_ldap, ldap_configured, LDAP_FALLBACK_LOCAL

    if ldap_configured():
        ldap_info = authenticate_ldap(username, password)
        if ldap_info:
            return upsert_ldap_user(session, ldap_info["username"], ldap_info["role"])
        if not LDAP_FALLBACK_LOCAL:
            return None

    user = get_user_by_username(session, username)
    if not user or not user.is_active:
        return None
    if getattr(user, "auth_source", "local") == "ldap":
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def upsert_ldap_user(session: Session, username: str, role: str) -> User:
    if role not in VALID_ROLES:
        role = ROLE_VIEWER
    user = get_user_by_username(session, username)
    placeholder_hash = hash_password(secrets.token_hex(32))
    if user:
        user.auth_source = "ldap"
        if not getattr(user, "role_locked", False):
            user.role = role
        user.is_active = True
        user.password_hash = placeholder_hash
    else:
        user = User(
            username=username,
            password_hash=placeholder_hash,
            role=role,
            is_active=True,
            auth_source="ldap",
            role_locked=False,
        )
        session.add(user)
    session.commit()
    session.refresh(user)
    session.expunge(user)
    return user


def migrate_auth_schema() -> None:
    from sqlalchemy import text

    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_source VARCHAR(16) DEFAULT 'local'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role_locked BOOLEAN DEFAULT FALSE",
    ]
    with engine.connect() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.commit()


def seed_default_admin() -> None:
    migrate_auth_schema()
    password = ADMIN_PASSWORD or "changeme"
    with get_session() as session:
        user_count = session.query(User).count()
        env_admin = get_user_by_username(session, ADMIN_USERNAME)

        if user_count == 0:
            if not ADMIN_PASSWORD:
                logger.warning(
                    "auth | ADMIN_PASSWORD не задан — создан %s / changeme",
                    ADMIN_USERNAME,
                )
            session.add(
                User(
                    username=ADMIN_USERNAME,
                    password_hash=hash_password(password),
                    role=ROLE_ADMIN,
                    is_active=True,
                    auth_source="local",
                    role_locked=False,
                )
            )
            session.commit()
            logger.info("auth | создан администратор: %s", ADMIN_USERNAME)
            return

        if env_admin and ADMIN_PASSWORD and env_admin.auth_source != "ldap":
            env_admin.password_hash = hash_password(ADMIN_PASSWORD)
            env_admin.role = ROLE_ADMIN
            env_admin.is_active = True
            session.commit()
            logger.info("auth | учётная запись %s синхронизирована из .env", ADMIN_USERNAME)
            return

        if not env_admin and ADMIN_PASSWORD:
            session.add(
                User(
                    username=ADMIN_USERNAME,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role=ROLE_ADMIN,
                    is_active=True,
                    auth_source="local",
                    role_locked=False,
                )
            )
            session.commit()
            logger.info("auth | создан администратор из .env: %s", ADMIN_USERNAME)


def _token_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется вход в систему",
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    token = _token_from_request(request, credentials)
    payload = _decode_token(token)
    user_id = int(payload.get("sub", "0"))
    with get_session() as session:
        user = get_user_by_id(session, user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден или отключён",
            )
        session.expunge(user)
        return user


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def require_permission(permission: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return user

    return checker


def require_any_permission(*permissions: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if not has_any_permission(user.role, permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return user

    return checker


def list_users() -> list[User]:
    with get_session() as session:
        users = session.query(User).order_by(User.id).all()
        for user in users:
            session.expunge(user)
        return users


def create_user(username: str, password: str, role: str) -> User:
    if role not in VALID_ROLES:
        raise ValueError(f"Недопустимая роль: {role}")
    with get_session() as session:
        if get_user_by_username(session, username):
            raise ValueError("Пользователь уже существует")
        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            auth_source="local",
            role_locked=False,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user


def update_user(
    user_id: int,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    password: Optional[str] = None,
    role_locked: Optional[bool] = None,
) -> User:
    with get_session() as session:
        user = get_user_by_id(session, user_id)
        if not user:
            raise ValueError("Пользователь не найден")

        if role is not None:
            if role not in VALID_ROLES:
                raise ValueError(f"Недопустимая роль: {role}")
            if user.role == ROLE_ADMIN and role != ROLE_ADMIN:
                if count_active_admins(session, exclude_id=user.id) == 0:
                    raise ValueError("Нельзя убрать роль admin у последнего администратора")
            user.role = role
            if user.auth_source == "ldap":
                user.role_locked = True

        if role_locked is not None:
            user.role_locked = role_locked

        if is_active is not None:
            if not is_active and user.role == ROLE_ADMIN:
                if count_active_admins(session, exclude_id=user.id) == 0:
                    raise ValueError("Нельзя отключить последнего администратора")
            user.is_active = is_active

        if password and getattr(user, "auth_source", "local") == "ldap":
            raise ValueError("LDAP-пользователи не могут иметь локальный пароль")
        if password:
            user.password_hash = hash_password(password)

        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user


def delete_user(user_id: int) -> None:
    with get_session() as session:
        user = get_user_by_id(session, user_id)
        if not user:
            raise ValueError("Пользователь не найден")
        if user.role == ROLE_ADMIN and user.is_active:
            if count_active_admins(session, exclude_id=user.id) == 0:
                raise ValueError("Нельзя удалить последнего администратора")
        session.delete(user)
        session.commit()
