"""Получение имени устройства по SSH (RouterOS system identity)."""

import re
from typing import Optional

import paramiko

IDENTITY_TIMEOUT_SEC = 8


def _parse_routeros_identity(output: str) -> Optional[str]:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("name:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                return value
    return None


def fetch_routeros_identity(
    ip: str,
    port: int,
    username: str,
    password: str,
) -> Optional[str]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=ip,
            port=port,
            username=username,
            password=password,
            timeout=IDENTITY_TIMEOUT_SEC,
            banner_timeout=IDENTITY_TIMEOUT_SEC,
            auth_timeout=IDENTITY_TIMEOUT_SEC,
            look_for_keys=False,
            allow_agent=False,
        )
        _, stdout, _ = client.exec_command(
            "/system identity print without-paging",
            timeout=IDENTITY_TIMEOUT_SEC,
        )
        output = stdout.read().decode("utf-8", errors="replace")
        return _parse_routeros_identity(output)
    except Exception:
        return None
    finally:
        client.close()


def fetch_device_hostname(
    ip: str,
    port: int,
    username: str,
    password: str,
    model: str,
) -> Optional[str]:
    model_lower = (model or "").lower()
    if model_lower == "routeros":
        return fetch_routeros_identity(ip, port, username, password)
    if model_lower == "ios":
        return _fetch_ssh_command(
            ip, port, username, password, "show running-config | include hostname"
        )
    return None


def _fetch_ssh_command(
    ip: str,
    port: int,
    username: str,
    password: str,
    command: str,
) -> Optional[str]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=ip,
            port=port,
            username=username,
            password=password,
            timeout=IDENTITY_TIMEOUT_SEC,
            banner_timeout=IDENTITY_TIMEOUT_SEC,
            auth_timeout=IDENTITY_TIMEOUT_SEC,
            look_for_keys=False,
            allow_agent=False,
        )
        _, stdout, _ = client.exec_command(command, timeout=IDENTITY_TIMEOUT_SEC)
        output = stdout.read().decode("utf-8", errors="replace")
        for line in output.splitlines():
            line = line.strip()
            if line.lower().startswith("hostname"):
                parts = re.split(r"\s+", line, maxsplit=1)
                if len(parts) > 1 and parts[1]:
                    return parts[1].strip()
        return None
    except Exception:
        return None
    finally:
        client.close()
