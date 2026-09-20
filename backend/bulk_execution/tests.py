import json
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from host_management.models import HostGroup, ManagedHost
from system_management.models import SystemSetting
from system_management.services import ensure_feature_permissions

from .models import BulkExecutionResult, BulkExecutionTask, BulkExecutionTransferItem, BulkExecutionUploadFile
from .services import create_bulk_execution_task, run_bulk_execution_task


class BulkExecutionApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ops", password="secret")
        self.group = HostGroup.objects.create(name="prod", sort_order=10)
        self.linux = ManagedHost.objects.create(
            name="linux-ok",
            group=self.group,
            private_ip="10.0.0.11",
            port=2222,
            login_user="root",
            login_password="secret",
            verified=True,
            verify_status="verified",
            os="ubuntu",
        )
        self.key_host = ManagedHost.objects.create(
            name="linux-key",
            group=self.group,
            private_ip="10.0.0.12",
            login_user="deploy",
            private_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----",
            verified=True,
            verify_status="verified",
            os="centos",
        )
        self.windows = ManagedHost.objects.create(
            name="windows",
            group=self.group,
            private_ip="10.0.0.13",
            login_user="Administrator",
            login_password="secret",
            verified=True,
            verify_status="verified",
            os="windows",
        )
        self.unverified = ManagedHost.objects.create(
            name="unverified",
            group=self.group,
            private_ip="10.0.0.14",
            login_user="root",
            login_password="secret",
            verified=False,
            verify_status="unverified",
            os="ubuntu",
        )
        self.no_credential = ManagedHost.objects.create(
            name="no-credential",
            group=self.group,
            private_ip="10.0.0.15",
            login_user="root",
            verified=True,
            verify_status="verified",
            os="debian",
        )

    def grant(self, *codenames):
        ensure_feature_permissions()
        self.user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        self.user = get_user_model().objects.get(id=self.user.id)
        self.client.force_login(self.user)

    def test_targets_return_only_verified_linux_hosts_with_ssh_credentials(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        response = self.client.get("/api/bulk-execution/targets/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload], [self.linux.id, self.key_host.id])
        self.assertEqual(payload[0]["name"], "linux-ok")
        self.assertEqual(payload[0]["groupName"], "prod")
        self.assertEqual(payload[0]["privateIp"], "10.0.0.11")
        self.assertEqual(payload[0]["port"], 2222)
        self.assertEqual(payload[0]["loginUser"], "root")

    def test_target_tree_requires_execute_permission(self):
        self.grant("access_bulkExecution")

        response = self.client.get("/api/bulk-execution/target-tree/")

        self.assertEqual(response.status_code, 403)

    def test_target_tree_returns_only_executable_targets_with_group_counts(self):
        parent = HostGroup.objects.create(name="parent", sort_order=1)
        child = HostGroup.objects.create(name="child", parent=parent, sort_order=1)
        empty = HostGroup.objects.create(name="empty", sort_order=2)
        child_host = ManagedHost.objects.create(
            name="child-linux",
            group=child,
            private_ip="10.0.1.11",
            login_user="root",
            login_password="secret",
            verified=True,
            verify_status="verified",
            os="ubuntu",
        )
        ManagedHost.objects.create(
            name="child-windows",
            group=child,
            private_ip="10.0.1.12",
            login_user="Administrator",
            login_password="secret",
            verified=True,
            verify_status="verified",
            os="windows",
        )
        ManagedHost.objects.create(
            name="empty-unverified",
            group=empty,
            private_ip="10.0.1.13",
            login_user="root",
            login_password="secret",
            verified=False,
            verify_status="unverified",
            os="ubuntu",
        )
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        response = self.client.get("/api/bulk-execution/target-tree/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["targets"]], [self.linux.id, self.key_host.id, child_host.id])
        self.assertNotIn(self.windows.id, [item["id"] for item in payload["targets"]])
        roots = {group["label"]: group for group in payload["groups"]}
        self.assertEqual(roots["prod"]["count"], 2)
        self.assertEqual(roots["parent"]["count"], 1)
        self.assertEqual(roots["parent"]["children"][0]["label"], "child")
        self.assertEqual(roots["parent"]["children"][0]["count"], 1)
        self.assertNotIn("empty", roots)

    def test_create_task_requires_execute_permission_and_snapshots_only_executable_targets(self):
        self.grant("access_bulkExecution")

        denied = self.client.post(
            "/api/bulk-execution/tasks/",
            data={"targetIds": [self.linux.id], "command": "uptime"},
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)

        self.grant("access_bulkExecution", "action_bulkExecution_execute")
        with patch("bulk_execution.views.start_bulk_execution_task") as start_task:
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={"targetIds": [self.linux.id, self.windows.id, self.no_credential.id], "command": "  uptime  ", "name": "check uptime"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)
        task = BulkExecutionTask.objects.get()
        self.assertEqual(task.name, "check uptime")
        self.assertEqual(task.command, "uptime")
        self.assertEqual(task.execution_type, BulkExecutionTask.EXECUTION_SHELL)
        self.assertEqual(task.created_by, self.user)
        self.assertEqual(task.target_count, 1)
        self.assertEqual(task.results.count(), 1)
        result = task.results.get()
        self.assertEqual(result.host, self.linux)
        self.assertEqual(result.host_name, "linux-ok")
        self.assertEqual(result.host_ip, "10.0.0.11")
        self.assertEqual(result.login_user, "root")
        start_task.assert_called_once_with(task.id)

    @override_settings(BULK_EXECUTION_MAX_TARGETS=500)
    def test_create_task_accepts_more_than_fifty_targets_when_configured(self):
        extra_hosts = [
            ManagedHost(
                name=f"linux-bulk-{index:03d}",
                group=self.group,
                private_ip=f"10.8.0.{index}",
                login_user="root",
                login_password="secret",
                verified=True,
                verify_status="verified",
                os="ubuntu",
            )
            for index in range(1, 116)
        ]
        ManagedHost.objects.bulk_create(extra_hosts)
        target_ids = [self.linux.id, self.key_host.id] + list(ManagedHost.objects.filter(name__startswith="linux-bulk-").values_list("id", flat=True))

        self.assertEqual(len(target_ids), 117)
        self.grant("access_bulkExecution", "action_bulkExecution_execute")
        with patch("bulk_execution.views.start_bulk_execution_task") as start_task:
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={"targetIds": target_ids, "command": "hostname", "name": "bulk 117 hosts"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["targetCount"], 117)
        task = BulkExecutionTask.objects.get(name="bulk 117 hosts")
        self.assertEqual(task.results.count(), 117)
        start_task.assert_called_once_with(task.id)

    def test_create_task_uses_terminal_settings_max_targets(self):
        extra_host = ManagedHost.objects.create(
            name="linux-extra",
            group=self.group,
            private_ip="10.0.0.16",
            login_user="root",
            login_password="secret",
            verified=True,
            verify_status="verified",
            os="ubuntu",
        )
        SystemSetting.objects.create(key="terminal_settings", value={"bulkExecutionMaxTargets": 2})
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        with patch("bulk_execution.views.start_bulk_execution_task") as start_task:
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={"targetIds": [self.linux.id, self.key_host.id, extra_host.id], "command": "hostname", "name": "too many"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "每次最多选择 2 台主机")
        self.assertFalse(BulkExecutionTask.objects.filter(name="too many").exists())
        start_task.assert_not_called()

    def test_create_task_requires_task_name(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        with patch("bulk_execution.views.start_bulk_execution_task") as start_task:
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={"targetIds": [self.linux.id], "command": "uptime", "name": "  "},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(BulkExecutionTask.objects.exists())
        start_task.assert_not_called()

    def test_create_task_rejects_unsupported_execution_type(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        with patch("bulk_execution.views.start_bulk_execution_task") as start_task:
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={"targetIds": [self.linux.id], "command": "uptime", "executionType": "unsupported", "name": "unsupported task"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(BulkExecutionTask.objects.exists())
        start_task.assert_not_called()

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-test-"))
    def test_create_file_upload_task_accepts_multipart_file_and_selected_targets(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")
        upload = SimpleUploadedFile("deploy.txt", b"hello from ops\n", content_type="text/plain")

        with patch("bulk_execution.views.start_bulk_execution_task") as start_task:
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={
                    "targetIds": json.dumps([self.linux.id, self.windows.id]),
                    "remoteDirectory": "/tmp/",
                    "name": "deploy file",
                    "file": upload,
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["executionType"], "file_upload")
        self.assertEqual(payload["remoteDirectory"], "/tmp")
        self.assertEqual(payload["uploadFilename"], "deploy.txt")
        self.assertEqual(payload["uploadSize"], 15)
        task = BulkExecutionTask.objects.get(name="deploy file")
        self.assertEqual(task.execution_type, BulkExecutionTask.EXECUTION_FILE_UPLOAD)
        self.assertEqual(task.command, "Upload deploy.txt to /tmp/deploy.txt")
        self.assertEqual(task.remote_directory, "/tmp")
        self.assertEqual(task.upload_filename, "deploy.txt")
        self.assertEqual(task.upload_size, 15)
        self.assertTrue(task.upload_file)
        self.assertEqual(task.target_count, 1)
        self.assertEqual(task.results.get().host, self.linux)
        start_task.assert_called_once_with(task.id)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-name-test-"))
    def test_create_file_upload_task_requires_task_name(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")
        upload = SimpleUploadedFile("deploy.txt", b"hello from ops\n", content_type="text/plain")

        with patch("bulk_execution.views.start_bulk_execution_task") as start_task:
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={
                    "targetIds": json.dumps([self.linux.id]),
                    "remoteDirectory": "/tmp/",
                    "file": upload,
                    "name": " ",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(BulkExecutionTask.objects.exists())
        start_task.assert_not_called()

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-multi-test-"))
    def test_create_file_upload_task_accepts_multiple_files_and_exposes_transfer_details(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute", "action_bulkExecution_refresh")
        deploy = SimpleUploadedFile("deploy.txt", b"deploy\n", content_type="text/plain")
        config = SimpleUploadedFile("config.yml", b"name: api\n", content_type="text/yaml")

        with patch("bulk_execution.views.start_bulk_execution_task") as start_task:
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={
                    "executionType": "file_upload",
                    "targetIds": json.dumps([self.linux.id, self.windows.id]),
                    "remoteDirectory": "/opt/app/",
                    "name": "bundle upload",
                    "overwrite": "true",
                    "files": [deploy, config],
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["executionType"], "file_upload")
        self.assertEqual(payload["remoteDirectory"], "/opt/app")
        self.assertEqual(payload["uploadFilename"], "2 files")
        self.assertEqual(payload["uploadSize"], 17)
        task = BulkExecutionTask.objects.get()
        self.assertEqual(task.upload_files.count(), 2)
        self.assertEqual(task.transfer_items.count(), 2)
        self.assertEqual([item.filename for item in task.upload_files.order_by("id")], ["deploy.txt", "config.yml"])
        self.assertEqual([item.remote_path for item in task.upload_files.order_by("id")], ["/opt/app/deploy.txt", "/opt/app/config.yml"])
        start_task.assert_called_once_with(task.id)

        detail = self.client.get(f"/api/bulk-execution/tasks/{task.id}/")
        self.assertEqual(detail.status_code, 200)
        detail_payload = detail.json()
        self.assertEqual([item["filename"] for item in detail_payload["uploadFiles"]], ["deploy.txt", "config.yml"])
        self.assertEqual([item["remotePath"] for item in detail_payload["uploadFiles"]], ["/opt/app/deploy.txt", "/opt/app/config.yml"])
        self.assertEqual([item["remotePath"] for item in detail_payload["results"][0]["transfers"]], ["/opt/app/deploy.txt", "/opt/app/config.yml"])

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-relative-test-"))
    def test_create_file_upload_task_preserves_relative_paths(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")
        config = SimpleUploadedFile("app.yml", b"name: api\n", content_type="text/yaml")
        script = SimpleUploadedFile("start.sh", b"#!/bin/sh\n", content_type="text/plain")

        with patch("bulk_execution.views.start_bulk_execution_task"):
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={
                    "executionType": "file_upload",
                    "targetIds": json.dumps([self.linux.id]),
                    "remoteDirectory": "/tmp/",
                    "name": "release upload",
                    "files": [config, script],
                    "relativePaths": ["release/config/app.yml", "release/bin/start.sh"],
                },
            )

        self.assertEqual(response.status_code, 201)
        task = BulkExecutionTask.objects.get(name="release upload")
        upload_files = list(task.upload_files.order_by("id"))
        self.assertEqual([item.filename for item in upload_files], ["release/config/app.yml", "release/bin/start.sh"])
        self.assertEqual(
            [item.remote_path for item in upload_files],
            ["/tmp/release/config/app.yml", "/tmp/release/bin/start.sh"],
        )

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-storage-name-test-"))
    def test_create_file_upload_task_uses_bounded_flat_storage_name_for_nested_paths(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")
        upload = SimpleUploadedFile("application-settings.yml", b"name: api\n", content_type="text/yaml")
        relative_path = "release/config/environments/production/us-east/application-settings.yml"

        with patch("bulk_execution.views.start_bulk_execution_task"):
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={
                    "executionType": "file_upload",
                    "targetIds": json.dumps([self.linux.id]),
                    "remoteDirectory": "/tmp/",
                    "name": "long nested upload",
                    "files": [upload],
                    "relativePaths": [relative_path],
                },
            )

        self.assertEqual(response.status_code, 201)
        task = BulkExecutionTask.objects.get(name="long nested upload")
        upload_file = task.upload_files.get()
        storage_prefix = "bulk_execution_uploads/"
        self.assertEqual(upload_file.filename, relative_path)
        self.assertEqual(upload_file.remote_path, f"/tmp/{relative_path}")
        self.assertTrue(upload_file.file.name.startswith(storage_prefix))
        self.assertNotIn("/", upload_file.file.name.removeprefix(storage_prefix))
        self.assertLessEqual(len(upload_file.file.name), BulkExecutionUploadFile._meta.get_field("file").max_length)
        self.assertEqual(task.upload_file.name, upload_file.file.name)
        self.assertLessEqual(len(task.upload_file.name), BulkExecutionTask._meta.get_field("upload_file").max_length)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-folder-size-test-"))
    def test_create_file_upload_task_accepts_folder_with_more_than_default_django_file_limit(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")
        file_count = 122
        uploads = [SimpleUploadedFile(f"folder/file-{index}.txt", b"payload", content_type="text/plain") for index in range(file_count)]
        relative_paths = [f"folder/file-{index}.txt" for index in range(file_count)]

        with patch("bulk_execution.views.start_bulk_execution_task"):
            response = self.client.post(
                "/api/bulk-execution/tasks/",
                data={
                    "executionType": "file_upload",
                    "targetIds": json.dumps([self.linux.id]),
                    "remoteDirectory": "/tmp/",
                    "name": "folder upload",
                    "files": uploads,
                    "relativePaths": relative_paths,
                },
            )

        self.assertEqual(response.status_code, 201)
        task = BulkExecutionTask.objects.get(name="folder upload")
        self.assertEqual(task.upload_files.count(), file_count)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-relative-unsafe-test-"))
    def test_create_file_upload_task_rejects_unsafe_relative_paths(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        for relative_path in ["/etc/passwd", "../secret", "release/../../secret", "C:/secret", "C:secret"]:
            upload = SimpleUploadedFile("payload.txt", b"payload", content_type="text/plain")
            with patch("bulk_execution.views.start_bulk_execution_task") as start_task:
                response = self.client.post(
                    "/api/bulk-execution/tasks/",
                    data={
                        "executionType": "file_upload",
                        "targetIds": json.dumps([self.linux.id]),
                        "remoteDirectory": "/tmp/",
                        "name": "unsafe upload",
                        "files": [upload],
                        "relativePaths": [relative_path],
                    },
                )

            self.assertEqual(response.status_code, 400, relative_path)
            self.assertFalse(BulkExecutionTask.objects.filter(name="unsafe upload").exists())
            start_task.assert_not_called()

    def test_upload_check_reports_connected_targets_unreachable_targets_and_duplicate_files(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        def fake_inspect(host, remote_directory, filenames):
            if host.id == self.key_host.id:
                return {"connected": False, "presentFiles": [], "error": "SSH connection failed"}
            self.assertEqual(remote_directory, "/opt/app")
            self.assertEqual(filenames, ["deploy.txt", "config.yml"])
            return {"connected": True, "presentFiles": ["deploy.txt"], "error": ""}

        with patch("bulk_execution.services.inspect_bulk_upload_target", side_effect=fake_inspect, create=True):
            response = self.client.post(
                "/api/bulk-execution/uploads/check/",
                data={
                    "targetIds": [self.linux.id, self.key_host.id, self.windows.id],
                    "remoteDirectory": "/opt/app/",
                    "filenames": ["deploy.txt", "config.yml"],
                    "totalSize": 16,
                },
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([target["id"] for target in payload["connectedTargets"]], [self.linux.id])
        self.assertEqual([target["id"] for target in payload["unreachableTargets"]], [self.key_host.id])
        self.assertEqual(payload["unreachableTargets"][0]["error"], "SSH connection failed")
        self.assertEqual(payload["usableTargetIds"], [self.linux.id])
        self.assertEqual(
            payload["duplicateFiles"],
            [
                {
                    "targetId": self.linux.id,
                    "hostName": "linux-ok",
                    "hostIp": "10.0.0.11",
                    "filenames": ["deploy.txt"],
                }
            ],
        )

    def test_upload_check_preserves_nested_relative_paths_for_duplicates(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        def fake_inspect(host, remote_directory, filenames):
            self.assertEqual(remote_directory, "/opt/app")
            self.assertEqual(filenames, ["release/config/app.yml", "release/bin/start.sh"])
            return {"connected": True, "presentFiles": ["release/config/app.yml"], "error": ""}

        with patch("bulk_execution.services.inspect_bulk_upload_target", side_effect=fake_inspect, create=True):
            response = self.client.post(
                "/api/bulk-execution/uploads/check/",
                data={
                    "targetIds": [self.linux.id],
                    "remoteDirectory": "/opt/app/",
                    "filenames": ["release/config/app.yml", "release/bin/start.sh"],
                    "totalSize": 16,
                },
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["duplicateFiles"][0]["filenames"], ["release/config/app.yml"])

    def test_create_file_upload_task_requires_uploaded_file(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        response = self.client.post(
            "/api/bulk-execution/tasks/",
            data={"targetIds": json.dumps([self.linux.id]), "remoteDirectory": "/tmp/", "executionType": "file_upload"},
        )

        self.assertEqual(response.status_code, 400)

    def test_create_task_rejects_unknown_execution_type(self):
        self.grant("access_bulkExecution", "action_bulkExecution_execute")

        response = self.client.post(
            "/api/bulk-execution/tasks/",
            data={"targetIds": [self.linux.id], "command": "uptime", "executionType": "python", "name": "unknown execution"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_task_history_detail_cancel_and_delete_endpoints(self):
        self.grant(
            "access_bulkExecution",
            "action_bulkExecution_execute",
            "action_bulkExecution_refresh",
            "action_bulkExecution_cancel",
            "action_bulkExecution_delete",
        )
        with patch("bulk_execution.views.start_bulk_execution_task"):
            create = self.client.post(
                "/api/bulk-execution/tasks/",
                data={"targetIds": [self.linux.id], "command": "hostname", "name": "history detail"},
                content_type="application/json",
            )
        task_id = create.json()["id"]

        listing = self.client.get("/api/bulk-execution/tasks/?keyword=hostname&page=1&pageSize=10")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 1)

        detail = self.client.get(f"/api/bulk-execution/tasks/{task_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["results"][0]["status"], "pending")

        canceled = self.client.post(f"/api/bulk-execution/tasks/{task_id}/cancel/")
        self.assertEqual(canceled.status_code, 200)
        self.assertTrue(canceled.json()["cancelRequested"])
        self.assertEqual(canceled.json()["status"], "canceled")

        deleted = self.client.delete(f"/api/bulk-execution/tasks/{task_id}/")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(BulkExecutionTask.objects.filter(id=task_id).exists())


@override_settings(BULK_EXECUTION_FORKS=10, BULK_EXECUTION_TIMEOUT_SECONDS=300)
class BulkExecutionRunnerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="runner")
        self.group = HostGroup.objects.create(name="runner", sort_order=10)
        self.host = ManagedHost.objects.create(
            name="api-01",
            group=self.group,
            private_ip="10.1.0.10",
            port=22,
            login_user="root",
            login_password="secret",
            verified=True,
            verify_status="verified",
            os="ubuntu",
        )

    def test_runner_events_update_result_output_and_task_counts(self):
        task = create_bulk_execution_task(self.user, {"targetIds": [self.host.id], "command": "hostname", "name": "hostnames"})

        def fake_run(host, command, timeout):
            self.assertEqual(host.id, self.host.id)
            self.assertEqual(command, "hostname")
            self.assertEqual(timeout, 300)
            return "api-01\n", "", 0

        with patch("bulk_execution.services.run_plain_ssh_command", side_effect=fake_run) as shell_runner:
            run_bulk_execution_task(task.id)

        shell_runner.assert_called_once()
        task.refresh_from_db()
        result = task.results.get()
        self.assertEqual(task.status, BulkExecutionTask.STATUS_COMPLETED)
        self.assertEqual(task.completed_count, 1)
        self.assertEqual(task.success_count, 1)
        self.assertEqual(task.failed_count, 0)
        self.assertEqual(result.status, BulkExecutionResult.STATUS_SUCCESS)
        self.assertEqual(result.stdout, "api-01\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.exit_code, 0)
        self.assertIsNotNone(result.started_at)
        self.assertIsNotNone(result.finished_at)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-runner-test-"))
    def test_file_upload_task_streams_through_shared_transfer_service(self):
        upload = SimpleUploadedFile("payload.txt", b"payload", content_type="text/plain")
        from .services import create_bulk_file_upload_task

        task = create_bulk_file_upload_task(
            self.user,
            {"targetIds": [self.host.id], "remoteDirectory": "/tmp/", "overwrite": True, "name": "upload payload"},
            upload,
        )

        def fake_upload(host, directory, filename, source, relative_path=""):
            self.assertEqual(host.id, self.host.id)
            self.assertEqual(directory, "/tmp")
            self.assertEqual(filename, "payload.txt")
            self.assertEqual(source.read(), b"payload")
            return {"size": 7, "protocol": "SFTP protocol"}

        with patch("bulk_execution.services.upload_remote_file_stream", side_effect=fake_upload) as uploader:
            run_bulk_execution_task(task.id)

        uploader.assert_called_once()
        task.refresh_from_db()
        result = task.results.get()
        transfer = result.transfers.get()
        self.assertEqual(task.status, BulkExecutionTask.STATUS_COMPLETED)
        self.assertEqual(result.status, BulkExecutionResult.STATUS_SUCCESS)
        self.assertEqual(transfer.status, BulkExecutionTransferItem.STATUS_SUCCESS)
        self.assertIn("SFTP protocol", result.stdout)
        self.assertFalse(task.upload_file.storage.exists(task.upload_file.name))

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-runner-multi-test-"))
    def test_multi_file_upload_preserves_nested_remote_paths(self):
        deploy = SimpleUploadedFile("deploy.txt", b"deploy\n", content_type="text/plain")
        config = SimpleUploadedFile("app.yml", b"name: api\n", content_type="text/yaml")
        from .services import create_bulk_file_upload_task

        task = create_bulk_file_upload_task(
            self.user,
            {
                "targetIds": [self.host.id],
                "remoteDirectory": "/srv/app",
                "overwrite": True,
                "name": "bundle upload",
                "relativePaths": ["deploy.txt", "release/config/app.yml"],
            },
            [deploy, config],
        )
        calls = []

        def fake_upload(host, directory, filename, source, relative_path=""):
            calls.append((directory, filename, source.read()))
            return {"size": len(calls[-1][2]), "protocol": "SFTP protocol"}

        with patch("bulk_execution.services.upload_remote_file_stream", side_effect=fake_upload):
            run_bulk_execution_task(task.id)

        task.refresh_from_db()
        result = task.results.get()
        self.assertEqual(
            [(directory, filename) for directory, filename, _ in calls],
            [("/srv/app", "deploy.txt"), ("/srv/app/release/config", "app.yml")],
        )
        self.assertEqual(task.status, BulkExecutionTask.STATUS_COMPLETED)
        self.assertEqual(result.status, BulkExecutionResult.STATUS_SUCCESS)
        self.assertEqual([item.status for item in result.transfers.order_by("id")], ["success", "success"])

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-existing-test-"))
    def test_file_upload_without_overwrite_rejects_existing_remote_file(self):
        upload = SimpleUploadedFile("payload.txt", b"payload", content_type="text/plain")
        from .services import create_bulk_file_upload_task

        task = create_bulk_file_upload_task(
            self.user,
            {"targetIds": [self.host.id], "remoteDirectory": "/tmp/", "name": "upload payload"},
            upload,
        )

        with patch("bulk_execution.services.remote_path_exists", return_value=True), patch(
            "bulk_execution.services.upload_remote_file_stream"
        ) as uploader:
            run_bulk_execution_task(task.id)

        uploader.assert_not_called()
        task.refresh_from_db()
        result = task.results.get()
        transfer = result.transfers.get()
        self.assertEqual(task.status, BulkExecutionTask.STATUS_FAILED)
        self.assertEqual(result.status, BulkExecutionResult.STATUS_FAILED)
        self.assertEqual(transfer.status, BulkExecutionTransferItem.STATUS_FAILED)
        self.assertIn("already exists", transfer.error)

    def test_runner_failure_event_marks_task_failed(self):
        task = create_bulk_execution_task(self.user, {"targetIds": [self.host.id], "command": "false", "name": "nonzero failure"})

        with patch("bulk_execution.services.run_plain_ssh_command", return_value=("", "boom", 1)):
            run_bulk_execution_task(task.id)

        task.refresh_from_db()
        result = task.results.get()
        self.assertEqual(task.status, BulkExecutionTask.STATUS_FAILED)
        self.assertEqual(task.failed_count, 1)
        self.assertEqual(result.status, BulkExecutionResult.STATUS_FAILED)
        self.assertEqual(result.stderr, "boom")
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.error, "boom")

    def test_plain_shell_empty_output_is_success_even_with_nonzero_exit_code(self):
        task = create_bulk_execution_task(self.user, {"targetIds": [self.host.id], "command": "grep missing /proc/mounts", "name": "empty grep"})

        with patch("bulk_execution.services.run_plain_ssh_command", return_value=("", "", 1)):
            run_bulk_execution_task(task.id)

        task.refresh_from_db()
        result = task.results.get()
        self.assertEqual(task.status, BulkExecutionTask.STATUS_COMPLETED)
        self.assertEqual(task.success_count, 1)
        self.assertEqual(result.status, BulkExecutionResult.STATUS_SUCCESS)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.error, "")

    @override_settings(BULK_EXECUTION_FORKS=1)
    def test_shell_task_runs_each_host_with_plain_ssh(self):
        host2 = ManagedHost.objects.create(
            name="api-02",
            group=self.group,
            private_ip="10.1.0.11",
            port=22,
            login_user="root",
            login_password="secret",
            verified=True,
            verify_status="verified",
            os="ubuntu",
        )
        task = create_bulk_execution_task(self.user, {"targetIds": [self.host.id, host2.id], "command": "ls", "name": "plain shell"})
        calls = []

        def fake_run(host, command, timeout):
            calls.append((host.name, command, timeout))
            return (f"{host.name}\n", "", 0)

        with patch("bulk_execution.services.run_plain_ssh_command", side_effect=fake_run):
            run_bulk_execution_task(task.id)

        task.refresh_from_db()
        self.assertEqual(sorted(calls), [("api-01", "ls", 300), ("api-02", "ls", 300)])
        self.assertEqual(task.status, BulkExecutionTask.STATUS_COMPLETED)
        self.assertEqual(task.success_count, 2)
        self.assertEqual(task.failed_count, 0)
        clean = task.results.get(inventory_name="host_1")
        second = task.results.get(inventory_name="host_2")
        self.assertEqual(clean.status, BulkExecutionResult.STATUS_SUCCESS)
        self.assertEqual(clean.stdout, "api-01\n")
        self.assertEqual(second.status, BulkExecutionResult.STATUS_SUCCESS)
        self.assertEqual(second.stdout, "api-02\n")
        self.assertEqual(second.error, "")

    def test_shell_command_failure_is_not_retried(self):
        task = create_bulk_execution_task(self.user, {"targetIds": [self.host.id], "command": "false", "name": "genuine failure"})

        with patch("bulk_execution.services.run_plain_ssh_command", return_value=("", "boom", 1)) as shell_runner:
            run_bulk_execution_task(task.id)

        shell_runner.assert_called_once()
        task.refresh_from_db()
        self.assertEqual(task.status, BulkExecutionTask.STATUS_FAILED)
        self.assertEqual(task.results.get().status, BulkExecutionResult.STATUS_FAILED)

    def test_cancel_requested_callback_marks_unfinished_results_skipped(self):
        task = create_bulk_execution_task(self.user, {"targetIds": [self.host.id], "command": "sleep 60", "name": "cancel sleep"})
        task.cancel_requested = True
        task.status = BulkExecutionTask.STATUS_RUNNING
        task.started_at = timezone.now()
        task.save(update_fields=["cancel_requested", "status", "started_at"])

        with patch("bulk_execution.services.run_plain_ssh_command") as shell_runner:
            run_bulk_execution_task(task.id)

        shell_runner.assert_not_called()
        task.refresh_from_db()
        result = task.results.get()
        self.assertEqual(task.status, BulkExecutionTask.STATUS_CANCELED)
        self.assertEqual(task.skipped_count, 1)
        self.assertEqual(result.status, BulkExecutionResult.STATUS_SKIPPED)
        self.assertIn("canceled", result.error.lower())

    def test_task_with_no_available_host_fails_instead_of_staying_running(self):
        task = create_bulk_execution_task(self.user, {"targetIds": [self.host.id], "command": "hostname", "name": "missing host"})
        self.host.delete()

        with patch("bulk_execution.services.run_plain_ssh_command") as shell_runner:
            run_bulk_execution_task(task.id)

        shell_runner.assert_not_called()
        task.refresh_from_db()
        result = task.results.get()
        self.assertEqual(task.status, BulkExecutionTask.STATUS_FAILED)
        self.assertEqual(task.error, "No available target host")
        self.assertEqual(task.skipped_count, 1)
        self.assertEqual(result.status, BulkExecutionResult.STATUS_SKIPPED)
