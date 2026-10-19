import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase, TestCase

from host_management.models import HostCredential, HostGroup, ManagedHost
from .. import services


class TerminalConnectionCharacterizationTests(SimpleTestCase):
    def make_host(self, **overrides):
        values = {
            "login_user": "root",
            "login_password": "secret",
            "private_key": "",
            "public_ip": "203.0.113.10",
            "private_ip": "10.0.0.8",
            "port": 22022,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def fake_paramiko(self, client_factory):
        return SimpleNamespace(
            SSHClient=client_factory,
            AutoAddPolicy=MagicMock(return_value="auto-add-policy"),
            RSAKey=MagicMock(),
            Ed25519Key=MagicMock(),
            ECDSAKey=MagicMock(),
            DSSKey=MagicMock(),
        )

    def test_open_ssh_client_uses_current_paramiko_timeouts_and_keepalive(self):
        client = MagicMock()
        transport = client.get_transport.return_value
        client_factory = MagicMock(return_value=client)
        paramiko = self.fake_paramiko(client_factory)
        host = self.make_host()

        with patch.dict(sys.modules, {"paramiko": paramiko}):
            result = services.open_ssh_client(host)

        self.assertIs(result, client)
        client.set_missing_host_key_policy.assert_called_once_with("auto-add-policy")
        client.connect.assert_called_once_with(
            hostname="203.0.113.10",
            port=22022,
            username="root",
            password="secret",
            pkey=None,
            timeout=15,
            banner_timeout=30,
            auth_timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )
        transport.set_keepalive.assert_called_once_with(30)

    def test_open_ssh_client_uses_terminal_settings_timeouts_attempts_and_keepalive(self):
        client = MagicMock()
        transport = client.get_transport.return_value
        client_factory = MagicMock(return_value=client)
        paramiko = self.fake_paramiko(client_factory)
        host = self.make_host()
        terminal_settings = {
            "sshConnectTimeoutSeconds": 9,
            "sshBannerTimeoutSeconds": 11,
            "sshAuthTimeoutSeconds": 13,
            "sshConnectAttempts": 1,
            "sshRetryDelayMs": 250,
            "sshKeepaliveSeconds": 7,
        }

        with patch.dict(sys.modules, {"paramiko": paramiko}):
            result = services.open_ssh_client(host, terminal_settings=terminal_settings)

        self.assertIs(result, client)
        client.connect.assert_called_once_with(
            hostname="203.0.113.10",
            port=22022,
            username="root",
            password="secret",
            pkey=None,
            timeout=9,
            banner_timeout=11,
            auth_timeout=13,
            look_for_keys=False,
            allow_agent=False,
        )
        transport.set_keepalive.assert_called_once_with(7)

    def test_open_ssh_client_skips_keepalive_when_terminal_setting_is_zero(self):
        client = MagicMock()
        transport = client.get_transport.return_value
        paramiko = self.fake_paramiko(MagicMock(return_value=client))

        with patch.dict(sys.modules, {"paramiko": paramiko}):
            services.open_ssh_client(self.make_host(), terminal_settings={"sshKeepaliveSeconds": 0})

        transport.set_keepalive.assert_not_called()

    def test_open_ssh_client_retries_retryable_errors_and_translates_last_error(self):
        clients = [MagicMock(), MagicMock(), MagicMock()]
        clients[0].connect.side_effect = TimeoutError("timed out once")
        clients[1].connect.side_effect = ConnectionResetError("connection reset twice")
        clients[2].connect.side_effect = RuntimeError("permission denied")
        paramiko = self.fake_paramiko(MagicMock(side_effect=clients))

        with patch.dict(sys.modules, {"paramiko": paramiko}), patch("time.sleep") as sleep:
            with self.assertRaises(services.TerminalConnectionError) as raised:
                services.open_ssh_client(self.make_host())

        self.assertEqual(str(raised.exception), "SSH \u8fde\u63a5\u5931\u8d25\uff1apermission denied")
        self.assertEqual(sleep.call_args_list, [call(0.8), call(1.6)])
        for client in clients:
            client.close.assert_called_once_with()

    def test_open_live_terminal_uses_compatible_shell_parameters_and_zero_timeout(self):
        client = MagicMock()
        channel = client.invoke_shell.return_value

        with patch("web_terminal.services.open_ssh_client", return_value=client):
            connection = services.open_live_terminal(self.make_host(), cols=132, rows=48)

        self.assertIsInstance(connection, services.LiveTerminalConnection)
        self.assertIs(connection.client, client)
        self.assertIs(connection.channel, channel)
        client.invoke_shell.assert_called_once_with(term="vt100", width=132, height=48)
        channel.settimeout.assert_called_once_with(0.0)

    def test_open_live_terminal_closes_client_and_translates_shell_error(self):
        client = MagicMock()
        client.invoke_shell.side_effect = RuntimeError("channel unavailable")

        with patch("web_terminal.services.open_ssh_client", return_value=client):
            with self.assertRaises(services.TerminalConnectionError) as raised:
                services.open_live_terminal(self.make_host())

        self.assertEqual(str(raised.exception), "SSH \u4f1a\u8bdd\u521b\u5efa\u5931\u8d25\uff1achannel unavailable")
        client.close.assert_called_once_with()

    def test_live_connection_command_uses_thirty_second_read_timeout(self):
        channel = MagicMock(closed=False)
        connection = services.LiveTerminalConnection(MagicMock(), channel)

        with patch.object(connection, "read_available", return_value="result") as read_available:
            result = connection.send_command("whoami")

        self.assertEqual(result, "result")
        channel.sendall.assert_called_once_with("whoami\n")
        read_available.assert_called_once_with(timeout=30.0, idle_timeout=0.35)

    def test_live_connection_command_uses_terminal_settings_read_timeouts(self):
        channel = MagicMock(closed=False)
        connection = services.LiveTerminalConnection(
            MagicMock(),
            channel,
            terminal_settings={"commandReadTimeoutSeconds": 12, "commandReadIdleTimeoutMs": 250},
        )

        with patch.object(connection, "read_available", return_value="result") as read_available:
            result = connection.send_command("whoami")

        self.assertEqual(result, "result")
        read_available.assert_called_once_with(timeout=12.0, idle_timeout=0.25)

    def test_live_connection_normalizes_output_and_translates_closed_send(self):
        channel = MagicMock(closed=False)
        connection = services.LiveTerminalConnection(MagicMock(), channel)

        with patch.object(connection, "read_available_raw", return_value="a\r\nb\rc\n"):
            self.assertEqual(connection.read_available(), "a\nb\nc")

        channel.closed = True
        with self.assertRaises(services.TerminalConnectionError) as raised:
            connection.send_data("pwd")
        self.assertEqual(str(raised.exception), "SSH \u4f1a\u8bdd\u5df2\u5173\u95ed\uff0c\u8bf7\u91cd\u65b0\u8fde\u63a5\u4e3b\u673a\u3002")

    def test_live_connection_sends_terminal_input_completely(self):
        channel = MagicMock(closed=False)
        connection = services.LiveTerminalConnection(MagicMock(), channel)
        data = "printf 'hello'\n" * 1000

        connection.send_data(data)

        channel.sendall.assert_called_once_with(data)
        channel.send.assert_not_called()

    def test_live_connection_preserves_utf8_split_across_recv_chunks(self):
        chunks = [b"\xe4\xbd", b"\xa0\xe5\xa5\xbd"]
        channel = MagicMock(closed=False)
        channel.recv_ready.return_value = True
        channel.recv.side_effect = chunks
        connection = services.LiveTerminalConnection(MagicMock(), channel)

        self.assertEqual(connection.read_raw(), "")
        self.assertEqual(connection.read_raw(), "你好")


    def test_connections_can_be_imported_before_services_package(self):
        environment = os.environ.copy()
        environment.setdefault("DJANGO_SETTINGS_MODULE", "ops_tool.settings")
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import django; "
                    "django.setup(); "
                    "import web_terminal.services.connections; "
                    "print('connections import OK')"
                ),
            ],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )

        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertIn("connections import OK", probe.stdout)

    def test_connection_symbols_report_the_new_implementation_module(self):
        self.assertEqual(
            services.TerminalConnectionError.__module__,
            "web_terminal.services.errors",
        )
        for name in (
            "LiveTerminalConnection",
            "open_live_terminal",
            "open_ssh_client",
            "should_retry_ssh_connect_error",
            "load_private_key",
            "normalize_terminal_output",
        ):
            with self.subTest(name=name):
                self.assertEqual(getattr(services, name).__module__, "web_terminal.services.connections")


