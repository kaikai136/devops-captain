from importlib import import_module

from django.db import migrations
from django.test import SimpleTestCase, TestCase

from web_terminal.services import TerminalConnectionError

from .models import HostCredential, HostGroup, ManagedHost
from .probe import verify_host
from .serializers import HostCredentialSerializer


class HostInitialMigrationTests(SimpleTestCase):
    def test_initial_migration_does_not_seed_demo_hosts(self):
        migration_module = import_module("host_management.migrations.0001_initial")

        seed_operations = [operation for operation in migration_module.Migration.operations if isinstance(operation, migrations.RunPython)]

        self.assertEqual(seed_operations, [])


class HostCredentialOptionalUsernameTests(TestCase):
    def test_create_accepts_blank_and_omitted_username_for_both_types(self):
        for kind in (HostCredential.TYPE_HOST, HostCredential.TYPE_APPLICATION):
            for username_data in ({}, {"username": ""}, {"username": "   "}):
                with self.subTest(kind=kind, username_data=username_data):
                    serializer = HostCredentialSerializer(data={
                        "name": f"credential-{HostCredential.objects.count()}",
                        "credentialType": kind,
                        "password": "secret",
                        **username_data,
                    })
                    self.assertTrue(serializer.is_valid(), serializer.errors)
                    saved = serializer.save()
                    saved.refresh_from_db()
                    self.assertEqual(saved.username, "")
                    self.assertEqual(saved.password, "secret")

    def test_edit_can_clear_username_without_changing_password(self):
        credential = HostCredential.objects.create(name="redis", username="redis", password="secret")
        serializer = HostCredentialSerializer(credential, data={"username": ""}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        credential.refresh_from_db()
        self.assertEqual(credential.username, "")
        self.assertEqual(credential.password, "secret")

    def test_import_preserves_password_only_credentials_and_can_clear_username(self):
        from .import_export import import_credentials

        imported = {"credentials": 0}
        import_credentials([{"name": "redis", "username": "", "password": "secret"}], imported)
        credential = HostCredential.objects.get(name="redis")
        self.assertEqual(credential.username, "")
        self.assertEqual(credential.password, "secret")
        credential.username = "redis"
        credential.save()
        import_credentials([{"name": "redis", "username": ""}], imported)
        credential.refresh_from_db()
        self.assertEqual(credential.username, "")
        self.assertEqual(credential.password, "secret")
        import_credentials([{"name": "password-only", "password": "secret"}], imported)
        self.assertEqual(HostCredential.objects.get(name="password-only").username, "")


class HostVerifyTests(TestCase):
    def setUp(self):
        self.group = HostGroup.objects.create(name="verify-tests", sort_order=10)

    def test_verify_host_updates_machine_config_on_success(self):
        host = ManagedHost.objects.create(
            name="success-host",
            group=self.group,
            private_ip="10.10.10.10",
            login_user="root",
            cpu=0,
            memory=0,
            verified=False,
        )

        with self.patch_probe(
            {
                "machine_name": "prod-api-01",
                "cpu": 4,
                "memory": 8,
                "disk": "sda: 447.1G  nvme0n1: 238.5G",
                "os": "ubuntu",
                "system_arch": "x86_64",
                "system_type": "ubuntu",
            }
        ):
            updated, error = verify_host(host)

        self.assertIsNone(error)
        self.assertTrue(updated.verified)
        self.assertEqual(updated.verify_status, "verified")
        self.assertEqual(updated.machine_name, "prod-api-01")
        self.assertEqual(updated.cpu, 4)
        self.assertEqual(updated.memory, 8)
        self.assertEqual(updated.disk, "sda: 447.1G  nvme0n1: 238.5G")
        self.assertEqual(updated.os, "ubuntu")

    def test_verify_host_clears_machine_config_on_failure(self):
        host = ManagedHost.objects.create(
            name="failed-host",
            group=self.group,
            private_ip="10.10.10.11",
            login_user="root",
            cpu=2,
            memory=4,
            disk="sda: 128G",
            machine_name="old-hostname",
            verified=True,
            verify_status="verified",
        )

        with self.patch_probe(TerminalConnectionError("ssh failed")):
            updated, error = verify_host(host)

        self.assertEqual(error, "ssh failed")
        self.assertFalse(updated.verified)
        self.assertEqual(updated.verify_status, "failed")
        self.assertEqual(updated.machine_name, "")
        self.assertEqual(updated.cpu, 0)
        self.assertEqual(updated.memory, 0)
        self.assertEqual(updated.disk, "")

    def test_verify_host_polls_credentials_and_saves_successful_login(self):
        HostCredential.objects.create(name="wrong", username="root", password="wrong")
        HostCredential.objects.create(name="correct", username="ops", password="secret")
        host = ManagedHost.objects.create(
            name="credential-host",
            group=self.group,
            private_ip="10.10.10.14",
            login_user="bad",
            login_password="bad-password",
            verified=False,
        )
        attempted_logins = []

        def fake_connect(_host, candidate, attempts=1, **_kwargs):
            attempted_logins.append((candidate.username, candidate.password))
            if candidate.username == "ops" and candidate.password == "secret":
                return object()
            raise TerminalConnectionError("authentication failed")

        from unittest.mock import patch
        from web_terminal.services import open_ssh_client

        def fake_probe_host_info(current_host):
            client = open_ssh_client(current_host)
            self.assertIsNotNone(client)
            return {
                "machine_name": "api-01",
                "cpu": 4,
                "memory": 8,
                "disk": "sda: 256G",
                "os": "ubuntu",
                "system_arch": "x86_64",
                "system_type": "ubuntu",
            }

        with patch("web_terminal.services.connections.connect_ssh_candidate", side_effect=fake_connect), patch(
            "host_management.probe.probe_host_info", side_effect=fake_probe_host_info
        ):
            updated, error = verify_host(host)

        self.assertIsNone(error)
        self.assertEqual(attempted_logins, [("bad", "bad-password"), ("root", "wrong"), ("ops", "secret")])
        self.assertTrue(updated.verified)
        self.assertEqual(updated.verify_status, "verified")
        self.assertEqual(updated.login_user, "ops")
        self.assertEqual(updated.login_password, "secret")
        updated.refresh_from_db()
        self.assertEqual(updated.login_user, "ops")
        self.assertEqual(updated.login_password, "secret")

    def test_host_credential_candidates_exclude_application_keys(self):
        HostCredential.objects.create(name="host-key", username="ops", password="host-secret")
        HostCredential.objects.create(
            name="application-key",
            username="db-user",
            password="app-secret",
            credential_type=HostCredential.TYPE_APPLICATION,
        )

        from web_terminal.services.connections import host_credential_login_candidates

        candidates = host_credential_login_candidates(set())

        self.assertEqual([(item.username, item.password) for item in candidates], [("ops", "host-secret")])

    def test_host_credential_serializer_validates_and_returns_credential_type(self):
        serializer = HostCredentialSerializer(data={
            "name": "application-key",
            "username": "db-user",
            "credentialType": "application",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        saved = serializer.save()
        self.assertEqual(HostCredentialSerializer(saved).data["credentialType"], "application")

        invalid = HostCredentialSerializer(data={
            "name": "bad-key",
            "username": "user",
            "credentialType": "other",
        })
        self.assertFalse(invalid.is_valid())

    def test_managed_host_verify_reports_when_login_was_auto_saved(self):
        host = ManagedHost.objects.create(
            name="api-host",
            group=self.group,
            private_ip="10.10.10.15",
            login_user="root",
            login_password="old",
            verified=False,
        )
        saved_host = ManagedHost.objects.get(id=host.id)
        saved_host.login_user = "ops"
        saved_host.login_password = "secret"

        from unittest.mock import patch

        with patch("host_management.views.verify_host", return_value=(saved_host, None)):
            response = self.client.post(f"/api/host-management/hosts/{host.id}/verify/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["credentialSaved"])
        self.assertEqual(payload["host"]["loginUser"], "ops")

    def test_verify_windows_host_only_checks_port_connectivity(self):
        host = ManagedHost.objects.create(
            name="win-host",
            group=self.group,
            private_ip="10.10.10.12",
            public_ip="203.0.113.12",
            port=3389,
            login_user="Administrator",
            login_password="secret",
            cpu=8,
            memory=16,
            disk="sda: 512G",
            machine_name="stale-name",
            system_arch="x86_64",
            system_type="windows",
            os="windows",
            verified=False,
        )

        class FakeSocket:
            def close(self):
                pass

        from unittest.mock import patch

        with patch("host_management.probe.probe_host_info") as probe_info, patch(
            "host_management.probe.socket.create_connection", return_value=FakeSocket()
        ) as connect:
            updated, error = verify_host(host)

        self.assertIsNone(error)
        probe_info.assert_not_called()
        connect.assert_called_once_with(("203.0.113.12", 3389), timeout=8)
        self.assertTrue(updated.verified)
        self.assertEqual(updated.verify_status, "verified")
        self.assertEqual(updated.os, "windows")
        self.assertEqual(updated.machine_name, "")
        self.assertEqual(updated.cpu, 0)
        self.assertEqual(updated.memory, 0)
        self.assertEqual(updated.disk, "")
        self.assertEqual(updated.system_arch, "")
        self.assertEqual(updated.system_type, "")

    def test_managed_host_verify_response_includes_disk_size(self):
        host = ManagedHost.objects.create(
            name="api-disk-host",
            group=self.group,
            private_ip="10.10.10.16",
            login_user="root",
            verified=False,
        )

        with self.patch_probe(
            {
                "machine_name": "api-disk-host",
                "cpu": 8,
                "memory": 32,
                "disk": "sda: 447.1G  nvme0n1: 238.5G",
                "os": "ubuntu",
                "system_arch": "x86_64",
                "system_type": "ubuntu",
            }
        ):
            response = self.client.post(f"/api/host-management/hosts/{host.id}/verify/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["host"]["cpu"], 8)
        self.assertEqual(payload["host"]["memory"], 32)
        self.assertEqual(payload["host"]["disk"], "sda: 447.1G  nvme0n1: 238.5G")

    def test_parse_lsblk_disk_details_uses_only_top_level_disks(self):
        from .probe import parse_lsblk_disk_details

        output = "\n".join(
            [
                "sda 480069664358 disk",
                "nvme0n1 256060514304 disk",
                "nvme0n1p1 1073741824 part",
            ]
        )

        self.assertEqual(parse_lsblk_disk_details(output), "sda: 447.1G  nvme0n1: 238.5G")
        self.assertEqual(parse_lsblk_disk_details(""), "")

    def test_verify_windows_host_marks_failed_when_port_unreachable(self):
        host = ManagedHost.objects.create(
            name="win-failed",
            group=self.group,
            private_ip="10.10.10.13",
            port=3389,
            os="windows",
            verified=True,
            verify_status="verified",
        )

        from unittest.mock import patch

        with patch("host_management.probe.socket.create_connection", side_effect=OSError("refused")):
            updated, error = verify_host(host)

        self.assertIn("refused", error)
        self.assertFalse(updated.verified)
        self.assertEqual(updated.verify_status, "failed")
        self.assertEqual(updated.os, "windows")

    def patch_probe(self, result):
        from unittest.mock import patch

        if isinstance(result, Exception):
            return patch("host_management.probe.probe_host_info", side_effect=result)
        return patch("host_management.probe.probe_host_info", return_value=result)


class HostDefaultGroupTests(TestCase):
    def test_create_host_without_groups_creates_default_group(self):
        response = self.client.post(
            "/api/host-management/hosts/",
            data={
                "name": "host-10",
                "privateIp": "172.16.0.99",
                "port": 22,
                "loginUser": "root",
                "os": "ubuntu",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        group = HostGroup.objects.get(name="default", parent__isnull=True)
        self.assertEqual(response.json()["group"], group.id)
        self.assertTrue(ManagedHost.objects.filter(name="host-10", group=group).exists())


class HostImportExportTests(TestCase):
    def test_export_host_management_payload(self):
        group = HostGroup.objects.create(name="prod", sort_order=10)
        HostCredential.objects.create(name="root账号", username="root", password="secret", port=22)
        ManagedHost.objects.create(
            name="api-01",
            group=group,
            private_ip="10.0.0.1",
            public_ip="1.1.1.1",
            login_user="root",
            cpu=4,
            memory=8,
            disk="sda: 256G",
        )

        response = self.client.get("/api/host-management/export/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], 1)
        self.assertTrue(any(item["path"] == "prod" for item in payload["groups"]))
        exported_host = next(item for item in payload["hosts"] if item["privateIp"] == "10.0.0.1")
        self.assertEqual(exported_host["disk"], "sda: 256G")
        self.assertTrue(any(item["name"] == "root账号" for item in payload["credentials"]))

    def test_import_host_management_payload(self):
        response = self.client.post(
            "/api/host-management/import/",
            data={
                "version": 1,
                "groups": [{"name": "prod", "path": "prod/zone-a", "sortOrder": 20}],
                "credentials": [{"name": "root账号", "username": "root", "password": "secret", "port": 22}],
                "hosts": [
                    {
                        "name": "api-01",
                        "groupPath": "prod/zone-a",
                        "privateIp": "10.0.0.2",
                        "publicIp": "1.1.1.2",
                        "port": 22,
                        "loginUser": "root",
                        "cpu": 4,
                        "memory": 8,
                        "disk": "sda: 256G",
                        "os": "centos",
                    }
                ],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported"]["hosts"], 1)
        self.assertTrue(HostGroup.objects.filter(name="zone-a", parent__name="prod").exists())
        self.assertTrue(HostCredential.objects.filter(name="root账号", username="root").exists())
        imported_host = ManagedHost.objects.get(private_ip="10.0.0.2", group__name="zone-a")
        self.assertEqual(imported_host.disk, "sda: 256G")
