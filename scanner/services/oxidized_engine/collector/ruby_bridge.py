from __future__ import annotations

import json
import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from services.git_helpers import git_env
from services.oxidized_config_loader import oxidized_home
from services.oxidized_engine.outputs import ModelOutputs

logger = logging.getLogger("services.oxidized_engine.collector.ruby_bridge")

_BRIDGE_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "oxidized_bridge.rb"
_RUBY_BIN = os.environ.get("RUBY_BIN", "ruby")


def _bridge_env() -> dict[str, str]:
    home = oxidized_home()
    env = os.environ.copy()
    env["OXIDIZED_HOME"] = str(home)
    config_path = Path(getattr(settings, "OXIDIZED_CONFIG_PATH", home / "config"))
    if config_path.name == "config" and config_path.parent == home:
        env["OXIDIZED_CONFIG_FILE"] = "config"
    elif config_path.exists():
        env["OXIDIZED_CONFIG_FILE"] = config_path.name
        env["OXIDIZED_HOME"] = str(config_path.parent)
    env["OXIDIZED_BRIDGE_LOG"] = os.environ.get(
        "OXIDIZED_BRIDGE_LOG", "/tmp/oxidized-bridge.log"
    )
    repo = os.environ.get("OXIDIZED_GIT_REPO", "/var/lib/oxidized")
    env.update(git_env(repo))
    return env


def _run_ruby(command: str, *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_RUBY_BIN, str(_BRIDGE_SCRIPT), command],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("OXIDIZED_RUBY_TIMEOUT", "300")),
        env=_bridge_env(),
        check=False,
    )


@lru_cache(maxsize=1)
def ruby_available() -> bool:
    if not _BRIDGE_SCRIPT.exists():
        return False
    try:
        proc = subprocess.run(
            [_RUBY_BIN, "-e", "require 'oxidized'"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def list_models() -> list[str]:
    proc = _run_ruby("list_models")
    if proc.returncode != 0:
        logger.warning(
            "oxidized | ruby | list_models failed: %s",
            (proc.stderr or proc.stdout).strip(),
        )
        return []
    data = json.loads(proc.stdout or "{}")
    return list(data.get("models") or [])


def collect_via_ruby(node) -> tuple[str, ModelOutputs | None]:
    payload = {
        "name": node.name,
        "ip": node.ip,
        "group": node.group,
        "model": node.model_name,
        "username": node.auth.get("username") or None,
        "password": node.auth.get("password") or None,
        "vars": node.vars,
    }
    proc = _run_ruby("collect", stdin=json.dumps(payload))
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ruby bridge failed").strip()
        logger.error("oxidized | ruby | collect failed for %s: %s", node.name, err)
        node.err_type = "RubyBridgeError"
        node.err_reason = err
        return "fail", None

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        node.err_type = "RubyBridgeError"
        node.err_reason = str(exc)
        return "fail", None

    node.err_type = data.get("err_type")
    node.err_reason = data.get("err_reason")
    if data.get("model"):
        node.model_name = str(data["model"])

    status = str(data.get("status") or "fail")
    if status == "success" and data.get("config"):
        outputs = ModelOutputs()
        outputs.add(str(data["config"]))
        return "success", outputs
    if status not in ("success", "fail", "no_connection"):
        return "fail", None
    return status, None
