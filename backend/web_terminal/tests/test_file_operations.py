import errno
import os
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from host_management.models import HostGroup, ManagedHost
from web_terminal.models import TerminalFileAudit
from web_terminal.services.file_operations import FileOperationError, transfer_files


class LocalSftp:
    def __init__(self, root):
        self.root = Path(root)
        self.fail_publish = False
        self.fail_write = False

    def local(self, path):
        return self.root.joinpath(*path.strip('/').split('/'))

    def normalize(self, path):
        resolved = self.local(path if path.startswith('/') else '/src/' + path).resolve()
        return '/' + resolved.relative_to(self.root.resolve()).as_posix()

    def stat(self, path):
        return self.local(path).stat()

    def lstat(self, path):
        return self.local(path).lstat()

    def listdir(self, path):
        return os.listdir(self.local(path))

    def mkdir(self, path, mode=0o777):
        self.local(path).mkdir(mode=mode)

    def chmod(self, path, mode):
        self.local(path).chmod(mode)

    def utime(self, path, times):
        os.utime(self.local(path), times)

    def open(self, path, mode):
        if self.fail_write and mode == 'wx':
            raise OSError(errno.EIO, 'write failed')
        return self.local(path).open('xb' if mode == 'wx' else mode)

    def remove(self, path):
        self.local(path).unlink()

    def rmdir(self, path):
        self.local(path).rmdir()

    def rename(self, source, destination):
        if self.fail_publish and '.captain-operation-' in source and destination == '/target/b.txt':
            self.fail_publish = False
            raise OSError(errno.EACCES, 'publish denied')
        if os.path.lexists(self.local(destination)):
            raise FileExistsError(errno.EEXIST, 'destination exists')
        self.local(source).rename(self.local(destination))

    def readlink(self, path):
        return os.readlink(self.local(path))

    def symlink(self, target, destination):
        self.local(destination).symlink_to(target)


