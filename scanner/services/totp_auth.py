"""TOTP 2FA для локальных пользователей."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import pyotp
from django.conf import settings

from core.models import User
from services.auth import JWT_ALGORITHM, hash_password, verify_password

logger = logging.getLogger(__name__)

TOTP_ISSUER = "Backup Tools"
CHALLENGE_TTL_MINUTES = 5
RECOVERY_CODE_COUNT = 8


def create_totp_challenge_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=CHALLENGE_TTL_MINUTES)
    payload = {
        "sub": str(user_id),
        "typ": "totp_challenge",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_totp_challenge(token: str) -> int:
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM])
    if payload.get("typ") != "totp_challenge":
        raise ValueError("Недействительный challenge")
    return int(payload.get("sub", "0"))


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user: User, secret: str) -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=user.username, issuer_name=TOTP_ISSUER)


def verify_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(str(code).strip(), valid_window=1)


def _generate_recovery_codes() -> list[str]:
    return [secrets.token_hex(4) for _ in range(RECOVERY_CODE_COUNT)]


def _hash_recovery(code: str) -> str:
    return hash_password(code)


def verify_recovery(user: User, code: str) -> bool:
    plain = str(code).strip().replace("-", "").lower()
    if not plain:
        return False
    remaining: list[str] = []
    matched = False
    for hashed in user.totp_recovery_hashes or []:
        if not matched and verify_password(plain, hashed):
            matched = True
            continue
        remaining.append(hashed)
    if matched:
        user.totp_recovery_hashes = remaining
        user.save(update_fields=["totp_recovery_hashes"])
    return matched


def begin_totp_setup(user: User) -> dict:
    if user.auth_source in ("ldap", "radius"):
        raise ValueError("2FA недоступна для LDAP/RADIUS-пользователей")
    secret = generate_secret()
    codes = _generate_recovery_codes()
    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri(user, secret),
        "recovery_codes": codes,
    }


def enable_totp(user: User, secret: str, code: str, recovery_codes: list[str]) -> None:
    if user.auth_source in ("ldap", "radius"):
        raise ValueError("2FA недоступна для LDAP/RADIUS-пользователей")
    if not verify_code(secret, code):
        raise ValueError("Неверный код подтверждения")
    user.totp_secret = secret
    user.totp_enabled = True
    user.totp_recovery_hashes = [_hash_recovery(c) for c in recovery_codes]
    user.save(update_fields=["totp_secret", "totp_enabled", "totp_recovery_hashes"])
    logger.info("totp | enabled | user=%s", user.username)


def disable_totp(user: User, *, password: str, code: str = "") -> None:
    if user.auth_source in ("ldap", "radius"):
        raise ValueError("2FA недоступна для LDAP/RADIUS-пользователей")
    if not verify_password(password, user.password_hash):
        raise ValueError("Неверный пароль")
    if user.totp_enabled and code and not verify_code(user.totp_secret, code):
        raise ValueError("Неверный TOTP-код")
    user.totp_enabled = False
    user.totp_secret = ""
    user.totp_recovery_hashes = []
    user.save(update_fields=["totp_enabled", "totp_secret", "totp_recovery_hashes"])
    logger.info("totp | disabled | user=%s", user.username)


def verify_login_second_factor(user: User, *, code: str = "", recovery_code: str = "") -> bool:
    if not user.totp_enabled:
        return True
    if code and verify_code(user.totp_secret, code):
        return True
    if recovery_code and verify_recovery(user, recovery_code):
        return True
    return False


def totp_public_status(user: User) -> dict:
    return {
        "totp_enabled": bool(user.totp_enabled),
        "totp_available": (user.auth_source or "local") != "ldap",
    }
