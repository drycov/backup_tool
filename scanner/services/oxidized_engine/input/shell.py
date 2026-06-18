"""Интерактивный SSH shell для моделей с enable/prompt (IOS, EOS)."""

from __future__ import annotations

import re
import time

import paramiko

from services.oxidized_engine.model.base import Model


def shell_exec(
    node,
    *,
    init_commands: list[str] | None = None,
    command: str,
    prompt_pattern: str = r"[>#]\s*$",
    timeout: float = 30,
) -> str:
    client = paramiko.SSHClient()
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

    channel = client.invoke_shell(width=200, height=1000)
    channel.settimeout(timeout)
    try:
        _ = _read_until(channel, prompt_pattern, timeout)
        for cmd in init_commands or []:
            channel.send(cmd + "\n")
            _ = _read_until(channel, prompt_pattern, timeout)
        channel.send(command + "\n")
        output = _read_until(channel, prompt_pattern, timeout)
        return Model.strip_ansi(output)
    finally:
        channel.close()
        client.close()


def _read_until(channel, pattern: str, timeout: float) -> str:
    buf = ""
    deadline = time.monotonic() + timeout
    regex = re.compile(pattern, re.MULTILINE)
    while time.monotonic() < deadline:
        if channel.recv_ready():
            chunk = channel.recv(65535).decode("utf-8", errors="replace")
            buf += chunk
            if regex.search(buf):
                return buf
        else:
            time.sleep(0.05)
    return buf
