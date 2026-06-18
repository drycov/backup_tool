"""MikroTik backup helpers — port of RealMikrotikBackup (binary + export files)."""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import paramiko

from services.oxidized_logging import get_engine_logger

if TYPE_CHECKING:
    from services.oxidized_engine.node import Node

logger = get_engine_logger("mikrotik")

_POLL_INTERVAL_SEC = 2


@dataclass
class MikrotikBackupConfig:
    binary_enabled: bool = True
    export_enabled: bool = True
    hide_sensitive: bool = False
    encrypt_password: str = ""
    purge_enabled: bool = True
    purge_keep: int = 10
    bin_dir: Path = Path("/var/lib/oxidized/bin")
    rsc_dir: Path = Path("/var/lib/oxidized/rsc")
    timeout: int = 300

    @classmethod
    def from_django(cls) -> MikrotikBackupConfig:
        from services.backup_settings import get_mikrotik_config

        return get_mikrotik_config()


def device_file_prefix(name: str) -> str:
    safe = re.sub(r"[^\w.-]+", "_", name).strip("_") or "device"
    try:
        from core.models import Device

        device_id = Device.objects.filter(name=name).values_list("id", flat=True).first()
        if device_id:
            return f"{device_id}_{safe}"
    except Exception:
        pass
    return safe


def export_command(remote_name: str, *, hide_sensitive: bool, ros7: bool) -> str:
    """Export command matching RealMikrotikBackup n8n workflow."""
    if hide_sensitive:
        if ros7:
            return f"/export file={remote_name}"
        return f"/export hide-sensitive file={remote_name}"
    if ros7:
        return f'[:parse "/export show-sensitive file={remote_name}"]'
    return f"/export file={remote_name}"


def backup_save_command(remote_name: str, *, encrypt_password: str) -> str:
    if encrypt_password:
        return (
            f"/system backup save dont-encrypt=no encryption=aes-sha256 "
            f'name={remote_name} password="{encrypt_password}"'
        )
    return f"/system backup save dont-encrypt=yes name={remote_name}"


class MikrotikBackupError(Exception):
    pass