class RemoteFileOperationTests(SimpleTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sftp = LocalSftp(self.temp.name)
        self.sftp.local('/src').mkdir()
        self.sftp.local('/target').mkdir()
        self.sftp.local('/src/a.txt').write_bytes(b'new-a')
        self.sftp.local('/src/b.txt').write_bytes(b'new-b')
        context = patch('web_terminal.services.file_operations.borrow_sftp_client', side_effect=lambda _host: nullcontext((None, self.sftp, False)))
        context.start()
        self.addCleanup(context.stop)

    def assert_no_temporary_entries(self):
        self.assertFalse(any(path.name.startswith('.captain-') for path in Path(self.temp.name).rglob('*')))

    def test_copy_keeps_source_and_move_removes_source(self):
        result = transfer_files(None, ['/src/a.txt'], '/target', 'copy')
        self.assertEqual(result['items'], [{'path': '/src/a.txt', 'targetPath': '/target/a.txt'}])
        self.assertEqual(self.sftp.local('/target/a.txt').read_bytes(), b'new-a')
        self.assertTrue(self.sftp.local('/src/a.txt').exists())
        transfer_files(None, ['/src/b.txt'], '/target', 'move')
        self.assertFalse(self.sftp.local('/src/b.txt').exists())
        self.assertEqual(self.sftp.local('/target/b.txt').read_bytes(), b'new-b')
        self.assert_no_temporary_entries()

    def test_overwrite_requires_confirmation(self):
        self.sftp.local('/target/a.txt').write_bytes(b'original')
        with self.assertRaises(FileOperationError) as caught:
            transfer_files(None, ['/src/a.txt'], '/target', 'copy')
        self.assertEqual(caught.exception.code, 'file_exists')
        self.assertEqual(self.sftp.local('/target/a.txt').read_bytes(), b'original')
        transfer_files(None, ['/src/a.txt'], '/target', 'copy', True)
        self.assertEqual(self.sftp.local('/target/a.txt').read_bytes(), b'new-a')
        self.assert_no_temporary_entries()

    def test_preserves_empty_binary_bom_and_crlf_bytes(self):
        for index, content in enumerate((b'', b'\xef\xbb\xbfhello\r\nworld\r\n', bytes(range(256)))):
            path = f'/src/bytes-{index}'
            self.sftp.local(path).write_bytes(content)
            transfer_files(None, [path], '/target', 'copy')
            self.assertEqual(self.sftp.local(f'/target/bytes-{index}').read_bytes(), content)
        self.assert_no_temporary_entries()

    def test_batch_preflight_detects_all_missing_sources_before_writes(self):
        with self.assertRaises(FileOperationError) as caught:
            transfer_files(None, ['/src/a.txt', '/missing'], '/target', 'move')
        self.assertEqual(caught.exception.code, 'source_not_found')
        self.assertEqual(self.sftp.local('/src/a.txt').read_bytes(), b'new-a')
        self.assertEqual(list(self.sftp.local('/target').iterdir()), [])

    def test_rejects_invalid_control_characters(self):
        for path in ('/src/a\n.txt', '/src/a\x00.txt'):
            with self.subTest(path=path), self.assertRaises(FileOperationError) as caught:
                transfer_files(None, [path], '/target', 'copy')
            self.assertEqual(caught.exception.code, 'invalid_path')
        self.assert_no_temporary_entries()

    def test_directory_move_merges_without_deleting_target_unique_files(self):
        self.sftp.local('/src/folder/nested').mkdir(parents=True)
        self.sftp.local('/src/folder/nested/empty').write_bytes(b'')
        self.sftp.local('/src/folder/shared').write_bytes(b'new')
        self.sftp.local('/target/folder').mkdir()
        self.sftp.local('/target/folder/shared').write_bytes(b'old')
        self.sftp.local('/target/folder/unique').write_bytes(b'keep')
        transfer_files(None, ['/src/folder'], '/target', 'move', True)
        self.assertFalse(self.sftp.local('/src/folder').exists())
        self.assertEqual(self.sftp.local('/target/folder/shared').read_bytes(), b'new')
        self.assertEqual(self.sftp.local('/target/folder/unique').read_bytes(), b'keep')
        self.assertEqual(self.sftp.local('/target/folder/nested/empty').read_bytes(), b'')
        self.assert_no_temporary_entries()

    def test_nested_type_conflict_does_not_change_either_tree(self):
        self.sftp.local('/src/folder').mkdir()
        self.sftp.local('/src/folder/shared').write_bytes(b'new')
        self.sftp.local('/target/folder/shared').mkdir(parents=True)
        with self.assertRaises(FileOperationError) as caught:
            transfer_files(None, ['/src/folder'], '/target', 'move', True)
        self.assertEqual(caught.exception.code, 'file_type_conflict')
        self.assertTrue(self.sftp.local('/src/folder/shared').is_file())
        self.assertTrue(self.sftp.local('/target/folder/shared').is_dir())
        self.assert_no_temporary_entries()

    def test_failed_write_preserves_originals_and_cleans_staging(self):
        self.sftp.local('/target/a.txt').write_bytes(b'old')
        self.sftp.fail_write = True
        with self.assertRaises(FileOperationError):
            transfer_files(None, ['/src/a.txt'], '/target', 'move', True)
        self.assertEqual(self.sftp.local('/src/a.txt').read_bytes(), b'new-a')
        self.assertEqual(self.sftp.local('/target/a.txt').read_bytes(), b'old')
        self.assert_no_temporary_entries()

    def test_second_publish_failure_rolls_back_whole_batch(self):
        self.sftp.local('/target/a.txt').write_bytes(b'old-a')
        self.sftp.local('/target/b.txt').write_bytes(b'old-b')
        self.sftp.fail_publish = True
        with self.assertRaises(FileOperationError):
            transfer_files(None, ['/src/a.txt', '/src/b.txt'], '/target', 'move', True)
        for name in ('a', 'b'):
            self.assertEqual(self.sftp.local(f'/src/{name}.txt').read_bytes(), f'new-{name}'.encode())
            self.assertEqual(self.sftp.local(f'/target/{name}.txt').read_bytes(), f'old-{name}'.encode())
        self.assert_no_temporary_entries()

    def test_rejects_self_descendants_root_and_missing_source(self):
        self.sftp.local('/src/folder/child').mkdir(parents=True)
        cases = [(['/src/a.txt'], '/src'), (['/src/folder'], '/src/folder/child'), (['/'], '/target'), (['/src/../src/..'], '/target'), (['/missing'], '/target')]
        for paths, target in cases:
            with self.subTest(paths=paths), self.assertRaises(FileOperationError):
                transfer_files(None, paths, target, 'copy')
        self.assert_no_temporary_entries()

    def test_symlinks_are_copied_as_links_not_followed(self):
        try:
            self.sftp.local('/src/link').symlink_to('a.txt')
        except OSError:
            self.skipTest('Local symlink creation is unavailable')
        transfer_files(None, ['/src/link'], '/target', 'copy')
        self.assertTrue(self.sftp.local('/target/link').is_symlink())
        self.assertEqual(os.readlink(self.sftp.local('/target/link')), 'a.txt')
        self.assertEqual(self.sftp.local('/src/a.txt').read_bytes(), b'new-a')
        self.assert_no_temporary_entries()


class FileOperationApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='file-operator', password='pass')
        self.client.force_login(self.user)
        self.host = ManagedHost.objects.create(name='operation-host', group=HostGroup.objects.create(name='operation-tests'), private_ip='10.0.0.7', login_user='root')
        self.url = f'/api/web-terminal/hosts/{self.host.pk}/files/transfer/'
        self.payload = {'paths': ['/src/a.txt'], 'targetDirectory': '/target', 'operation': 'copy'}

    def test_success_records_operation_source_and_target(self):
        with patch('web_terminal.api.files.transfer_remote_files', return_value={'items': [{'path': '/src/a.txt', 'targetPath': '/target/a.txt'}]}) as transfer:
            response = self.client.post(self.url, self.payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        transfer.assert_called_once_with(self.host, ['/src/a.txt'], '/target', 'copy', False)
        audit = TerminalFileAudit.objects.get()
        self.assertEqual((audit.operation, audit.path, audit.target_path, audit.protocol), ('copy', '/src/a.txt', '/target/a.txt', 'sftp'))

    def test_conflict_returns_stable_code_and_failed_audit(self):
        with patch('web_terminal.api.files.transfer_remote_files', side_effect=FileOperationError('target exists', 'file_exists', 409)):
            response = self.client.post(self.url, self.payload, content_type='application/json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'file_exists')
        self.assertEqual(TerminalFileAudit.objects.get().status, 'failed')

    def test_validates_overwrite_paths_and_operation_before_transfer(self):
        for overrides in ({'overwrite': 'false'}, {'paths': []}, {'paths': [None]}, {'paths': '/src/a'}, {'operation': 'remove'}):
            with self.subTest(overrides=overrides), patch('web_terminal.api.files.transfer_remote_files') as transfer:
                response = self.client.post(self.url, {**self.payload, **overrides}, content_type='application/json')
                self.assertEqual(response.status_code, 400)
                transfer.assert_not_called()

    def test_requires_terminal_permission(self):
        user = get_user_model().objects.create_user(username='no-file-operation', password='pass')
        self.client.force_login(user)
        self.assertEqual(self.client.post(self.url, self.payload, content_type='application/json').status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.payload, content_type='application/json').status_code, 401)
