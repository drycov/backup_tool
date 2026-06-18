"""Dump OpenAPI spec to JSON for CI drift checks."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from services.openapi_spec import build_openapi_spec


class Command(BaseCommand):
    help = "Write OpenAPI JSON snapshot (default: openapi.snapshot.json)"

    def add_arguments(self, parser):
        parser.add_argument(
            "-o",
            "--output",
            default="openapi.snapshot.json",
            help="Output file path relative to scanner/",
        )

    def handle(self, *args, **options):
        out = Path(options["output"])
        spec = build_openapi_spec()
        out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {out} ({len(spec.get('paths', {}))} paths)"))
