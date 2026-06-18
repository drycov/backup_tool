from django.core.management.base import BaseCommand

from services.task_worker import tick


class Command(BaseCommand):
    help = "Обработка очереди фоновых задач (degrade, compliance, scheduled scan)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Один цикл и выход",
        )
        parser.add_argument(
            "--poll",
            type=int,
            default=30,
            help="Интервал опроса в секундах",
        )

    def handle(self, *args, **options):
        import os
        import time

        os.environ["TASK_WORKER_INLINE"] = "false"
        poll = max(10, options["poll"])
        if options["once"]:
            tick()
            return
        self.stdout.write(self.style.SUCCESS(f"task worker started | poll={poll}s"))
        while True:
            tick()
            time.sleep(poll)
