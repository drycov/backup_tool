from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings


@dataclass
class GitOutputConfig:
    user: str
    email: str
    repo: Path
    single_repo: bool = True
    branch: str = "main"


@dataclass
class GroupConfig:
    username: str
    password: str
    model: str = "routeros"


@dataclass
class OxidizedConfig:
    """Runtime settings mirroring oxidized/config YAML sections."""

    interval: int = 3600
    threads: int = 10
    timeout: int = 20
    retries: int = 3
    resolve_dns: bool = True
    default_model: str = "routeros"
    default_ssh_port: int = 44333
    ssh_secure: bool = False
    log_path: Path = field(default_factory=lambda: Path("/var/lib/oxidized/oxidized.log"))
    git: GitOutputConfig = field(default_factory=lambda: GitOutputConfig(
        user="Oxidized",
        email="oxidized@localhost",
        repo=Path("/var/lib/oxidized"),
    ))
    groups: dict[str, GroupConfig] = field(default_factory=dict)
    git_remote_url: str = ""
    gitea_token: str = ""
    gitea_http_user: str = "oauth2"
    git_ssh_private_key: Path = field(
        default_factory=lambda: Path("/home/oxidized/.ssh/id_rsa")
    )
    git_ssh_public_key: Path = field(
        default_factory=lambda: Path("/home/oxidized/.ssh/id_rsa.pub")
    )

    @classmethod
    def from_django(cls) -> OxidizedConfig:
        repo = Path(os.environ.get("OXIDIZED_GIT_REPO", "/var/lib/oxidized"))
        groups: dict[str, GroupConfig] = {}
        try:
            from services.inventory import load_inventory

            for profile in load_inventory().credential_profiles:
                groups[profile.group_name] = GroupConfig(
                    username=profile.username,
                    password=profile.password,
                    model="routeros",
                )
        except Exception:
            pass

        if not groups:
            groups["default"] = GroupConfig(
                username=getattr(settings, "OVN_USER", "admin"),
                password=getattr(settings, "OVN_PASS", ""),
            )

        return cls(
            interval=int(os.environ.get("OXIDIZED_INTERVAL", "3600")),
            threads=int(os.environ.get("OXIDIZED_THREADS", "10")),
            timeout=int(os.environ.get("OXIDIZED_TIMEOUT", "20")),
            retries=int(os.environ.get("OXIDIZED_RETRIES", "3")),
            resolve_dns=os.environ.get("OXIDIZED_RESOLVE_DNS", "true").lower()
            in ("1", "true", "yes"),
            default_model=os.environ.get("OXIDIZED_DEFAULT_MODEL", "routeros"),
            default_ssh_port=int(getattr(settings, "ROUTEROS_SSH_PORT", 44333)),
            log_path=Path(getattr(settings, "OXIDIZED_LOG_PATH", "/var/lib/oxidized/oxidized.log")),
            git=GitOutputConfig(
                user=os.environ.get("GIT_COMMIT_USER", "Oxidized"),
                email=os.environ.get("GIT_COMMIT_EMAIL", "oxidized@localhost"),
                repo=repo,
                single_repo=True,
                branch=os.environ.get("GIT_BRANCH", "main"),
            ),
            groups=groups,
            git_remote_url=getattr(settings, "GIT_REMOTE_URL", ""),
            gitea_token=getattr(settings, "GITEA_TOKEN", ""),
            gitea_http_user=getattr(settings, "GITEA_HTTP_USER", "oauth2"),
            git_ssh_private_key=Path(
                os.environ.get("GIT_SSH_PRIVATE_KEY", "/home/oxidized/.ssh/id_rsa")
            ),
            git_ssh_public_key=Path(
                os.environ.get("GIT_SSH_PUBLIC_KEY", "/home/oxidized/.ssh/id_rsa.pub")
            ),
        )
