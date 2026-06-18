"""Commit и push MikroTik bin/rsc в oxidized git-репозиторий."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

from services.git_helpers import git_env
from services.mikrotik_backup import device_file_prefix
from services.oxidized_engine.config import OxidizedConfig
from services.oxidized_engine.hooks import push_git_remote

logger = logging.getLogger(__name__)
_git_lock = threading.RLock()


def mikrotik_git_push_enabled() -> bool:
    from services.backup_settings import get_config

    return get_config().mk_backup_git_push


def _repo_relative(repo: Path, path: Path) -> str | None:
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except ValueError:
        return None


def _stage_prefix_files(repo: Path, folder: Path, prefix: str, env: dict[str, str]) -> list[str]:
    if not folder.is_dir():
        return []
    rel_folder = _repo_relative(repo, folder)
    if not rel_folder:
        return []

    staged: list[str] = []
    for path in folder.glob(f"{prefix}*"):
        rel = _repo_relative(repo, path)
        if not rel:
            continue
        subprocess.run(
            ["git", "-C", str(repo), "add", "--", rel],
            capture_output=True,
            text=True,
            env=env,
        )
        staged.append(rel)

    listed = subprocess.run(
        ["git", "-C", str(repo), "ls-files", f"{rel_folder}/{prefix}*"],
        capture_output=True,
        text=True,
        env=env,
    )
    if listed.returncode == 0:
        for rel in listed.stdout.splitlines():
            rel = rel.strip()
            if rel and not (repo / rel).exists():
                subprocess.run(
                    ["git", "-C", str(repo), "add", "--", rel],
                    capture_output=True,
                    text=True,
                    env=env,
                )
                staged.append(rel)

    return staged


def commit_mikrotik_backups(node_name: str) -> bool:
    """Добавить bin/rsc узла в git, закоммитить и запушить в remote."""
    if not mikrotik_git_push_enabled():
        return False

    from services.backup_settings import get_mikrotik_config
    from services.oxidized_engine.output.git import GitOutput

    ox_cfg = OxidizedConfig.from_django()
    if not ox_cfg.git_remote_url:
        logger.debug("mikrotik | git | skip push — GIT_REMOTE_URL not set")
        return False

    mk_cfg = get_mikrotik_config()
    prefix = device_file_prefix(node_name)
    repo = ox_cfg.git.repo.resolve()

    with _git_lock:
        GitOutput(ox_cfg)._repo_path()
        env = git_env(repo)
        staged: list[str] = []
        staged.extend(_stage_prefix_files(repo, mk_cfg.bin_dir, prefix, env))
        staged.extend(_stage_prefix_files(repo, mk_cfg.rsc_dir, prefix, env))

        if not staged:
            logger.debug("mikrotik | git | nothing to stage for %s", node_name)
            return False

        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--", *staged],
            capture_output=True,
            text=True,
            env=env,
        )
        if status.returncode != 0 or not status.stdout.strip():
            logger.debug("mikrotik | git | no changes for %s", node_name)
            return False

        user = ox_cfg.git.user
        email = ox_cfg.git.email
        commit = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                f"user.name={user}",
                "-c",
                f"user.email={email}",
                "commit",
                "-m",
                f"mikrotik backup {node_name}",
                "--author",
                f"{user} <{email}>",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        if commit.returncode != 0:
            combined = (commit.stdout + commit.stderr).strip()
            if "nothing to commit" in combined:
                return False
            logger.warning("mikrotik | git | commit failed: %s", combined)
            return False

        subprocess.run(
            ["git", "-C", str(repo), "branch", "-M", ox_cfg.git.branch],
            capture_output=True,
            text=True,
            env=env,
        )
        logger.info("mikrotik | git | committed bin/rsc for %s", node_name)
        push_git_remote(ox_cfg, repo)
        return True
