from __future__ import annotations

import logging

import paramiko

from services.oxidized_engine.model.base import Model
from services.oxidized_engine.node import Node
from services.oxidized_engine.outputs import ModelOutputs

logger = logging.getLogger(__name__)


class SSHInput:
    """SSH input — exec model commands via paramiko (oxidized input ssh exec)."""

    def __init__(self, secure: bool = False) -> None:
        self.secure = secure

    def get(self, node: Node) -> ModelOutputs:
        client = paramiko.SSHClient()
        if self.secure:
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=node.ip,
                port=node.ssh_port,
                username=node.auth["username"],
                password=node.auth["password"],
                timeout=node.timeout,
                banner_timeout=node.timeout,
                auth_timeout=node.timeout,
                look_for_keys=False,
                allow_agent=False,
            )
        except Exception as exc:
            raise ConnectionError(str(exc)) from exc

        def exec_cmd(command: str) -> str:
            _, stdout, stderr = client.exec_command(command, timeout=node.timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            if not output.strip():
                output = stderr.read().decode("utf-8", errors="replace")
            return Model.strip_ansi(output)

        try:
            model = node.model
            return model.collect(node, exec_cmd)
        finally:
            client.close()
