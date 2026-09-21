from django.core.management.base import BaseCommand

from services.scheduler import run_scheduler


class Command(BaseCommand):
    help = "APScheduler для периодических scan/discovery и сервисных задач"

    def handle(self, *args, **options):
        run_scheduler()
