import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from host_management.models import HostGroup, ManagedHost
from system_management.models import OperationLog
from web_terminal.models import TerminalCommandAudit
from web_terminal.consumers.ssh import TerminalConsumer
from web_terminal.services import TerminalConnectionError
from web_terminal.services.docker_resources import get_remote_docker_resources, parse_docker_resources
from web_terminal.services.containers import (
    MAX_LOG_BYTES, container_action_command, container_terminal_command,
    get_remote_containers, parse_docker_containers, read_bounded_logs,
)
from web_terminal.services.monitoring import get_remote_resource_monitor, parse_remote_resource_monitor_output
from . import test_monitoring_parsers


CONTAINER_ID = "a" * 64
INSPECT = json.dumps({"Id": CONTAINER_ID, "State": {"Running": True}})


class ExtendedMonitorTests(SimpleTestCase):
    def test_details_extend_without_changing_legacy_core_metrics(self):
        output = test_monitoring_parsers.MonitoringParserCharacterizationTests.monitor_output.replace(
            "uptime=120.5", "uptime=120.5\ncpuModel=Example CPU\nhostTime=2026-10-17T12:00:00+08:00"
        ).replace("Cached: 100 kB", "SwapTotal: 100 kB\nSwapFree: 25 kB\nCached: 100 kB")
        output += "SECTION:details\ndns=1.1.1.1 8.8.8.8\ntcpCongestion=bbr\nipv4=1\nipv6=0\n"
        payload = parse_remote_resource_monitor_output(output)
        self.assertEqual(payload["system"]["cpuModel"], "Example CPU")
        self.assertEqual(payload["system"]["cpuCores"], 1)
        self.assertEqual(payload["swap"]["usagePercent"], 75)
        self.assertTrue(payload["management"]["bbrEnabled"])
        self.assertTrue(payload["management"]["ipv6Enabled"])
        self.assertEqual(payload["management"]["dnsServers"], ["1.1.1.1", "8.8.8.8"])
        self.assertEqual(payload["network"][0]["rxBytes"], 4072)
        with patch("web_terminal.services.monitoring.run_one_shot_ssh_command", return_value=output):
            result = get_remote_resource_monitor(SimpleNamespace(port=22022))
        self.assertEqual(result["management"]["sshPort"], 22022)

    def test_missing_optional_fields_do_not_break_monitor(self):
        output = test_monitoring_parsers.MonitoringParserCharacterizationTests.monitor_output + "SECTION:details\n"
        payload = parse_remote_resource_monitor_output(output)
        self.assertFalse(payload["swap"]["available"])
        self.assertIsNone(payload["management"]["bbrEnabled"])
        self.assertEqual(payload["system"]["cpuModel"], "-")


