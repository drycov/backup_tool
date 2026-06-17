from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, urlparse, urlunparse

from services.git_helpers import git_env
from services.oxidized_engine.config import OxidizedConfig
from services.oxidized_engine.job import Job

if TYPE_CHECKING:
    from services.oxidized_engine.node import Node

logger = logging.getLogger(__name__)


def _repo_has_commits(repo: Path, env: dict[str, str]) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode == 0


class HookRunner:
    """Hooks runner — post_store githubrepo push."""

    def __init__(self, config: OxidizedConfig) -> None:
        self.config = config

    def post_store(self, node: Node, job: Job, commitref: str | None) -> None:
        if not self.config.git_remote_url:
            return
        self._push_to_remote(node)

    def node_fail(self, node: Node, job: Job) -> None:
        logger.warning(
            "oxidized | hook | node_fail %s/%s status=%s",
            node.group,
            node.name,
            job.status,
        )

    def _push_to_remote(self, node: Node) -> None:
        repo = Path(node.repo)
        remote_url = self._remote_url()
        if not remote_url:
            return

        env = git_env(repo)
        if self.config.gitea_token and remote_url.startswith("http"):
            parsed = urlparse(remote_url)
            user = quote(self.config.gitea_http_user, safe="")
            token = quote(self.config.gitea_token, safe="")
            auth_url = urlunparse(
                (parsed.scheme, f"{user}:{token}@{parsed.netloc}", parsed.path, "", "", "")
            )
            remote_url = auth_url
        elif remote_url.startswith(("git@", "ssh://")) and self.config.git_ssh_private_key.exists():
            key = self.config.git_ssh_private_key
            env["GIT_SSH_COMMAND"] = (
                f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
            )

        try:
            origin = subprocess.run(
                ["git", "-C", str(repo), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                env=env,
            )
            if origin.returncode != 0:
                subprocess.run(
                    ["git", "-C", str(repo), "remote", "add", "origin", remote_url],
                    check=True,
                    capture_output=True,
                    env=env,
                )
            else:
                subprocess.run(
                    ["git", "-C", str(repo), "remote", "set-url", "origin", remote_url],
                    check=True,
                    capture_output=True,
                    env=env,
                )

            branch = self.config.git.branch
            if _repo_has_commits(repo, env):
                fetch = subprocess.run(
                    ["git", "-C", str(repo), "fetch", "origin", branch],
                    capture_output=True,
                    text=True,
                    env=env,
                )
                if fetch.returncode != 0:
                    err = (fetch.stderr or fetch.stdout or "").strip()
                    if err and "not found" not in err.lower():
                        logger.debug("oxidized | hook | fetch: %s", err)

            push = subprocess.run(
                ["git", "-C", str(repo), "push", "-u", "origin", branch],
                capture_output=True,
                text=True,
                env=env,
            )
            if push.returncode != 0:
                push = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repo),
                        "push",
                        "-u",
                        "origin",
                        f"HEAD:{branch}",
                    ],
                    capture_output=True,
                    text=True,
                    env=env,
                )
            if push.returncode == 0:
                logger.info("oxidized | hook | pushed to %s", self.config.git_remote_url)
            else:
                raise subprocess.CalledProcessError(
                    push.returncode, push.args, push.stdout, push.stderr
                )
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "oxidized | hook | push failed: %s",
                exc.stderr or exc.stdout or exc,
            )
        except Exception as exc:
            logger.warning("oxidized | hook | push error: %s", exc)

    def _remote_url(self) -> str:
        url = self.config.git_remote_url.strip()
        if self.config.gitea_token and url.startswith("http"):
            return url
        return url
