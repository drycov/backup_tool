"""Парсинг DATABASE_URL и проверка доступности БД."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

_POSTGRES_SCHEMES = {"postgresql", "postgres", "postgresql+psycopg2"}
_SQLITE_SCHEMES = {"sqlite", "sqlite3"}


def default_sqlite_path(base_dir: Path | None = None) -> Path:
    explicit = os.environ.get("SQLITE_DB_PATH", "").strip()
    if explicit:
        return Path(explicit)
    docker_inventory = Path("/data/inventory/scanner.db")
    if docker_inventory.parent.exists():
        return docker_inventory
    root = base_dir or Path(__file__).resolve().parent.parent
    return root / "scanner.db"


def default_database_url(base_dir: Path | None = None) -> str:
    path = default_sqlite_path(base_dir)
    return f"sqlite:////{path.as_posix().lstrip('/')}"


def resolved_database_url(base_dir: Path | None = None) -> str:
    raw = os.environ.get("DATABASE_URL", "").strip()
    if raw:
        return raw
    return default_database_url(base_dir)


def is_postgresql_url(url: str | None = None) -> bool:
    scheme = urlparse(
        (url or resolved_database_url()).replace("postgresql+psycopg2://", "postgresql://")
    ).scheme
    return scheme in _POSTGRES_SCHEMES


def database_url_for_log(url: str | None = None) -> str:
    raw = url or resolved_database_url() or "env-only"
    if raw == "env-only":
        return raw
    parsed = urlparse(raw.replace("postgresql+psycopg2://", "postgresql://"))
    if parsed.scheme in _SQLITE_SCHEMES:
        return f"sqlite:{parsed.path}"
    if parsed.scheme in _POSTGRES_SCHEMES:
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        name = parsed.path.lstrip("/") or "?"
        return f"postgresql://{parsed.username or '?'}:***@{host}:{port}/{name}"
    return re.sub(r":([^:@/]+)@", ":***@", raw)


def django_db_config(base_dir: Path | None = None) -> dict[str, Any]:
    """Конфигурация Django DATABASES['default'] из DATABASE_URL или SQLite по умолчанию."""
    url = resolved_database_url(base_dir)
    normalized = url.replace("postgresql+psycopg2://", "postgresql://")
    parsed = urlparse(normalized)

    if parsed.scheme in _SQLITE_SCHEMES:
        db_path = unquote(parsed.path)
        if db_path.startswith("//"):
            db_path = db_path[1:]
        elif db_path.startswith("/") and len(db_path) > 2 and db_path[2] == ":":
            pass
        elif parsed.netloc:
            db_path = f"{parsed.netloc}{parsed.path}"
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(path),
        }

    if parsed.scheme in _POSTGRES_SCHEMES:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
        }

    raise ValueError(
        f"Неподдерживаемый DATABASE_URL: {parsed.scheme}. "
        "Используйте sqlite:///… или postgresql://…"
    )


_checked = False
_available = False


def is_database_available() -> bool:
    """Проверка соединения; при недоступности настройки читаются из .env."""
    global _checked, _available
    if _checked:
        return _available
    try:
        from django.db import connection

        connection.ensure_connection()
        _available = True
    except Exception as exc:
        logger.warning(
            "database | недоступна (%s), настройки и seed — из .env",
            exc,
        )
        _available = False
    _checked = True
    return _available


def reset_availability_cache() -> None:
    global _checked, _available
    _checked = False
    _available = False


def require_database(message: str = "База данных недоступна") -> None:
    if not is_database_available():
        raise ValueError(
            f"{message}. Задайте DATABASE_URL "
            "(sqlite:////data/inventory/scanner.db или postgresql://user:pass@host:5432/db)."
        )
