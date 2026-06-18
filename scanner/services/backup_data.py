"""Резервное копирование БД и inventory на диск."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def backup_destination() -> Path:
    from services.system_settings import get_config

    return Path(get_config().backup_data_dir)


def run_backup_data() -> dict:
    dest_root = backup_destination()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = dest_root / stamp
    dest.mkdir(parents=True, exist_ok=True)

    results: dict = {"path": str(dest), "ok": True}

    db_cfg = settings.DATABASES.get("default", {})
    engine = db_cfg.get("ENGINE", "")
    if "sqlite3" in engine:
        src = Path(str(db_cfg.get("NAME", "")))
        if src.is_file():
            shutil.copy2(src, dest / "scanner.db")
            results["database"] = "sqlite copied"
        else:
            results["database"] = "sqlite not found"
            results["ok"] = False
    elif "postgresql" in engine:
        env = os.environ.copy()
        env["PGPASSWORD"] = str(db_cfg.get("PASSWORD", ""))
        dump_path = dest / "inventory.sql"
        cmd = [
            "pg_dump",
            "-h",
            str(db_cfg.get("HOST", "localhost")),
            "-p",
            str(db_cfg.get("PORT", "5432")),
            "-U",
            str(db_cfg.get("USER", "")),
            "-d",
            str(db_cfg.get("NAME", "")),
            "-f",
            str(dump_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
            results["database"] = "postgresql dump"
        except FileNotFoundError:
            results["database"] = "pg_dump not found"
            results["ok"] = False
        except subprocess.CalledProcessError as exc:
            results["database"] = (exc.stderr or str(exc))[:200]
            results["ok"] = False
    else:
        results["database"] = f"unsupported: {engine}"
        results["ok"] = False

    for env_key in ("INVENTORY_PATH", "NETWORK_INVENTORY_PATH"):
        src = Path(os.environ.get(env_key, "") or getattr(settings, env_key, ""))
        if src.is_file():
            shutil.copy2(src, dest / src.name)
            results[src.name] = "copied"

    logger.info("backup_data | %s ok=%s", dest, results["ok"])
    return results