class DockerResourceServiceTests(SimpleTestCase):
    def test_image_references_preserve_repository_tag_pairs(self):
        records = [
            {"ID": "sha256:abc", "Repository": "registry:5000/first", "Tag": "v1", "Size": "20MB"},
            {"ID": "sha256:abc", "Repository": "second", "Tag": "v2", "Size": "20MB"},
            {"ID": "sha256:abc", "Repository": "second", "Tag": "v2", "Size": "20MB"},
        ]
        rows = parse_docker_resources("images", "\n".join(json.dumps(record) for record in records))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["references"], ["registry:5000/first:v1", "second:v2"])
        self.assertEqual(rows[0]["size"], "20MB")
        self.assertEqual(rows[0]["diskUsage"], "20MB")
        self.assertEqual(rows[0]["contentSize"], "")
        self.assertEqual(rows[0]["extra"], "")

    def test_explicit_image_sizes_and_extra_are_not_inferred(self):
        record = {"ID": "sha256:abc", "Size": "10MB", "DiskUsage": "30MB", "ContentSize": "8MB", "Extra": "U"}
        row = parse_docker_resources("images", json.dumps(record))[0]
        self.assertEqual(row["diskUsage"], "30MB")
        self.assertEqual(row["contentSize"], "8MB")
        self.assertEqual(row["extra"], "U")
        missing = parse_docker_resources("images", '{"ID":"missing"}')[0]
        self.assertEqual(missing["references"], [])
        for field in ("diskUsage", "contentSize", "extra"):
            self.assertEqual(missing[field], "")

    @patch("web_terminal.services.docker_resources.run_one_shot_ssh_command", return_value='{"ID":"sha256:abc","Repository":"repo","Tag":"one","CreatedAt":"today","Size":"10MB"}\n{"ID":"sha256:abc","Repository":"repo","Tag":"two","CreatedAt":"today","Size":"10MB"}')
    def test_images_merge_tags_by_unique_id_and_run_only_requested_command(self, command):
        rows = get_remote_docker_resources(Mock(), "images")
        self.assertEqual(rows["total"], 1)
        self.assertEqual(rows["images"][0]["tags"], ["one", "two"])
        self.assertIn("docker image ls", command.call_args.args[1])

    def test_empty_and_other_resource_parsers(self):
        self.assertEqual(parse_docker_resources("networks", ""), [])
        self.assertEqual(parse_docker_resources("networks", '{"ID":"id","Name":"bridge","Driver":"bridge","Scope":"local"}')[0]["name"], "bridge")
        self.assertEqual(parse_docker_resources("volumes", '{"Name":"data","Driver":"local"}')[0]["name"], "data")

    @patch("web_terminal.services.docker_resources.run_one_shot_ssh_command", side_effect=TerminalConnectionError("permission denied"))
    def test_unavailable_docker_does_not_return_a_successful_empty_list(self, command):
        result = get_remote_docker_resources(Mock(), "volumes")
        self.assertFalse(result["available"])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["volumes"], [])

