import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session

from .db import User, get_session

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
AUTH_COOKIE_NAME = os.environ.get("AUTH_COOKIE_NAME", "backup_tools_token")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

security = HTTPBearer(auto_error=False)

ROLE_VIEWER = "viewer"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"
VALID_ROLES = {ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN}

PERMISSION_VIEW_INVENTORY = "inventory:read"
PERMISSION_EDIT_DEVICES = "inventory:devices"
PERMISSION_EDIT_INVENTORY = "inventory:write"
PERMISSION_VIEW_CREDENTIALS = "credentials:read"
PERMISSION_EDIT_CREDENTIALS = "credentials:write"
PERMISSION_RUN_SCAN = "scan:run"
PERMISSION_OXIDIZED_READ = "oxidized:read"
PERMISSION_OXIDIZED_WRITE = "oxidized:write"
PERMISSION_MANAGE_USERS = "users:manage"

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_VIEWER: {
        PERMISSION_VIEW_INVENTORY,
        PERMISSION_OXIDIZED_READ,
    },
    ROLE_OPERATOR: {
        PERMISSION_VIEW_INVENTORY,
        PERMISSION_EDIT_DEVICES,
        PERMISSION_RUN_SCAN,
        PERMISSION_OXIDIZED_READ,
        PERMISSION_OXIDIZED_WRITE,
    },
    ROLE_ADMIN: {
        PERMISSION_VIEW_INVENTORY,
        PERMISSION_EDIT_DEVICES,
        PERMISSION_EDIT_INVENTORY,
        PERMISSION_VIEW_CREDENTIALS,
        PERMISSION_EDIT_CREDENTIALS,
        PERMISSION_RUN_SCAN,
        PERMISSION_OXIDIZED_READ,
        PERMISSION_OXIDIZED_WRITE,
        PERMISSION_MANAGE_USERS,
    },
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def permissions_for_role(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, set()))


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


def authenticate_user(session: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(session, username)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def seed_default_admin() -> None:
    """Создать админа при пустой БД или синхронизировать ADMIN_USERNAME/PASSWORD из .env."""
    password = ADMIN_PASSWORD or "changeme"
    with get_session() as session:
        user_count = session.query(User).count()
        env_admin = get_user_by_username(session, ADMIN_USERNAME)

        if user_count == 0:
            if not ADMIN_PASSWORD:
                logger.warning(
                    "auth | ADMIN_PASSWORD не задан — создан %s / changeme (смените пароль!)",
                    ADMIN_USERNAME,
                )
            session.add(
                User(
                    username=ADMIN_USERNAME,
                    password_hash=hash_password(password),
                    role=ROLE_ADMIN,
                    is_active=True,
                )
            )
            session.commit()
            logger.info("auth | создан администратор: %s", ADMIN_USERNAME)
            return

        if env_admin and ADMIN_PASSWORD:
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
) -> User:
    with get_session() as session:
        user = get_user_by_id(session, user_id)
        if not user:
            raise ValueError("Пользователь не найден")
        if role is not None:
            if role not in VALID_ROLES:
                raise ValueError(f"Недопустимая роль: {role}")
            user.role = role
        if is_active is not None:
            user.is_active = is_active
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
        session.delete(user)
        session.commit()
