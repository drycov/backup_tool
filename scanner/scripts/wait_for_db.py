#!/usr/bin/env python
"""Ожидание PostgreSQL перед стартом Gunicorn (если DATABASE_URL — postgresql)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backup_tools.settings")


def main() -> int:
    from services.database import is_postgresql_url, resolved_database_url

    url = resolved_database_url()
    if not is_postgresql_url(url):
        return 0

    import django

    django.setup()

    from django.db import connection

    deadline = int(os.environ.get("DB_WAIT_SECONDS", "60"))
    for attempt in range(1, deadline + 1):
        try:
            connection.ensure_connection()
            print(f"database | ready (attempt {attempt})", flush=True)
            return 0
        except Exception as exc:
            print(f"database | wait {attempt}/{deadline}: {exc}", flush=True)
            time.sleep(1)

    print("database | timeout waiting for PostgreSQL", file=sys.stderr, flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
