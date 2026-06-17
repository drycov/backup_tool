from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.git_helpers import git_env
from services.oxidized_engine.config import OxidizedConfig
from services.oxidized_engine.outputs import ModelOutputs

if TYPE_CHECKING:
    from services.oxidized_engine.node import Node

logger = logging.getLogger(__name__)


class GitOutput:
    """Git output — port of Oxidized::Output::Git (subprocess git)."""

    def __init__(self, config: OxidizedConfig) -> None:
        self.config = config
        self.git_cfg = config.git
        self.last_commit: str | None = None

    def _repo_path(self) -> Path:
        path = self.git_cfg.repo
        path.mkdir(parents=True, exist_ok=True)
        env = git_env(path)
        if not (path / ".git").exists():
            subprocess.run(
                ["git", "init", str(path)],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            self._git("config", "user.name", self.git_cfg.user)
            self._git("config", "user.email", self.git_cfg.email)
        return path

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        repo = self._repo_path()
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            env=git_env(repo),
        )

    def _file_path(self, name: str, group: str | None) -> str:
        if group and self.git_cfg.single_repo:
            return f"{group}/{name}"
        return name

    def store(
        self,
        name: str,
        outputs: ModelOutputs,
        *,
        msg: str,
        group: str | None = None,
        user: str | None = None,
        email: str | None = None,
    ) -> bool:
        data = outputs.to_cfg()
        if not data:
            return False

        rel_path = self._file_path(name, group)
        repo = self._repo_path()
        target = repo / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and target.read_text(encoding="utf-8", errors="replace") == data:
            logger.debug("oxidized | git | no change for %s", rel_path)
            return False

        target.write_text(data, encoding="utf-8")
        if user:
            self._git("config", "user.name", user)
        if email:
            self._git("config", "user.email", email)

        self._git("add", rel_path)
        author = f"{user or self.git_cfg.user} <{email or self.git_cfg.email}>"
        commit = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                f"user.name={user or self.git_cfg.user}",
                "-c",
                f"user.email={email or self.git_cfg.email}",
                "commit",
                "-m",
                msg,
                "--author",
                author,
            ],
            capture_output=True,
            text=True,
            env=git_env(repo),
        )
        if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
            logger.warning("oxidized | git | commit failed: %s", commit.stderr)
            return False

        subprocess.run(
            ["git", "-C", str(repo), "branch", "-M", self.git_cfg.branch],
            capture_output=True,
            text=True,
            env=git_env(repo),
        )

        rev = self._git("rev-parse", "HEAD")
        self.last_commit = rev.stdout.strip()
        logger.info("oxidized | git | stored %s", rel_path)
        return True

    def fetch(self, node: Node) -> str:
        rel_path = self._file_path(node.name, node.group)
        target = self._repo_path() / rel_path
        if not target.exists():
            return "node not found"
        return target.read_text(encoding="utf-8", errors="replace")

    def version(self, node: Node) -> list[dict[str, Any]]:
        rel_path = self._file_path(node.name, node.group)
        repo = self._repo_path()
        log = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                "--follow",
                f"--format=%H|%cI|%an|%s",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            env=git_env(repo),
        )
        if log.returncode != 0:
            return []
        versions: list[dict[str, Any]] = []
        for line in log.stdout.splitlines():
            if not line.strip():
                continue
            oid, time_str, author, message = line.split("|", 3)
            versions.append(
                {
                    "oid": oid,
                    "date": time_str,
                    "time": time_str,
                    "author": author,
                    "message": message,
                }
            )
        return versions

    def get_version(self, node: Node, oid: str) -> str:
        rel_path = self._file_path(node.name, node.group)
        repo = self._repo_path()
        show = subprocess.run(
            ["git", "-C", str(repo), "show", f"{oid}:{rel_path}"],
            capture_output=True,
            text=True,
            env=git_env(repo),
        )
        if show.returncode != 0:
            return "version not found"
        return show.stdout

    def get_diff(self, node: Node, oid1: str, oid2: str | None = None) -> dict[str, Any]:
        rel_path = self._file_path(node.name, node.group)
        repo = self._repo_path()
        env = git_env(repo)
        if oid2:
            diff = subprocess.run(
                ["git", "-C", str(repo), "diff", oid2, oid1, "--", rel_path],
                capture_output=True,
                text=True,
                env=env,
            )
        else:
            diff = subprocess.run(
                ["git", "-C", str(repo), "show", oid1, "--", rel_path],
                capture_output=True,
                text=True,
                env=env,
            )
        patch = diff.stdout or "no diffs"
        added = patch.count("\n+") - patch.count("\n+++")
        removed = patch.count("\n-") - patch.count("\n---")
        return {"patch": patch, "stat": [len(patch.splitlines()), added, removed]}
