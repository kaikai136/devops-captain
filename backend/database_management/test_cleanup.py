from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from .models import AssetDirectory, DatabaseAsset, DatabaseTransferTask, SavedDatabaseQuery
from .transfers import request_task_cancellation


class ConnectionCleanupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cleanup")
        self.directory = AssetDirectory.objects.create(name="keep")
        self.asset = DatabaseAsset.objects.create(name="local", host="unused", username="user", directory=self.directory)
        SavedDatabaseQuery.objects.create(owner=self.user, asset=self.asset, name="saved", sql="SELECT 1")
        self.emitter = patch("database_management.transfers.emit")
        self.emitter.start()
        self.addCleanup(self.emitter.stop)

    def task(self, **values):
        return DatabaseTransferTask.objects.create(owner=self.user, asset=self.asset, scope="database", direction="export", format="sql", expires_at=timezone.now() + timedelta(days=1), **values)

    def test_preview_changes_nothing(self):
        task = self.task()
        output = StringIO()
        call_command("clear_database_connections", stdout=output)
        self.assertIn("Connections: 1; saved queries: 1; active transfers: 1", output.getvalue())
        self.assertEqual(DatabaseAsset.objects.count(), 1)
        self.assertEqual(SavedDatabaseQuery.objects.count(), 1)
        task.refresh_from_db()
        self.assertFalse(task.cancel_requested)

    def test_running_task_blocks_deletion_and_persists_cancellation(self):
        task = self.task(status="running", stage="exporting")
        with self.assertRaises(CommandError):
            call_command("clear_database_connections", execute=True, stdout=StringIO())
        task.refresh_from_db()
        self.assertEqual(task.status, "cancel_requested")
        self.assertTrue(task.cancel_requested)
        self.assertEqual(DatabaseAsset.objects.count(), 1)
        self.assertEqual(SavedDatabaseQuery.objects.count(), 1)
        task.status = "cancelled"
        task.save()
        call_command("clear_database_connections", execute=True, stdout=StringIO())
        self.assertEqual(DatabaseAsset.objects.count(), 0)

    def test_execution_cancels_pending_and_preserves_directories_history_and_files(self):
        with TemporaryDirectory() as directory:
            result = Path(directory) / "result.zip"
            result.write_bytes(b"existing-result")
            history = self.task(status="succeeded", output_path=str(result))
            pending = [self.task(status=status, stage=stage) for status, stage in (
                ("queued", "queued"), ("uploading", "uploading"),
                ("awaiting_confirmation", "awaiting_confirmation"), ("inspecting", "inspection_queued"),
            )]
            call_command("clear_database_connections", execute=True, stdout=StringIO())
            self.assertEqual(DatabaseAsset.objects.count(), 0)
            self.assertEqual(SavedDatabaseQuery.objects.count(), 0)
            self.assertTrue(AssetDirectory.objects.filter(pk=self.directory.pk).exists())
            for task in pending:
                task.refresh_from_db()
                self.assertEqual(task.status, "cancelled")
                self.assertTrue(task.cancel_requested)
                self.assertIsNone(task.asset_id)
            history.refresh_from_db()
            self.assertEqual(history.status, "succeeded")
            self.assertEqual(history.output_path, str(result))
            self.assertEqual(result.read_bytes(), b"existing-result")
            call_command("clear_database_connections", execute=True, stdout=StringIO())
            self.assertEqual(DatabaseTransferTask.objects.count(), len(pending) + 1)

    def test_worker_claim_race_requests_running_cancellation_instead_of_marking_complete(self):
        task = self.task(status="queued", stage="queued")
        original = task.refresh_from_db

        def claim_first(*args, **kwargs):
            DatabaseTransferTask.objects.filter(pk=task.pk, status="queued").update(status="running", stage="starting")
            original(*args, **kwargs)

        with patch.object(task, "refresh_from_db", side_effect=claim_first):
            request_task_cancellation(task)
        self.assertEqual(task.status, "cancel_requested")
        self.assertIsNone(task.finished_at)

    def test_connection_manifest_import_without_asset_is_cancelled_too(self):
        task = self.task(status="queued")
        task.asset = None
        task.scope = "connections"
        task.direction = "import"
        task.format = "json"
        task.save()
        call_command("clear_database_connections", execute=True, stdout=StringIO())
        task.refresh_from_db()
        self.assertEqual(task.status, "cancelled")
        self.assertEqual(DatabaseAsset.objects.count(), 0)