class ContainerServiceTests(SimpleTestCase):
    def test_container_and_stats_parser(self):
        listed = json.dumps({"ID": CONTAINER_ID, "Names": "web", "Image": "nginx", "State": "running", "Status": "Up 2 days", "RunningFor": "2 days", "Ports": "80/tcp"})
        stats = json.dumps({"ID": CONTAINER_ID, "CPUPerc": "2.5%", "MemUsage": "12MiB / 1GiB", "MemPerc": "1.2%"})
        items = parse_docker_containers(f"bad json\n{listed}", stats)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["cpuPercent"], 2.5)
        self.assertEqual(items[0]["memoryUsageBytes"], 12 * 1024**2)
        self.assertEqual(items[0]["memoryLimitBytes"], 1024**3)
        self.assertEqual(parse_docker_containers("{}\n[]"), [])

    @patch("web_terminal.services.containers.run_one_shot_ssh_command")
    def test_unavailable_docker_and_missing_stats(self, command):
        command.side_effect = TerminalConnectionError("permission denied while trying to connect to Docker")
        self.assertFalse(get_remote_containers(Mock())["available"])
        command.side_effect = [json.dumps({"ID": CONTAINER_ID}), TerminalConnectionError("stats failed")]
        self.assertIsNone(get_remote_containers(Mock())["containers"][0]["cpuPercent"])

    @patch("web_terminal.services.containers.run_one_shot_ssh_command", return_value=INSPECT)
    def test_control_whitelist_and_canonical_id(self, command):
        self.assertEqual(container_action_command(Mock(), "web", "restart"), f"docker restart {CONTAINER_ID}")
        self.assertEqual(container_terminal_command(Mock(), "web"), f"docker exec -it {CONTAINER_ID} /bin/sh\r")
        command.reset_mock()
        for action, identifier in [("rm", "web"), ("start", "web; id"), ("stop", "--help")]:
            with self.assertRaises(ValueError):
                container_action_command(Mock(), identifier, action)
        command.assert_not_called()

    @patch("web_terminal.services.containers.run_one_shot_ssh_command", return_value=json.dumps({"Id": CONTAINER_ID, "State": {"Running": False}}))
    def test_stopped_container_cannot_open_terminal(self, command):
        with self.assertRaisesMessage(ValueError, "容器未运行"):
            container_terminal_command(Mock(), "web")

    @patch("web_terminal.services.containers.open_ssh_client")
    @patch("web_terminal.services.containers.validate_container", return_value=CONTAINER_ID)
    def test_logs_are_bounded_and_connections_cleaned(self, validate, connect):
        channel = Mock()
        channel.recv_ready.return_value = True
        channel.recv.side_effect = lambda count: b"x" * count
        connect.return_value.exec_command.return_value = (Mock(), SimpleNamespace(channel=channel), Mock())
        result = read_bounded_logs(Mock(), "web", 200)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["logs"]), MAX_LOG_BYTES)
        channel.close.assert_called_once()
        connect.return_value.close.assert_called_once()
        for tail in (0, 1001, True, "200"):
            with self.assertRaises(ValueError):
                read_bounded_logs(Mock(), "web", tail)

    @patch("web_terminal.services.containers.open_ssh_client")
    @patch("web_terminal.services.containers.validate_container", return_value=CONTAINER_ID)
    def test_log_transport_timeout_is_normalized_and_closes_client(self, validate, connect):
        connect.return_value.exec_command.side_effect = TimeoutError("SSH timeout")
        with self.assertRaisesMessage(TerminalConnectionError, "SSH timeout"):
            read_bounded_logs(Mock(), "web", 200)
        connect.return_value.close.assert_called_once()

    @patch("web_terminal.services.containers.time.monotonic", side_effect=[0, 31])
    @patch("web_terminal.services.containers.open_ssh_client")
    @patch("web_terminal.services.containers.validate_container", return_value=CONTAINER_ID)
    def test_log_deadline_is_bounded_and_closes_channel(self, validate, connect, monotonic):
        channel = Mock()
        connect.return_value.exec_command.return_value = (Mock(), SimpleNamespace(channel=channel), Mock())
        with self.assertRaisesMessage(TerminalConnectionError, "读取容器日志超时"):
            read_bounded_logs(Mock(), "web", 200)
        channel.close.assert_called_once()
        connect.return_value.close.assert_called_once()

    @patch("web_terminal.services.containers.open_ssh_client")
    @patch("web_terminal.services.containers.validate_container", return_value=CONTAINER_ID)
    def test_log_command_failure_preserves_error_and_closes_client(self, validate, connect):
        channel = Mock()
        channel.recv_ready.side_effect = [True, False]
        channel.recv.return_value = b"container disappeared"
        channel.exit_status_ready.return_value = True
        channel.recv_exit_status.return_value = 1
        connect.return_value.exec_command.return_value = (Mock(), SimpleNamespace(channel=channel), Mock())
        with self.assertRaisesMessage(TerminalConnectionError, "container disappeared"):
            read_bounded_logs(Mock(), "web", 200)
        connect.return_value.close.assert_called_once()


