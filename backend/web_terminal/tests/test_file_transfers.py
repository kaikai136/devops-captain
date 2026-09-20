from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import asyncssh
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from host_management.models import HostGroup, ManagedHost
from system_management.services import FEATURE_PERMISSION_CODE_BY_KEY, PAGE_ACTION_PERMISSION_CODE_BY_KEY, ensure_feature_permissions
from web_terminal.gateway.server import RemoteSFTPFile
from web_terminal.models import TerminalFileAudit
from web_terminal.services import (
    borrow_ssh_client,
    clear_ssh_client_pool,
    upload_remote_file_with_sftp_stream,
)


class _ActiveTransport:
    def is_active(self):
        return True


class _PooledClient:
    def __init__(self):
        self.transport = _ActiveTransport()
        self.closed = False

    def get_transport(self):
        return self.transport

    def close(self):
        self.closed = True


class SshClientPoolTests(SimpleTestCase):
    def tearDown(self):
        clear_ssh_client_pool()

    def test_borrow_reuses_idle_client_for_same_host_and_credentials(self):
        host = SimpleNamespace(
            pk=7,
            public_ip="203.0.113.7",
            private_ip="10.0.0.7",
            port=22,
            login_user="root",
            login_password="secret",
            private_key="",
        )
        client = _PooledClient()

        with patch("web_terminal.services.connections.open_ssh_client", return_value=client) as opener:
            with borrow_ssh_client(host) as first:
                self.assertIs(first, client)
            with borrow_ssh_client(host) as second:
                self.assertIs(second, client)

        self.assertEqual(opener.call_count, 1)
        self.assertFalse(client.closed)
        clear_ssh_client_pool()
        self.assertTrue(client.closed)


class StreamingUploadServiceTests(SimpleTestCase):
    def test_sftp_upload_streams_chunks_to_temp_file_then_renames(self):
        writes = []

        class Source:
            def __init__(self):
                self.seek_calls = []

            def seek(self, offset):
                self.seek_calls.append(offset)

            def chunks(self, chunk_size):
                self.chunk_size = chunk_size
                yield b"abc"
                yield b"defg"

        class RemoteFile:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def write(self, data):
                writes.append(data)

        sftp = MagicMock()
        sftp.open.return_value = RemoteFile()
        sftp.posix_rename = MagicMock()
        client = MagicMock()
        client.open_sftp.return_value = sftp
        source = Source()

        with patch("web_terminal.services.files.borrow_ssh_client", return_value=nullcontext(client)), patch(
            "web_terminal.services.files.ensure_remote_sftp_directory"
        ), patch(
            "web_terminal.services.files.temporary_remote_upload_path",
            return_value="/srv/.report.txt.upload-test",
        ):
            payload = upload_remote_file_with_sftp_stream(object(), "/srv/report.txt", source)

        self.assertEqual(writes, [b"abc", b"defg"])
        self.assertEqual(payload["size"], 7)
        self.assertEqual(source.seek_calls, [0])
        sftp.open.assert_called_once_with("/srv/.report.txt.upload-test", "wb")
        sftp.posix_rename.assert_called_once_with("/srv/.report.txt.upload-test", "/srv/report.txt")
        sftp.close.assert_called_once_with()


class MultipartUploadApiTests(TestCase):
    def setUp(self):
        ensure_feature_permissions()
        self.user = get_user_model().objects.create_user(username="file-upload-operator", password="pass")
        role = Group.objects.create(name="file-upload-terminal-role")
        role.permissions.add(
            Permission.objects.get(codename=FEATURE_PERMISSION_CODE_BY_KEY["hosts"]),
            Permission.objects.get(codename=PAGE_ACTION_PERMISSION_CODE_BY_KEY[("hosts", "terminal")]),
        )
        self.user.groups.add(role)
        self.client.force_login(self.user)
        self.group = HostGroup.objects.create(name="file-upload-tests")
        self.host = ManagedHost.objects.create(
            name="upload-host",
            group=self.group,
            private_ip="10.0.0.20",
            login_user="root",
        )

    def test_upload_endpoint_prefers_multipart_stream_and_records_audit(self):
        uploaded = SimpleUploadedFile("report.txt", b"stream-me", content_type="text/plain")
        payload = {
            "path": "/srv/folder/report.txt",
            "protocol": "SFTP protocol",
            "size": 9,
            "attempts": [{"protocol": "SFTP protocol", "status": "success"}],
        }

        with patch("web_terminal.api.files.upload_remote_file_stream", return_value=payload) as stream_upload, patch(
            "web_terminal.api.files.upload_remote_file"
        ) as legacy_upload:
            response = self.client.post(
                f"/api/web-terminal/hosts/{self.host.id}/files/upload/",
                data={
                    "directory": "/srv",
                    "filename": "report.txt",
                    "relativePath": "folder/report.txt",
                    "file": uploaded,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["size"], 9)
        stream_upload.assert_called_once()
        args = stream_upload.call_args.args
        self.assertEqual(args[0], self.host)
        self.assertEqual(args[1:3], ("/srv", "report.txt"))
        self.assertEqual(args[4], "folder/report.txt")
        legacy_upload.assert_not_called()

        audit = TerminalFileAudit.objects.get()
        self.assertEqual(audit.operation, TerminalFileAudit.OPERATION_WRITE)
        self.assertEqual(audit.username, self.user.username)
        self.assertEqual(audit.host, self.host)
        self.assertEqual(audit.path, "/srv/folder/report.txt")
        self.assertEqual(audit.size, 9)
        self.assertEqual(audit.protocol, "sftp")


class GatewayTransferAuditTests(SimpleTestCase):
    def test_remote_sftp_file_records_one_read_audit_on_close(self):
        class RemoteFile:
            def __init__(self):
                self.data = b"abcdef"

            def seek(self, offset):
                self.offset = offset

            def read(self, size):
                return self.data[self.offset:self.offset + size]

            def close(self):
                pass

        remote_file = RemoteFile()
        sftp = MagicMock()
        sftp.open.return_value = remote_file
        client = MagicMock()
        client.open_sftp.return_value = sftp

        with patch("web_terminal.gateway.server.open_ssh_client", return_value=client), patch(
            "web_terminal.gateway.server.record_file_audit"
        ) as record:
            handle = RemoteSFTPFile(object(), None, "/tmp/data.bin", asyncssh.FXF_READ)
            self.assertEqual(handle.read(0, 3), b"abc")
            self.assertEqual(handle.read(3, 3), b"def")
            handle.close()

        record.assert_called_once()
        self.assertEqual(record.call_args.kwargs["operation"], "read")
        self.assertEqual(record.call_args.kwargs["path"], "/tmp/data.bin")
        self.assertEqual(record.call_args.kwargs["size"], 6)
        self.assertEqual(record.call_args.kwargs["status"], "success")
