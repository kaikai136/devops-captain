from contextlib import nullcontext
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from host_management.models import HostGroup, ManagedHost
from web_terminal.models import TerminalFileAudit
from web_terminal.services import TerminalConnectionError, update_remote_file_content


class FileContentApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="file-editor", password="pass")
        self.client.force_login(self.user)
        self.host = ManagedHost.objects.create(
            name="editor-host", group=HostGroup.objects.create(name="editor-tests"),
            private_ip="10.0.0.7", login_user="root",
        )
        self.base = f"/api/web-terminal/hosts/{self.host.id}/files/content/"

    def test_reads_stream_without_size_limit_and_records_audit(self):
        payload = {"filename": "test.png", "content": iter([b"abc", b"def"]), "size": 6, "protocol": "sftp"}
        with patch("web_terminal.api.files.stream_remote_file_content", return_value=payload) as read:
            response = self.client.get(self.base, {"path": "/srv/test.png"})
            self.assertEqual(b"".join(response.streaming_content), b"abcdef")
        read.assert_called_once_with(self.host, "/srv/test.png", "auto")
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))
        self.assertEqual(response["Content-Length"], "6")
        self.assertEqual(response["Cache-Control"], "no-store")
        audit = TerminalFileAudit.objects.get()
        self.assertEqual(audit.operation, "read")
        self.assertEqual(audit.size, 6)

    def test_read_failure_is_audited(self):
        with patch("web_terminal.api.files.stream_remote_file_content", side_effect=TerminalConnectionError("denied")):
            response = self.client.get(self.base, {"path": "/srv/test.txt"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TerminalFileAudit.objects.get().status, "failed")

    def test_saves_multipart_to_original_path_and_audits(self):
        with patch("web_terminal.api.files.update_remote_file_content", return_value={"path": "/srv/test.txt", "size": 3, "protocol": "ssh"}) as write:
            response = self.client.post(self.base + "update/", {"path": "/srv/test.txt", "file": SimpleUploadedFile("test.txt", b"new")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(write.call_args.args[1], "/srv/test.txt")
        audit = TerminalFileAudit.objects.get()
        self.assertEqual((audit.operation, audit.size, audit.path), ("write", 3, "/srv/test.txt"))

    def test_empty_file_and_failed_save(self):
        with patch("web_terminal.api.files.update_remote_file_content", side_effect=TerminalConnectionError("write denied")):
            response = self.client.post(self.base + "update/", {"path": "/srv/test.txt", "file": SimpleUploadedFile("test.txt", b"")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TerminalFileAudit.objects.get().status, "failed")

    def test_requires_terminal_permission(self):
        user = get_user_model().objects.create_user(username="no-terminal", password="pass")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.base, {"path": "/srv/a"}).status_code, 403)
        self.assertEqual(self.client.post(self.base + "update/", {}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.base).status_code, 401)


class FileContentSaveTests(SimpleTestCase):
    def test_stages_complete_bytes_before_replacing_resolved_target(self):
        client = MagicMock()
        stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
        client.exec_command.return_value = (stdin, stdout, stderr)
        stderr.read.return_value = b""
        stdout.channel.recv_exit_status.return_value = 0
        with patch("web_terminal.services.files.resolve_remote_file_path", return_value="/srv/actual.txt"), patch(
            "web_terminal.services.files.borrow_ssh_client", return_value=nullcontext(client)
        ), patch("web_terminal.services.files.temporary_remote_upload_path", return_value="/srv/.temp"):
            result = update_remote_file_content(object(), "/srv/link.txt", BytesIO(b"new"))
        command = client.exec_command.call_args.args[0]
        self.assertIn("cp -p -- /srv/actual.txt /srv/.temp", command)
        self.assertIn("test $(wc -c < /srv/.temp) -eq 3", command)
        self.assertIn("mv -f -- /srv/.temp /srv/actual.txt", command)
        stdin.write.assert_called_once_with(b"new")
        self.assertEqual(result["size"], 3)

    def test_failed_save_only_cleans_staging_file(self):
        client = MagicMock()
        stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
        client.exec_command.return_value = (stdin, stdout, stderr)
        stderr.read.return_value = b"permission denied"
        stdout.channel.recv_exit_status.return_value = 1
        with patch("web_terminal.services.files.resolve_remote_file_path", return_value="/srv/actual.txt"), patch(
            "web_terminal.services.files.borrow_ssh_client", return_value=nullcontext(client)
        ), patch("web_terminal.services.files.temporary_remote_upload_path", return_value="/srv/.temp"):
            with self.assertRaises(TerminalConnectionError):
                update_remote_file_content(object(), "/srv/link.txt", BytesIO(b"new"))
        self.assertEqual(client.exec_command.call_args.args[0], "rm -f -- /srv/.temp")
