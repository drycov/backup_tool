from __future__ import annotations

import os
from pathlib import Path


def git_env(repo: Path | str | None = None) -> dict[str, str]:
    """Git subprocess env with safe.directory for shared oxidized-data volume."""
    env = os.environ.copy()
    if repo is None:
        return env
    repo_path = str(Path(repo).resolve())
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "safe.directory"
    env["GIT_CONFIG_VALUE_0"] = repo_path
    return env
