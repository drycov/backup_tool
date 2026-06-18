"""Восстановление MikroTik из .backup / .rsc файлов."""

from __future__ import annotations

import logging

from services.mikrotik_backup import MikrotikBackup, MikrotikBackupError, device_file_prefix

logger = logging.getLogger(__name__)


def restore_mikrotik_backup(name: str, backup_type: str, filename: str) -> dict:
    """Загрузить локальный backup на устройство и выполнить load/import."""
    if backup_type not in ("bin", "rsc"):
        raise MikrotikBackupError("type must be bin or rsc")

    from django.conf import settings

    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        raise MikrotikBackupError("Restore доступен только при OXIDIZED_ENGINE=python")

    from services.oxidized_engine import get_manager

    manager = get_manager()
    manager.worker.reload()
    node = manager.nodes.find(name)
    if node.model_name != "routeros":
        raise MikrotikBackupError(f"Узел '{name}' не routeros")

    svc = MikrotikBackup()
    local_path = svc.resolve_download(name, backup_type, filename)
    prefix = device_file_prefix(name)
    remote_base = f"{prefix}_ui_restore"

    client = svc._connect(node)
    try:
        with client.open_sftp() as sftp:
            if backup_type == "bin":
                remote_file = f"{remote_base}.backup"
                sftp.put(str(local_path), remote_file)
                output = svc._exec(client, f'/system backup load name="{remote_base}"')
                action = "backup_load"
            else:
                remote_file = f"{remote_base}.rsc"
                sftp.put(str(local_path), remote_file)
                output = svc._exec(client, f'/import file-name="{remote_file}"')
                action = "import"

        logger.info("mikrotik | restore | %s | %s | %s", name, action, filename)
        return {
            "ok": True,
            "action": action,
            "file": filename,
            "remote": remote_base,
            "output": (output or "")[:2000],
        }
    finally:
        client.close()


def compare_backup_files(name: str, file_a: str, file_b: str, backup_type: str) -> dict:
    """Сравнение метаданных / diff для двух backup-файлов."""
    if backup_type not in ("bin", "rsc"):
        raise MikrotikBackupError("type must be bin or rsc")
    svc = MikrotikBackup()
    path_a = svc.resolve_download(name, backup_type, file_a)
    path_b = svc.resolve_download(name, backup_type, file_b)
    stat_a = path_a.stat()
    stat_b = path_b.stat()
    result = {
        "file_a": file_a,
        "file_b": file_b,
        "size_a": stat_a.st_size,
        "size_b": stat_b.st_size,
        "mtime_a": int(stat_a.st_mtime),
        "mtime_b": int(stat_b.st_mtime),
        "size_delta": stat_b.st_size - stat_a.st_size,
    }
    if backup_type == "rsc":
        text_a = path_a.read_text(encoding="utf-8", errors="replace")
        text_b = path_b.read_text(encoding="utf-8", errors="replace")
        import difflib

        diff = list(
            difflib.unified_diff(
                text_a.splitlines(),
                text_b.splitlines(),
                fromfile=file_a,
                tofile=file_b,
                lineterm="",
            )
        )
        result["diff_lines"] = len(diff)
        result["diff"] = "\n".join(diff[:500])
    return result
