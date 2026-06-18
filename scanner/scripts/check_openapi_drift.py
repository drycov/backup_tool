#!/usr/bin/env python3
"""Generate or verify OpenAPI snapshot (CI drift check)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "openapi.snapshot.json"


def _canonical(spec: dict) -> str:
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAPI snapshot for Backup Tools")
    parser.add_argument("--write", action="store_true", help="Write openapi.snapshot.json")
    parser.add_argument("--check", action="store_true", help="Fail if live spec differs from snapshot")
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.error("Specify --write or --check")

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backup_tools.settings")
    sys.path.insert(0, str(ROOT))

    import django

    django.setup()

    from services.openapi_spec import build_openapi_spec

    spec = build_openapi_spec()

    if args.write:
        SNAPSHOT.write_text(
            json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {SNAPSHOT}")
        return 0

    if not SNAPSHOT.is_file():
        print(f"Missing snapshot: {SNAPSHOT} (run with --write)", file=sys.stderr)
        return 1

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if _canonical(expected) != _canonical(spec):
        print("OpenAPI drift: live spec differs from openapi.snapshot.json", file=sys.stderr)
        print("Run: python scripts/check_openapi_drift.py --write", file=sys.stderr)
        return 1

    print("OpenAPI snapshot OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
