import time

from django.core.management.base import BaseCommand

from database_management.transfers import claim_one, cleanup_expired, execute_claimed


class Command(BaseCommand):
    help = "Run one database import/export task worker"

    def add_arguments(self, parser):
        parser.add_argument("--poll-interval", type=float, default=1.0)

    def handle(self, *args, **options):
        interval = max(0.2, options["poll_interval"])
        last_cleanup = 0.0
        self.stdout.write("Database transfer worker started")
        while True:
            now = time.monotonic()
            if now - last_cleanup >= 60:
                cleanup_expired(); last_cleanup = now
            task = claim_one()
            if task is None:
                time.sleep(interval)
                continue
            execute_claimed(task)
