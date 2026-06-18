"""Git push и интеграции — singleton в PostgreSQL, .env как fallback."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from core.models import GitConfig
from services.database import is_database_available, require_database, reset_availability_cache

logger = logging.getLogger(__name__)

PASSWORD_MASK = "********"


@dataclass(frozen=True)
class GitConfigData:
    git_remote_url: str
    gitea_token: str
    gitea_http_user: str
    git_commit_user: str
    git_commit_email: str
    git_branch: str
    oxidized_source_token: str
    oxidized_public_url: str


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes")


def _defaults_from_env() -> dict[str, Any]:
    return {
        "git_remote_url": os.environ.get("GIT_REMOTE_URL", "").strip(),
        "gitea_token": os.environ.get("GITEA_TOKEN", ""),
        "gitea_http_user": os.environ.get("GITEA_HTTP_USER", "oauth2").strip() or "oauth2",
        "git_commit_user": os.environ.get("GIT_COMMIT_USER", "Oxidized").strip() or "Oxidized",
        "git_commit_email": os.environ.get("GIT_COMMIT_EMAIL", "oxidized@localhost").strip()
        or "oxidized@localhost",
        "git_branch": os.environ.get("GIT_BRANCH", "main").strip() or "main",
        "oxidized_source_token": os.environ.get("OXIDIZED_SOURCE_TOKEN", ""),
        "oxidized_public_url": os.environ.get("OXIDIZED_PUBLIC_URL", "http://localhost:8888").strip()
        or "http://localhost:8888",
    }


def _row_to_data(row: GitConfig) -> GitConfigData:
    return GitConfigData(
        git_remote_url=row.git_remote_url or "",
        gitea_token=row.gitea_token or "",
        gitea_http_user=row.gitea_http_user or "oauth2",
        git_commit_user=row.git_commit_user or "Oxidized",
        git_commit_email=row.git_commit_email or "oxidized@localhost",
        git_branch=row.git_branch or "main",
        oxidized_source_token=row.oxidized_source_token or "",
        oxidized_public_url=row.oxidized_public_url
        or os.environ.get("OXIDIZED_PUBLIC_URL", "http://localhost:8888").strip(),
    )


def ensure_initialized() -> None:
    if not is_database_available():
        return
    try:
        defaults = _defaults_from_env()
        _, created = GitConfig.objects.get_or_create(pk=1, defaults=defaults)
        if created:
            logger.info("git | конфигурация инициализирована из .env")
    except Exception as exc:
        logger.warning("git | init failed: %s", exc)
        reset_availability_cache()


def get_config() -> GitConfigData:
    if not is_database_available():
        return GitConfigData(**_defaults_from_env())
    try:
        row = GitConfig.objects.filter(pk=1).first()
        if not row:
            ensure_initialized()
            row = GitConfig.objects.get(pk=1)
        return _row_to_data(row)
    except Exception as exc:
        logger.warning("git | read failed: %s", exc)
        reset_availability_cache()
        return GitConfigData(**_defaults_from_env())


def public_url() -> str:
    url = get_config().oxidized_public_url or os.environ.get(
        "OXIDIZED_PUBLIC_URL", "http://localhost:8888"
    )
    return url.strip().rstrip("/")


def source_token() -> str:
    return get_config().oxidized_source_token or os.environ.get("OXIDIZED_SOURCE_TOKEN", "")


def get_config_public() -> dict[str, Any]:
    cfg = get_config()
    return {
        "git_remote_url": cfg.git_remote_url,
        "gitea_token_set": bool(cfg.gitea_token),
        "gitea_http_user": cfg.gitea_http_user,
        "git_commit_user": cfg.git_commit_user,
        "git_commit_email": cfg.git_commit_email,
        "git_branch": cfg.git_branch,
        "oxidized_source_token_set": bool(cfg.oxidized_source_token),
        "oxidized_public_url": cfg.oxidized_public_url,
        "git_remote_configured": bool(cfg.git_remote_url),
        "gitea_configured": bool(cfg.gitea_token),
        "storage": "database" if is_database_available() else "env",
    }


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    require_database("Сохранение настроек Git невозможно")
    row = GitConfig.objects.filter(pk=1).first()
    if not row:
        ensure_initialized()
        row = GitConfig.objects.get(pk=1)

    gitea_token = payload.get("gitea_token")
    if gitea_token in (None, "", PASSWORD_MASK):
        gitea_token = row.gitea_token
    else:
        gitea_token = str(gitea_token)

    source_token = payload.get("oxidized_source_token")
    if source_token in (None, "", PASSWORD_MASK):
        source_token = row.oxidized_source_token
    else:
        source_token = str(source_token)

    row.git_remote_url = str(payload.get("git_remote_url", row.git_remote_url)).strip()
    row.gitea_token = gitea_token
    row.gitea_http_user = str(payload.get("gitea_http_user", row.gitea_http_user)).strip() or "oauth2"
    row.git_commit_user = str(payload.get("git_commit_user", row.git_commit_user)).strip() or "Oxidized"
    row.git_commit_email = (
        str(payload.get("git_commit_email", row.git_commit_email)).strip() or "oxidized@localhost"
    )
    row.git_branch = str(payload.get("git_branch", row.git_branch)).strip() or "main"
    row.oxidized_source_token = source_token
    row.oxidized_public_url = str(payload.get("oxidized_public_url", row.oxidized_public_url)).strip()
    row.save()

    from services.inventory import load_inventory, update_oxidized_credentials

    update_oxidized_credentials(load_inventory())
    try:
        from services.oxidized_engine import reload_engine

        reload_engine()
    except Exception:
        logger.exception("git | reload engine after settings save failed")

    logger.info("git | настройки сохранены через UI")
    return get_config_public()
