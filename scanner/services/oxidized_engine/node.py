from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from services.oxidized_engine.config import OxidizedConfig
from services.oxidized_engine.outputs import ModelOutputs

logger = logging.getLogger(__name__)


@dataclass
class JobRecord:
    start: datetime
    end: datetime
    status: str
    time: float


@dataclass
class NodeStats:
    mtime: float = 0.0
    success: int = 0
    fail: int = 0
    no_connection: int = 0

    def add(self, status: str) -> None:
        if status == "success":
            self.success += 1
        elif status == "no_connection":
            self.no_connection += 1
        else:
            self.fail += 1


class Node:
    """Device node — mirrors Oxidized::Node resolve_* and #run."""

    def __init__(self, opt: dict[str, Any], config: OxidizedConfig) -> None:
        self.config = config
        self.name = str(opt["name"])
        self.ip = self._resolve_ip(str(opt.get("ip") or self.name), config.resolve_dns)
        self.group = opt.get("group") or "default"
        raw_model = self._resolve_key("model", opt, config.default_model)
        self.model_name = config.resolve_model(raw_model)
        self.vars = dict(opt.get("vars") or {})
        self.auth = {
            "username": self._resolve_key("username", opt, ""),
            "password": self._resolve_key("password", opt, ""),
        }
        self.timeout = int(self._resolve_key("timeout", opt, str(config.timeout)) or config.timeout)
        self.ssh_port = int(self.vars.get("ssh_port") or config.default_ssh_port)
        self.running = False
        self.nexted = False
        self.retry = 0
        self.last: JobRecord | None = None
        self.stats = NodeStats()
        self.user: str | None = None
        self.email: str | None = None
        self.msg: str | None = None
        self.err_type: str | None = None
        self.err_reason: str | None = None

    def _resolve_ip(self, ip_addr: str, resolve_dns: bool) -> str:
        host = ip_addr.split("/", 1)[0]
        try:
            socket.inet_aton(host)
            return host
        except OSError:
            pass
        if resolve_dns:
            try:
                return socket.gethostbyname(host)
            except OSError:
                logger.warning("oxidized | dns | %s not resolvable", host)
        return host

    def _resolve_key(self, key: str, opt: dict[str, Any], default: str = "") -> str:
        if opt.get(key):
            return str(opt[key])
        group_cfg = self.config.groups.get(self.group)
        if group_cfg and key in ("username", "password", "model"):
            value = getattr(group_cfg, key, None)
            if value:
                return str(value)
        if key == "model":
            return self.config.default_model
        return default

    @property
    def repo(self) -> str:
        return str(self.config.git.repo)

    def _ruby_model_error(self) -> bool:
        reason = (self.err_reason or "").lower()
        err_type = (self.err_type or "").lower()
        return (
            "modelnotfound" in err_type
            or "modelnotfound" in reason
            or " not found for node " in reason
        )

    def run(self) -> tuple[str, ModelOutputs | None]:
        from services.oxidized_engine.collector.ruby_bridge import (
            collect_via_ruby,
            ruby_available,
        )

        if ruby_available():
            status, outputs = collect_via_ruby(self)
            if status == "success":
                return status, outputs
            if not self._ruby_model_error():
                return status, outputs
            logger.info(
                "oxidized | ruby | model error, fallback python | %s",
                self.name,
            )
            self.err_type = self.err_reason = None

        from services.oxidized_engine.input.ssh import SSHInput
        from services.oxidized_engine.model.registry import get_model

        input_handler = SSHInput(secure=self.config.ssh_secure)
        try:
            model = get_model(self.model_name)
            node_proxy = _PythonModelNode(self, model)
            outputs = input_handler.get(node_proxy)
            return "success", outputs
        except ConnectionError as exc:
            self.err_type = exc.__class__.__name__
            self.err_reason = str(exc)
            return "no_connection", None
        except Exception as exc:
            self.err_type = exc.__class__.__name__
            self.err_reason = str(exc)
            logger.exception("oxidized | node | %s failed", self.name)
            return "fail", None

    def serialize(self) -> dict[str, Any]:
        full_name = f"{self.group}/{self.name}" if self.group else self.name
        payload: dict[str, Any] = {
            "name": self.name,
            "full_name": full_name,
            "ip": self.ip,
            "group": self.group,
            "model": self.model_name,
            "mtime": self.stats.mtime,
            "vars": self.vars,
            "last": None,
        }
        if self.last:
            payload["last"] = {
                "start": self.last.start.isoformat(),
                "end": self.last.end.isoformat(),
                "status": self.last.status,
                "time": self.last.time,
            }
        return payload

    def reset(self) -> None:
        self.user = self.email = self.msg = None
        self.retry = 0

    def modified(self) -> None:
        self.stats.mtime = datetime.now(timezone.utc).timestamp()

    def due(self, now: float, interval: int) -> bool:
        if self.nexted:
            return True
        if self.last is None:
            return True
        return (self.last.end.timestamp() + interval) <= now


class _PythonModelNode:
    """Adapter so SSHInput can call model.collect on fallback Python models."""

    def __init__(self, node: Node, model) -> None:
        self._node = node
        self.model = model

    def __getattr__(self, name: str):
        return getattr(self._node, name)
