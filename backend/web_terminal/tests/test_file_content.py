from contextlib import nullcontext
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from host_management.models import HostGroup, ManagedHost
from web_terminal.models import TerminalFileAudit
from web_terminal.services import TerminalConnectionError, update_remote_file_content
from web_terminal.services.errors import TerminalFileChangedError


BASELINE_HASH = sha256(b"old").hexdigest()


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
            response = self.client.post(self.base + "update/", {"path": "/srv/test.txt", "expected_hash": BASELINE_HASH, "file": SimpleUploadedFile("test.txt", b"new")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(write.call_args.args[1], "/srv/test.txt")
        self.assertEqual(write.call_args.kwargs, {"expected_hash": BASELINE_HASH, "force": False})
        audit = TerminalFileAudit.objects.get()
        self.assertEqual((audit.operation, audit.size, audit.path), ("write", 3, "/srv/test.txt"))

    def test_empty_file_and_failed_save(self):
        with patch("web_terminal.api.files.update_remote_file_content", side_effect=TerminalConnectionError("write denied")):
            response = self.client.post(self.base + "update/", {"path": "/srv/test.txt", "expected_hash": BASELINE_HASH, "file": SimpleUploadedFile("test.txt", b"")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TerminalFileAudit.objects.get().status, "failed")

    def test_conflict_returns_409_and_failed_audit(self):
        with patch("web_terminal.api.files.update_remote_file_content", side_effect=TerminalFileChangedError("changed")):
            response = self.client.post(self.base + "update/", {
                "path": "/srv/test.txt", "expected_hash": BASELINE_HASH,
                "file": SimpleUploadedFile("test.txt", b"new"),
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "file_changed")
        self.assertEqual(TerminalFileAudit.objects.get().status, "failed")

    def test_force_save_explicitly_bypasses_baseline(self):
        with patch("web_terminal.api.files.update_remote_file_content", return_value={"size": 0}) as write:
            response = self.client.post(self.base + "update/", {
                "path": "/srv/test.txt", "force": "true", "file": SimpleUploadedFile("test.txt", b""),
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(write.call_args.kwargs, {"expected_hash": None, "force": True})

    def test_missing_or_invalid_baseline_and_force_do_not_write(self):
        for fields in ({}, {"expected_hash": "invalid"}, {"expected_hash": "x" * 64}, {"force": "yes"}):
            with self.subTest(fields=fields), patch("web_terminal.api.files.update_remote_file_content") as write:
                response = self.client.post(self.base + "update/", {
                    "path": "/srv/test.txt", "file": SimpleUploadedFile("test.txt", b"new"), **fields,
                })
                self.assertEqual(response.status_code, 400)
                write.assert_not_called()

    def test_requires_terminal_permission(self):
        user = get_user_model().objects.create_user(username="no-terminal", password="pass")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.base, {"path": "/srv/a"}).status_code, 403)
        self.assertEqual(self.client.post(self.base + "update/", {}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.base).status_code, 401)


class FileContentSaveTests(SimpleTestCase):
    @skipUnless(shutil.which("sh"), "Requires a POSIX shell and coreutils")
    def test_remote_save_command_checks_real_content_before_replacing(self):
        cases = (
            (b"old", b"old", b"new", False, 0),
            (b"old", b"OLD", b"new", False, 73),
            (b"old", b"OLD", b"new", True, 0),
            (b"old", b"old", b"new", False, 1),
            (b"", b"", b"new", False, 0),
            (b"old", b"old", b"", False, 0),
            (b"\xef\xbb\xbfa\r\n", b"\xef\xbb\xbfa\r\n", b"\xef\xbb\xbfnew\r\n", False, 0),
        )
        for original, current, edited, force, status in cases:
            with self.subTest(current=current, edited=edited, force=force), TemporaryDirectory() as directory:
                target = Path(directory) / "file with spaces.txt"
                staging = Path(directory) / ".staging"
                target.write_bytes(current)
                commands = []

                def execute(command, timeout):
                    if status == 1 and not commands:
                        command = "sha256sum() { return 1; }; " + command
                    result = subprocess.run([shutil.which("sh"), "-c", command], input=edited, capture_output=True, timeout=timeout)
                    commands.append((command, result.returncode))
                    stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
                    stdout.channel.recv_exit_status.return_value = result.returncode
                    stderr.read.return_value = result.stderr
                    return stdin, stdout, stderr

                client = MagicMock()
                client.exec_command.side_effect = execute
                with patch("web_terminal.services.files.resolve_remote_file_path", return_value=target.as_posix()), patch(
                    "web_terminal.services.files.borrow_ssh_client", return_value=nullcontext(client)
                ), patch("web_terminal.services.files.temporary_remote_upload_path", return_value=staging.as_posix()):
                    if status != 0:
                        error_class = TerminalFileChangedError if status == 73 else TerminalConnectionError
                        with self.assertRaises(error_class):
                            update_remote_file_content(object(), "/srv/link.txt", BytesIO(edited), expected_hash=sha256(original).hexdigest(), force=force)
                    else:
                        update_remote_file_content(object(), "/srv/link.txt", BytesIO(edited), expected_hash=sha256(original).hexdigest(), force=force)
                self.assertEqual(commands[0][1], status)
                self.assertEqual(target.read_bytes(), edited if status == 0 else current)
                self.assertFalse(staging.exists())

    def test_stages_complete_bytes_before_replacing_resolved_target(self):
        client = MagicMock()
        stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
        client.exec_command.return_value = (stdin, stdout, stderr)
        stderr.read.return_value = b""
        stdout.channel.recv_exit_status.return_value = 0
        with patch("web_terminal.services.files.resolve_remote_file_path", return_value="/srv/actual.txt"), patch(
            "web_terminal.services.files.borrow_ssh_client", return_value=nullcontext(client)
        ), patch("web_terminal.services.files.temporary_remote_upload_path", return_value="/srv/.temp"):
            result = update_remote_file_content(object(), "/srv/link.txt", BytesIO(b"new"), expected_hash=BASELINE_HASH)
        command = client.exec_command.call_args.args[0]
        self.assertIn("cp -p -- /srv/actual.txt /srv/.temp", command)
        self.assertIn("test $(wc -c < /srv/.temp) -eq 3", command)
        self.assertIn("mv -f -- /srv/.temp /srv/actual.txt", command)
        self.assertIn("current_hash=$(sha256sum < /srv/actual.txt)", command)
        self.assertIn(BASELINE_HASH, command)
        self.assertLess(command.index("cat >"), command.index("sha256sum"))
        self.assertLess(command.index("sha256sum"), command.index("mv -f"))
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
                update_remote_file_content(object(), "/srv/link.txt", BytesIO(b"new"), expected_hash=BASELINE_HASH)
        self.assertEqual(client.exec_command.call_args.args[0], "rm -f -- /srv/.temp")

    def test_conflict_cleans_only_staging_and_force_omits_hash_check(self):
        for force in (False, True):
            with self.subTest(force=force):
                client = MagicMock()
                stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
                client.exec_command.return_value = (stdin, stdout, stderr)
                stderr.read.return_value = b""
                stdout.channel.recv_exit_status.return_value = 0 if force else 73
                with patch("web_terminal.services.files.resolve_remote_file_path", return_value="/srv/actual.txt"), patch(
                    "web_terminal.services.files.borrow_ssh_client", return_value=nullcontext(client)
                ), patch("web_terminal.services.files.temporary_remote_upload_path", return_value="/srv/.temp"):
                    if force:
                        update_remote_file_content(object(), "/srv/link.txt", BytesIO(b"new"), force=True)
                    else:
                        with self.assertRaises(TerminalFileChangedError):
                            update_remote_file_content(object(), "/srv/link.txt", BytesIO(b"new"), expected_hash=BASELINE_HASH)
                command = client.exec_command.call_args_list[0].args[0]
                self.assertEqual("sha256sum" in command, not force)
                if not force:
                    self.assertEqual(client.exec_command.call_args.args[0], "rm -f -- /srv/.temp")

    def test_missing_baseline_fails_before_connecting(self):
        with patch("web_terminal.services.files.borrow_ssh_client") as connect:
            with self.assertRaises(TerminalConnectionError):
                update_remote_file_content(object(), "/srv/a", BytesIO(b"new"))
        connect.assert_not_called()
