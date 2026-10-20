from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from database_management.models import DatabaseAsset, DatabaseTransferTask, SavedDatabaseQuery
from database_management.transfers import ACTIVE, request_task_cancellation


class Command(BaseCommand):
    help = "Preview database connection/query cleanup; --execute cancels transfers and deletes local connection records only."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", help="Explicitly delete all current-environment connection assets and saved queries")

    def handle(self, *args, **options):
        asset_ids = list(DatabaseAsset.objects.values_list("id", flat=True))
        queries = SavedDatabaseQuery.objects.filter(asset_id__in=asset_ids)
        related_tasks = Q(asset_id__in=asset_ids) | Q(scope="connections")
        tasks = DatabaseTransferTask.objects.filter(related_tasks, status__in=ACTIVE)
        self.stdout.write(f"Connections: {len(asset_ids)}; saved queries: {queries.count()}; active transfers: {tasks.count()}")
        if not options["execute"]:
            self.stdout.write("Preview only. Use --execute to cancel transfers and delete these local records.")
            return

        # Cancellation must commit even when a running worker prevents deletion.
        for task in tasks:
            request_task_cancellation(task)
        with transaction.atomic():
            assets = DatabaseAsset.objects.select_for_update().filter(id__in=asset_ids)
            list(assets.values_list("id", flat=True))
            remaining = DatabaseTransferTask.objects.select_for_update().filter(related_tasks, status__in=ACTIVE)
            if remaining.exists():
                raise CommandError("Cancellation requested; running transfers must finish before cleanup. Re-run after workers stop these tasks.")
            if DatabaseAsset.objects.exclude(id__in=asset_ids).exists():
                raise CommandError("Connections changed during cleanup. Re-run after connection changes stop.")
            query_count = queries.count()
            asset_count = assets.count()
            assets.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted connections: {asset_count}; saved queries: {query_count}. Directories, task history and result files retained."))