class HostContainerApiTests(TestCase):
    @patch("web_terminal.api.containers.get_remote_docker_resources")
    def test_resource_queries_are_isolated_and_permission_gated(self, resources):
        for resource in ("images", "networks", "volumes"):
            resources.return_value = {"available": True, resource: [], "total": 0}
            url = f"/api/web-terminal/hosts/{self.host.id}/{resource}/"
            response = self.client.post(url, {}, content_type="application/json")
            self.assertEqual(response.status_code, 200)
            resources.assert_called_with(self.host, resource)
            self.assertEqual(response.json()["total"], 0)
        resources.reset_mock()
        self.host.os = "windows"
        self.host.save(update_fields=["os"])
        for resource in ("images", "networks", "volumes"):
            url = f"/api/web-terminal/hosts/{self.host.id}/{resource}/"
            self.assertEqual(self.client.post(url, {}, content_type="application/json").status_code, 400)
        resources.assert_not_called()
        regular = get_user_model().objects.create_user(username="resource-reader", password="pass")
        self.client.force_login(regular)
        for resource in ("images", "networks", "volumes"):
            url = f"/api/web-terminal/hosts/{self.host.id}/{resource}/"
            self.assertEqual(self.client.post(url, {}, content_type="application/json").status_code, 403)
        resources.assert_not_called()

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="host-admin", password="pass", email="")
        self.host = ManagedHost.objects.create(group=HostGroup.objects.create(name="monitor-hosts"), name="node", private_ip="10.0.0.1")
        self.base = f"/api/web-terminal/hosts/{self.host.id}/containers/"
        self.client.force_login(self.user)

    def post(self, endpoint="", payload=None):
        return self.client.post(self.base + endpoint, payload or {}, content_type="application/json")

    @patch("web_terminal.api.containers.get_remote_containers", return_value={"available": True, "containers": []})
    def test_list_and_permission_rejection(self, containers):
        self.assertEqual(self.post().status_code, 200)
        containers.reset_mock()
        regular = get_user_model().objects.create_user(username="readonly", password="pass")
        self.client.force_login(regular)
        with patch("web_terminal.api.containers.container_action_command") as command, patch("web_terminal.api.containers.read_bounded_logs") as logs:
            for endpoint in ("", "action/", "logs/"):
                self.assertEqual(self.post(endpoint).status_code, 403)
            command.assert_not_called()
            logs.assert_not_called()
        containers.assert_not_called()

    @patch("web_terminal.api.containers.container_action_command", return_value=f"docker restart {CONTAINER_ID}")
    @patch("web_terminal.api.containers.run_one_shot_ssh_command", return_value="done")
    def test_action_success_and_failure_are_audited(self, command, validate):
        self.assertEqual(self.post("action/", {"containerId": "web", "action": "restart"}).status_code, 200)
        command.side_effect = TerminalConnectionError("daemon unavailable")
        self.assertEqual(self.post("action/", {"containerId": "web", "action": "restart"}).status_code, 400)
        self.assertEqual(TerminalCommandAudit.objects.filter(host=self.host).count(), 2)
        self.assertEqual(OperationLog.objects.filter(module="主机容器").count(), 2)
        self.assertIn("daemon unavailable", TerminalCommandAudit.objects.first().output)

    @patch("web_terminal.api.containers.read_bounded_logs", return_value={"logs": "hello", "truncated": False})
    def test_logs_and_windows_unsupported(self, logs):
        response = self.post("logs/", {"containerId": "web"})
        self.assertEqual(response.json()["logs"], "hello")
        self.host.os = "windows"
        self.host.save(update_fields=["os"])
        self.assertEqual(self.post().status_code, 400)
        with patch("web_terminal.api.monitoring.get_remote_resource_monitor") as monitor:
            self.assertEqual(self.client.post(f"/api/web-terminal/hosts/{self.host.id}/monitor/", {}, content_type="application/json").status_code, 400)
            monitor.assert_not_called()


class ContainerTerminalTests(SimpleTestCase):
    @patch("web_terminal.consumers.ssh.threading.Thread")
    @patch("web_terminal.consumers.ssh.open_live_terminal")
    @patch("web_terminal.consumers.ssh.container_terminal_command", return_value=f"docker exec -it {CONTAINER_ID} /bin/sh\r")
    @patch("web_terminal.consumers.ssh.ManagedHost.objects.get", return_value=SimpleNamespace(id=7))
    def test_validated_entry_is_sent_and_recorded(self, host, validate, connect, thread):
        consumer = TerminalConsumer()
        consumer.scope = {"url_route": {"kwargs": {"host_id": 7}}, "query_string": b"container=web"}
        for method in ("accept", "send", "close", "_create_audit_session", "_send_initial_output", "_install_cwd_hook", "_record_input"):
            setattr(consumer, method, Mock())
        consumer._is_authenticated = Mock(return_value=True)
        consumer._has_terminal_permission = Mock(return_value=True)
        consumer.connect()
        validate.assert_called_once_with(host.return_value, "web")
        consumer._record_input.assert_called_once_with(f"docker exec -it {CONTAINER_ID} /bin/sh\r")
        connect.return_value.send_data.assert_called_once_with(f"docker exec -it {CONTAINER_ID} /bin/sh\r")
        consumer.close.assert_not_called()
