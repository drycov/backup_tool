"""Применение отрендеренной конфигурации на устройство (по модели)."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

import paramiko

from services.mikrotik_backup import MikrotikBackup, device_file_prefix
from services.schemas import Device

logger = logging.getLogger(__name__)


def apply_config_to_device(device: Device, config_text: str) -> dict:
    model = (device.model or "routeros").lower()
    if model == "routeros" or model.startswith("routeros"):
        return _apply_routeros(device, config_text)
    if model in ("ios", "iosxe", "nxos", "asa"):
        return _apply_cisco_ios(device, config_text)
    if model == "junos":
        return _apply_junos(device, config_text)
    return _apply_ssh_lines(device, config_text)


def _connect_device(device: Device) -> tuple[paramiko.SSHClient, int]:
    from services.inventory import load_inventory

    inventory = load_inventory()
    profile = next(
        (p for p in inventory.credential_profiles if p.group_name == device.group),
        None,
    )
    if not profile and inventory.credential_profiles:
        profile = inventory.credential_profiles[0]
    if not profile:
        raise ValueError("Нет профиля credentials для группы устройства")

    port = int(device.ports[0]) if device.ports else 22
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=device.ip,
        port=port,
        username=profile.username,
        password=profile.password,
        timeout=60,
        banner_timeout=60,
        auth_timeout=60,
        look_for_keys=False,
        allow_agent=False,
    )
    return client, port


def _apply_routeros(device: Device, config_text: str) -> dict:
    from services.oxidized_engine import get_manager

    manager = get_manager()
    manager.worker.reload()
    node = manager.nodes.find(device.name)
    if not node:
        raise ValueError(f"Узел '{device.name}' не найден в Oxidized engine")
    if node.model_name != "routeros":
        raise ValueError("RouterOS import доступен только для routeros")

    prefix = device_file_prefix(device.name)
    remote_name = f"{prefix}_provision.rsc"
    svc = MikrotikBackup()
    client = svc._connect(node)
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".rsc", delete=False) as tmp:
            tmp.write(config_text)
            local_path = Path(tmp.name)
        try:
            with client.open_sftp() as sftp:
                sftp.put(str(local_path), remote_name)
            output = svc._exec(client, f'/import file-name="{remote_name}"')
            return {"method": "routeros_import", "remote_file": remote_name, "output": output or ""}
        finally:
            local_path.unlink(missing_ok=True)
    finally:
        client.close()


def _apply_cisco_ios(device: Device, config_text: str) -> dict:
    lines = _config_lines(config_text)
    client, _ = _connect_device(device)
    outputs: list[str] = []
    try:
        for cmd in ["configure terminal", *lines, "end", "write memory"]:
            out = _exec(client, cmd)
            if out:
                outputs.append(f"$ {cmd}\n{out}")
        return {"method": "ios_configure", "output": "\n".join(outputs)}
    finally:
        client.close()


def _apply_junos(device: Device, config_text: str) -> dict:
    lines = _config_lines(config_text)
    client, _ = _connect_device(device)
    outputs: list[str] = []
    try:
        for cmd in ["configure", *lines, "commit and-quit"]:
            out = _exec(client, cmd)
            if out:
                outputs.append(f"$ {cmd}\n{out}")
        return {"method": "junos_configure", "output": "\n".join(outputs)}
    finally:
        client.close()


def _apply_ssh_lines(device: Device, config_text: str) -> dict:
    lines = _config_lines(config_text)
    client, _ = _connect_device(device)
    outputs: list[str] = []
    try:
        for cmd in lines:
            out = _exec(client, cmd)
            if out:
                outputs.append(f"$ {cmd}\n{out}")
        return {"method": "ssh_lines", "output": "\n".join(outputs)}
    finally:
        client.close()


def _config_lines(config_text: str) -> list[str]:
    lines: list[str] = []
    for raw in config_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("!") or line.startswith("#"):
            continue
        lines.append(line)
    if not lines:
        raise ValueError("Конфигурация пуста после фильтрации комментариев")
    return lines


def _exec(client: paramiko.SSHClient, command: str) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=120)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    combined = (out or err).strip()
    if re.search(r"%\s*Error|invalid input|syntax error", combined, re.I):
        raise ValueError(combined[:500] or f"Команда завершилась с ошибкой: {command}")
    return combined