class TerminalCredentialPollingTests(TestCase):
    def setUp(self):
        self.group = HostGroup.objects.create(name="credential-polling")

    def fake_paramiko(self, client_factory):
        return SimpleNamespace(
            SSHClient=client_factory,
            AutoAddPolicy=MagicMock(return_value="auto-add-policy"),
            RSAKey=MagicMock(),
            Ed25519Key=MagicMock(),
            ECDSAKey=MagicMock(),
            DSSKey=MagicMock(),
        )

    def test_open_ssh_client_polls_host_credentials_and_saves_successful_login(self):
        HostCredential.objects.create(name="wrong", username="root", password="wrong")
        HostCredential.objects.create(name="correct", username="ops", password="secret")
        host = ManagedHost.objects.create(
            name="api-01",
            group=self.group,
            private_ip="10.0.0.8",
            login_user="bad",
            login_password="bad-password",
        )
        attempts = []
        clients = [MagicMock(), MagicMock(), MagicMock()]

        def connect_side_effect(*, username, password, **_kwargs):
            attempts.append((username, password))
            if username == "ops" and password == "secret":
                return None
            raise RuntimeError("authentication failed")

        for client in clients:
            client.connect.side_effect = connect_side_effect
        paramiko = self.fake_paramiko(MagicMock(side_effect=clients))

        with patch.dict(sys.modules, {"paramiko": paramiko}):
            result = services.open_ssh_client(host)

        self.assertIs(result, clients[-1])
        self.assertEqual(attempts, [("bad", "bad-password"), ("root", "wrong"), ("ops", "secret")])
        host.refresh_from_db()
        self.assertEqual(host.login_user, "ops")
        self.assertEqual(host.login_password, "secret")

    def test_open_ssh_client_keeps_existing_login_when_it_connects(self):
        HostCredential.objects.create(name="other", username="ops", password="secret")
        host = ManagedHost.objects.create(
            name="api-01",
            group=self.group,
            private_ip="10.0.0.8",
            login_user="root",
            login_password="current",
        )
        client = MagicMock()
        paramiko = self.fake_paramiko(MagicMock(return_value=client))

        with patch.dict(sys.modules, {"paramiko": paramiko}):
            result = services.open_ssh_client(host)

        self.assertIs(result, client)
        client.connect.assert_called_once()
        host.refresh_from_db()
        self.assertEqual(host.login_user, "root")
        self.assertEqual(host.login_password, "current")

    def test_open_ssh_client_stops_credential_polling_after_connectivity_timeout(self):
        HostCredential.objects.create(name="other", username="ops", password="secret")
        host = ManagedHost.objects.create(
            name="api-01",
            group=self.group,
            private_ip="10.0.0.8",
            login_user="root",
            login_password="bad-network",
        )
        attempts = []
        clients = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]

        def connect_side_effect(*, username, password, **_kwargs):
            attempts.append((username, password))
            if username == "ops":
                return None
            raise TimeoutError("timed out")

        for client in clients:
            client.connect.side_effect = connect_side_effect
        paramiko = self.fake_paramiko(MagicMock(side_effect=clients))

        with patch.dict(sys.modules, {"paramiko": paramiko}), patch("time.sleep"):
            with self.assertRaises(services.TerminalConnectionError):
                services.open_ssh_client(host)

        self.assertEqual(attempts, [("root", "bad-network"), ("root", "bad-network"), ("root", "bad-network")])
        host.refresh_from_db()
        self.assertEqual(host.login_user, "root")
        self.assertEqual(host.login_password, "bad-network")
