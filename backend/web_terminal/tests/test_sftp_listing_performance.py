from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from web_terminal.services import list_remote_directory_with_sftp


class DirectoryListingPerformanceTests(SimpleTestCase):
    def test_sftp_listing_reads_directory_once_without_legacy_find_scan(self):
        host = SimpleNamespace(
            pk=7,
            public_ip="203.0.113.7",
            private_ip="10.0.0.7",
            port=22,
            login_user="root",
            login_password="secret",
            private_key="",
        )
        client = MagicMock()
        sftp = MagicMock()
        sftp.normalize.return_value = "/srv"
        sftp.listdir_attr.return_value = [
            SimpleNamespace(filename="logs", st_mode=0o40755, st_mtime=1, st_size=4096, st_uid=0, st_gid=0),
            SimpleNamespace(filename="app.log", st_mode=0o100644, st_mtime=2, st_size=128, st_uid=1000, st_gid=1000),
        ]

        with patch(
            "web_terminal.services.files.borrow_sftp_client",
            return_value=nullcontext((client, sftp, True)),
        ), patch(
            "web_terminal.services.files.enrich_remote_entries_with_identities"
        ) as enrich_identities, patch(
            "web_terminal.services.files.enrich_remote_entries_with_stat"
        ) as legacy_enrich:
            payload = list_remote_directory_with_sftp(host, "/srv")

        sftp.normalize.assert_called_once_with("/srv")
        sftp.listdir_attr.assert_called_once_with("/srv")
        enrich_identities.assert_called_once()
        legacy_enrich.assert_not_called()
        self.assertEqual(payload["metrics"]["entryCount"], 2)
        self.assertTrue(payload["metrics"]["sessionReused"])
        self.assertEqual([entry["name"] for entry in payload["entries"]], ["..", "logs", "app.log"])
