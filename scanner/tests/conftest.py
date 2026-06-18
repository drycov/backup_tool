"""Pytest bootstrap — env before Django settings load."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / ".pytest_smoke.db"

os.environ["DATABASE_URL"] = f"sqlite:////{DB_FILE.resolve().as_posix().lstrip('/')}"
os.environ["JWT_SECRET"] = "pytest-secret-min-32-characters-long"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "pytest-admin-pass"
os.environ["OXIDIZED_ENGINE"] = "python"
