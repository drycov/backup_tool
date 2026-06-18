"""Получение имени устройства по SSH (RouterOS system identity)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import paramiko

IDENTITY_TIMEOUT_SEC = 8


@dataclass(frozen=True)
class DeviceProbeResult:
    authenticated: bool
    identity: str | None = None


def _parse_routeros_identity(output: str) -> Optional[str]:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("name:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                return value
    return None


def _ssh_session(
    ip: str,
    port: int,
    username: str,
    password: str,
) -> paramiko.SSHClient | None:
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
        return client
    except Exception:
        client.close()
        return None


def probe_device_access(
    ip: str,
    port: int,
    username: str,
    password: str,
    model: str,
) -> DeviceProbeResult:
    """One SSH session: auth check + optional identity for supported models."""
    client = _ssh_session(ip, port, username, password)
    if client is None:
        return DeviceProbeResult(authenticated=False)

    try:
        from services.vendor_catalog import normalize_model

        model_lower = normalize_model(model)
        if model_lower == "routeros":
            _, stdout, _ = client.exec_command(
                "/system identity print without-paging",
                timeout=IDENTITY_TIMEOUT_SEC,
            )
            output = stdout.read().decode("utf-8", errors="replace")
            return DeviceProbeResult(
                authenticated=True,
                identity=_parse_routeros_identity(output),
            )

        if model_lower in ("ios", "iosxe", "iosxr", "nxos", "asa"):
            _, stdout, _ = client.exec_command(
                "show running-config | include hostname",
                timeout=IDENTITY_TIMEOUT_SEC,
            )
            output = stdout.read().decode("utf-8", errors="replace")
            for line in output.splitlines():
                line = line.strip()
                if line.lower().startswith("hostname"):
                    parts = re.split(r"\s+", line, maxsplit=1)
                    if len(parts) > 1 and parts[1]:
                        return DeviceProbeResult(authenticated=True, identity=parts[1].strip())
            return DeviceProbeResult(authenticated=True)

        if model_lower in ("junos", "juniper"):
            _, stdout, _ = client.exec_command(
                "show system host-name",
                timeout=IDENTITY_TIMEOUT_SEC,
            )
            output = stdout.read().decode("utf-8", errors="replace")
            for line in output.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("host-name"):
                    parts = re.split(r"\s+", stripped, maxsplit=1)
                    if len(parts) > 1 and parts[1]:
                        return DeviceProbeResult(authenticated=True, identity=parts[1].strip())
            return DeviceProbeResult(authenticated=True)

        if model_lower in ("eos", "arista"):
            _, stdout, _ = client.exec_command(
                "show hostname",
                timeout=IDENTITY_TIMEOUT_SEC,
            )
            output = stdout.read().decode("utf-8", errors="replace")
            for line in output.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("hostname:"):
                    value = stripped.split(":", 1)[1].strip()
                    if value:
                        return DeviceProbeResult(authenticated=True, identity=value)
            return DeviceProbeResult(authenticated=True)

        return DeviceProbeResult(authenticated=True)
    except Exception:
        return DeviceProbeResult(authenticated=False)
    finally:
        client.close()


def fetch_routeros_identity(
    ip: str,
    port: int,
    username: str,
    password: str,
) -> Optional[str]:
    result = probe_device_access(ip, port, username, password, "routeros")
    if not result.authenticated:
        return None
    return result.identity


def fetch_device_hostname(
    ip: str,
    port: int,
    username: str,
    password: str,
    model: str,
) -> Optional[str]:
    result = probe_device_access(ip, port, username, password, model)
    if not result.authenticated:
        return None
    return result.identity
