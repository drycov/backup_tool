from django.core.management.base import BaseCommand

from services.backup_data import run_backup_data


class Command(BaseCommand):
    help = "Резервная копия БД и inventory-файлов в BACKUP_DATA_DIR"

    def handle(self, *args, **options):
        result = run_backup_data()
        self.stdout.write(f"path: {result.get('path')}")
        self.stdout.write(f"database: {result.get('database', '—')}")
        for key, value in result.items():
            if key in ("path", "ok", "database"):
                continue
            self.stdout.write(f"{key}: {value}")
        if not result.get("ok"):
            self.stderr.write(self.style.ERROR("backup failed"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("backup ok"))
