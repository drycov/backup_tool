from django.core.management.base import BaseCommand

from services.audit import purge_old_audit_events


class Command(BaseCommand):
    help = "Удалить записи аудита старше AUDIT_RETENTION_DAYS"

    def handle(self, *args, **options):
        result = purge_old_audit_events()
        self.stdout.write(
            self.style.SUCCESS(
                f"audit purge | deleted={result.get('deleted', 0)} "
                f"retention_days={result.get('retention_days', 0)}"
            )
        )
