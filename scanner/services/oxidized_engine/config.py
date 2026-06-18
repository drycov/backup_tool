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
    model_map: dict[str, str] = field(default_factory=dict)
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

    def resolve_model(self, raw: str | None) -> str:
        from services.oxidized_config_loader import resolve_model_name

        if not raw:
            return self.default_model
        mapped = resolve_model_name(raw, {"model": self.default_model, "model_map": self.model_map})
        return mapped or self.default_model

    @classmethod
    def from_django(cls) -> OxidizedConfig:
        from services.oxidized_config_loader import (
            default_ssh_port_from_yaml,
            groups_from_yaml,
            load_oxidized_yaml,
        )

        yaml_cfg = load_oxidized_yaml()
        default_model = str(
            yaml_cfg.get("model")
            or os.environ.get("OXIDIZED_DEFAULT_MODEL", "routeros")
        )
        yaml_port = default_ssh_port_from_yaml(yaml_cfg)
        default_ssh_port = yaml_port if yaml_port is not None else int(
            getattr(settings, "ROUTEROS_SSH_PORT", 44333)
        )

        groups = groups_from_yaml(yaml_cfg, default_model=default_model)
        try:
            from services.inventory import load_inventory

            for profile in load_inventory().credential_profiles:
                existing = groups.get(profile.group_name)
                groups[profile.group_name] = GroupConfig(
                    username=profile.username,
                    password=profile.password,
                    model=existing.model if existing else default_model,
                )
        except Exception:
            pass

        if not groups:
            from services.scan_settings import get_credentials

            ovn_user, ovn_pass, _, _ = get_credentials()
            groups["default"] = GroupConfig(
                username=ovn_user or "admin",
                password=ovn_pass or "",
                model=default_model,
            )

        model_map_raw = yaml_cfg.get("model_map") or {}
        model_map = {str(k): str(v) for k, v in model_map_raw.items()}

        input_cfg = yaml_cfg.get("input") or {}
        ssh_cfg = input_cfg.get("ssh") or {}

        repo = Path(os.environ.get("OXIDIZED_GIT_REPO", "/var/lib/oxidized"))
        output_cfg = yaml_cfg.get("output") or {}
        git_cfg = output_cfg.get("git") or {}

        from services.git_settings import get_config as get_git_db_config

        _git_cfg = get_git_db_config()

        return cls(
            interval=int(yaml_cfg.get("interval") or os.environ.get("OXIDIZED_INTERVAL", "3600")),
            threads=int(yaml_cfg.get("threads") or os.environ.get("OXIDIZED_THREADS", "10")),
            timeout=int(yaml_cfg.get("timeout") or os.environ.get("OXIDIZED_TIMEOUT", "20")),
            retries=int(yaml_cfg.get("retries") or os.environ.get("OXIDIZED_RETRIES", "3")),
            resolve_dns=str(
                yaml_cfg.get("resolve_dns", os.environ.get("OXIDIZED_RESOLVE_DNS", "true"))
            ).lower() in ("1", "true", "yes"),
            default_model=default_model,
            default_ssh_port=default_ssh_port,
            ssh_secure=bool(ssh_cfg.get("secure", False)),
            model_map=model_map,
            log_path=Path(
                getattr(
                    settings,
                    "OXIDIZED_PYTHON_LOG_PATH",
                    "/var/lib/oxidized/oxidized-python.log",
                )
            ),
            git=GitOutputConfig(
                user=str(git_cfg.get("user") or os.environ.get("GIT_COMMIT_USER", "Oxidized")),
                email=str(
                    git_cfg.get("email")
                    or os.environ.get("GIT_COMMIT_EMAIL", "oxidized@localhost")
                ),
                repo=Path(str(git_cfg.get("repo") or repo)),
                single_repo=bool(git_cfg.get("single_repo", True)),
                branch=str(
                    git_cfg.get("single_branch_name")
                    or os.environ.get("GIT_BRANCH", "main")
                ),
            ),
            groups=groups,
            git_remote_url=_git_cfg.git_remote_url,
            gitea_token=_git_cfg.gitea_token,
            gitea_http_user=_git_cfg.gitea_http_user,
            git_ssh_private_key=Path(
                os.environ.get("GIT_SSH_PRIVATE_KEY", "/home/oxidized/.ssh/id_rsa")
            ),
            git_ssh_public_key=Path(
                os.environ.get("GIT_SSH_PUBLIC_KEY", "/home/oxidized/.ssh/id_rsa.pub")
            ),
        )