class MikrotikBackup:
    def __init__(self, config: MikrotikBackupConfig | None = None) -> None:
        self.config = config or MikrotikBackupConfig.from_django()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for folder in (self.config.bin_dir, self.config.rsc_dir):
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("mikrotik | cannot create dir %s: %s", folder, exc)

    def run_for_node(self, node: Node) -> dict[str, str | bool]:
        if node.model_name != "routeros":
            return {"skipped": True, "reason": "not routeros"}

        results: dict[str, str | bool] = {}
        client = self._connect(node)
        try:
            if self.config.binary_enabled:
                results["binary"] = self._backup_binary(client, node)
            else:
                logger.info("mikrotik | binary backup | %s | skipped (disabled)", node.name)
            if self.config.export_enabled:
                results["export"] = self._backup_export(client, node)
            else:
                logger.info("mikrotik | export backup | %s | skipped (disabled)", node.name)
        finally:
            client.close()
        return results

    def list_files(self, name: str) -> dict[str, list[dict[str, str | int]]]:
        prefix = device_file_prefix(name)
        return {
            "binary": self._list_dir(self.config.bin_dir, prefix, ".backup"),
            "export": self._list_dir(self.config.rsc_dir, prefix, ".rsc"),
        }

    def resolve_download(self, name: str, backup_type: str, filename: str) -> Path:
        prefix = device_file_prefix(name)
        base = self.config.bin_dir if backup_type == "bin" else self.config.rsc_dir
        path = (base / filename).resolve()
        if not str(path).startswith(str(base.resolve())):
            raise MikrotikBackupError("invalid path")
        if not path.name.startswith(prefix):
            raise MikrotikBackupError("file not found")
        if not path.is_file():
            raise MikrotikBackupError("file not found")
        return path

    def _list_dir(self, folder: Path, prefix: str, suffix: str) -> list[dict[str, str | int]]:
        if not folder.is_dir():
            return []
        items: list[dict[str, str | int]] = []
        for path in sorted(folder.glob(f"{prefix}*{suffix}"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = path.stat()
            items.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                }
            )
        return items

    def _connect(self, node: Node) -> paramiko.SSHClient:
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
            raise MikrotikBackupError(str(exc)) from exc
        return client

    def _exec(self, client: paramiko.SSHClient, command: str) -> str:
        _, stdout, stderr = client.exec_command(command, timeout=self.config.timeout)
        output = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if err.strip() and not output.strip():
            output = err
        return output

    def _remote_file_listed(self, client: paramiko.SSHClient, filename: str) -> bool:
        listing = self._exec(client, "/file print")
        return filename in listing

    def _resolve_sftp_path(
        self,
        sftp: paramiko.SFTPClient,
        filename: str,
        *,
        client: paramiko.SSHClient | None = None,
        wait_timeout: int | None = None,
    ) -> str:
        timeout = wait_timeout or min(self.config.timeout, 120)
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            if client and self._remote_file_listed(client, filename):
                pass
            for candidate in (filename, f"./{filename}"):
                try:
                    sftp.stat(candidate)
                    return candidate
                except OSError as exc:
                    last_error = str(exc)
            time.sleep(_POLL_INTERVAL_SEC)
        raise MikrotikBackupError(
            f"remote file not found: {filename} (waited {timeout}s, last: {last_error})"
        )

    def _sftp_get(
        self,
        client: paramiko.SSHClient,
        remote: str,
        local: Path,
        *,
        wait_timeout: int | None = None,
    ) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        with client.open_sftp() as sftp:
            remote_path = self._resolve_sftp_path(
                sftp,
                remote,
                client=client,
                wait_timeout=wait_timeout,
            )
            sftp.get(remote_path, str(local))

    def _ros7(self, client: paramiko.SSHClient) -> bool:
        resource = self._exec(client, "/system resource print")
        match = re.search(r"version:\s*(\d+)", resource)
        if match:
            return int(match.group(1)) >= 7
        pkg = self._exec(client, "/system package update print")
        for line in pkg.splitlines():
            if "installed-version:" in line or "current-version:" in line:
                ver_match = re.search(r"(\d+)", line)
                if ver_match:
                    return int(ver_match.group(1)) >= 7
        return False

    def _backup_binary(self, client: paramiko.SSHClient, node: Node) -> bool:
        prefix = device_file_prefix(node.name)
        remote_base = f"{prefix}.backup"
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        local_stamp = self.config.bin_dir / f"{prefix}_{stamp}.backup"
        local_last = self.config.bin_dir / f"{prefix}_last.backup"

        logger.info("mikrotik | binary backup | %s | start", node.name)
        cmd = backup_save_command(prefix, encrypt_password=self.config.encrypt_password)
        save_out = self._exec(client, cmd)
        if re.search(r"(failure:|status: failed|could not create|not enough (disk )?space)", save_out, re.I):
            raise MikrotikBackupError(f"backup save rejected: {save_out[:300].strip()}")
        self._sftp_get(client, remote_base, local_stamp, wait_timeout=180)
        shutil.copy2(local_stamp, local_last)
        self._exec(client, f'/file remove "{remote_base}"')

        if self.config.purge_enabled:
            self._purge_old(self.config.bin_dir, prefix)

        size = local_stamp.stat().st_size
        logger.info(
            "mikrotik | binary backup | %s -> %s (%d bytes)",
            node.name,
            local_stamp.name,
            size,
        )
        return True

    def _backup_export(self, client: paramiko.SSHClient, node: Node) -> bool:
        prefix = device_file_prefix(node.name)
        remote_base = prefix
        remote_file = f"{remote_base}.rsc"
        local_file = self.config.rsc_dir / f"{prefix}.rsc"

        hide = node.vars.get("remove_secret")
        if hide is None:
            hide = self.config.hide_sensitive
        else:
            hide = str(hide).lower() in ("1", "true", "yes")

        ros7 = self._ros7(client)
        cmd = export_command(remote_base, hide_sensitive=bool(hide), ros7=ros7)
        logger.info(
            "mikrotik | export backup | %s | start (ros%d, hide_sensitive=%s)",
            node.name,
            7 if ros7 else 6,
            hide,
        )
        self._exec(client, cmd)
        self._sftp_get(client, remote_file, local_file, wait_timeout=90)
        self._exec(client, f'/file remove "{remote_file}"')
        self._clean_export_header(local_file)

        size = local_file.stat().st_size
        logger.info(
            "mikrotik | export backup | %s -> %s (%d bytes)",
            node.name,
            local_file.name,
            size,
        )
        return True

    def _clean_export_header(self, path: Path) -> None:
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        cleaned = re.sub(r"^#.*by", "#", text, flags=re.MULTILINE)
        if cleaned != text:
            path.write_text(cleaned, encoding="utf-8")

    def _purge_old(self, folder: Path, prefix: str) -> None:
        keep = max(1, self.config.purge_keep)
        dated = [
            path
            for path in folder.glob(f"{prefix}_*.backup")
            if not path.name.endswith("_last.backup")
        ]
        dated.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for path in dated[keep:]:
            path.unlink(missing_ok=True)
            logger.info("mikrotik | purge | removed %s", path.name)


def run_mikrotik_backups(node: Node) -> bool:
    cfg = MikrotikBackupConfig.from_django()
    from services.group_policies import effective_mk_flags

    binary, export = effective_mk_flags(node.group, cfg.binary_enabled, cfg.export_enabled)
    if not binary and not export:
        logger.info("mikrotik | backup | %s | skipped (disabled for group)", node.name)
        return True
    cfg = replace(cfg, binary_enabled=binary, export_enabled=export)
    try:
        MikrotikBackup(cfg).run_for_node(node)
        try:
            from services.git_mikrotik import commit_mikrotik_backups

            commit_mikrotik_backups(node.name)
        except Exception:
            logger.exception("mikrotik | git push failed | %s", node.name)
        return True
    except MikrotikBackupError as exc:
        logger.warning("mikrotik | backup failed | %s: %s", node.name, exc)
        from services.backup_notifications import notify_backup_error

        notify_backup_error(node.name, node.ip, "mikrotik_backup", str(exc))
        return False
    except Exception as exc:
        logger.exception("mikrotik | backup failed | %s", node.name)
        from services.backup_notifications import notify_backup_error

        notify_backup_error(node.name, node.ip, "mikrotik_backup", str(exc))
        return False


def run_mikrotik_backup_by_name(name: str) -> dict[str, str | bool]:
    from django.conf import settings

    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        raise MikrotikBackupError("MikroTik backup доступен только при OXIDIZED_ENGINE=python")

    from services.oxidized_engine import get_manager

    manager = get_manager()
    manager.worker.reload()
    node = manager.nodes.find(name)
    if node.model_name != "routeros":
        raise MikrotikBackupError(f"Узел '{name}' не routeros (model={node.model_name})")

    ok = run_mikrotik_backups(node)
    if not ok:
        raise MikrotikBackupError("MikroTik backup завершился с ошибкой — см. лог Oxidized")
    return MikrotikBackup().list_files(name)
