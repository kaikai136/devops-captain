import datetime
import socket
import ssl
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from . import adapters, services, transfers, mysql_connection
from .catalog import duplicate_asset, exported_asset, import_manifest_payload
from .connection_config import (
    ConnectionPolicyError, encode_secrets, enforce_policy, enforce_sql,
    merge_secrets, secrets_for, ssl_context, validate_materials, validate_options,
)
from .models import DatabaseAsset, DatabaseTransferTask
from .serializers import DatabaseAssetSerializer
from .services import decrypt_password, encrypt_password


def asset(**changes):
    return DatabaseAsset(name="test", host="db.example.test", port=3306, username="test", **changes)


class ConnectionValidationTests(SimpleTestCase):
    def test_legacy_and_allowed_parameters(self):
        self.assertEqual(validate_options({}, "mysql"), {})
        self.assertEqual(validate_options({"ssl": True}, "postgresql"), {"ssl": True})
        validate_options({"connectTimeout": 120, "charset": "gb18030", "parameters": {"readTimeout": 600, "writeTimeout": 1, "autocommit": False, "sqlMode": "STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION", "timeZone": "Asia/Shanghai"}, "expiresAt": "2030-01-01T12:00:00+08:00"}, "mysql")
        for options in ({"connectTimeout": 0}, {"connectTimeout": True}, {"parameters": {"host": "other"}}, {"parameters": {"readTimeout": 601}}, {"parameters": {"autocommit": 1}}, {"parameters": {"sqlMode": "BAD_MODE"}}, {"parameters": {"timeZone": "bad zone"}}, {"expiresAt": "2030-01-01T12:00:00"}, {"readOnly": "yes"}, {"tls": {"mode": "bad"}}, {"ssh": {"enabled": True}}):
            with self.subTest(options=options), self.assertRaises(ValueError): validate_options(options, "mysql")
        self.assertEqual(validate_options({"color": "#1890ff", "environment": "production", "readOnly": True, "connectTimeout": 10}, "postgresql"), {"color": "#1890ff", "environment": "production", "readOnly": True, "connectTimeout": 10})
        self.assertEqual(validate_options({"color": "#1890ff", "authMethod": "password"}, "redis"), {"color": "#1890ff", "authMethod": "password"})

    def test_secrets_are_allowlisted_and_size_limited(self):
        for updates in ({"password": "secret"}, {"sshPrivateKey": {"name": "../id", "content": "x"}}, {"sslCa": {"name": "ca.pem", "content": "x" * (256 * 1024 + 1)}}):
            with self.assertRaises(ValueError): merge_secrets(None, updates)
        original = asset(connection_secrets_encrypted=encode_secrets({"sshPassword": "old", "sslCa": {"name": "old.pem", "content": "old"}}))
        self.assertEqual(merge_secrets(original, {})["sshPassword"], "old")
        self.assertNotIn("sslCa", merge_secrets(original, {"sslCa": None}))
        with self.assertRaises(ValueError): validate_materials({"ssl": True}, {"sslCa": {"name": "bad.pem", "content": "bad"}})

    def test_readonly_sql_rejects_all_write_and_session_escape_forms(self):
        connection = asset(options={"readOnly": True})
        for sql in ("SELECT 1", "SELECT 'UPDATE, INTO' AS message", "SHOW CREATE TABLE test", "SHOW DATABASES", "DESCRIBE test", "EXPLAIN SELECT * FROM test"):
            enforce_sql(connection, sql)
        for sql in ("UPDATE t SET a=1", "SELECT 1; SELECT 2", "CALL p()", "SET TRANSACTION READ WRITE", "SELECT 1 INTO OUTFILE '/tmp/out'", "SELECT @a:=1", "SELECT LOAD_FILE('/tmp/out')", "SELECT GET_LOCK('x',1)", "SELECT * FROM t FOR UPDATE", "/*!50000 SELECT 1 */", "EXPLAIN UPDATE t SET a=1"):
            with self.subTest(sql=sql), self.assertRaises(ValueError): enforce_sql(connection, sql)
        with self.assertRaises(ConnectionPolicyError): enforce_policy(connection, write=True)
        expired = asset(options={"expiresAt": (timezone.now() - datetime.timedelta(seconds=1)).isoformat()})
        with self.assertRaises(ConnectionPolicyError): enforce_policy(expired)

    def test_real_tls_material_parsing_pairing_and_hostname_modes(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "db.example.test")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(key, hashes.SHA256())
        cert_text = cert.public_bytes(serialization.Encoding.PEM).decode()
        key_text = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        material = {"sslCa": {"name": "ca.pem", "content": cert_text}, "sslCert": {"name": "client.pem", "content": cert_text}, "sslKey": {"name": "key.pem", "content": key_text}}
        for mode, verify, hostname in (("require", ssl.CERT_NONE, False), ("verify_ca", ssl.CERT_REQUIRED, False), ("verify_identity", ssl.CERT_REQUIRED, True)):
            options = {"ssl": True, "tls": {"mode": mode}}
            validate_materials(options, material)
            context = ssl_context(options, material)
            self.assertEqual(context.verify_mode, verify)
            self.assertEqual(context.check_hostname, hostname)
        with self.assertRaises(ValueError): validate_materials({"ssl": True}, {"sslCert": material["sslCert"]})
        with self.assertRaises(ValueError): validate_materials({"ssl": True, "tls": {"mode": "verify_ca"}}, {})
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        mismatched = {**material, "sslKey": {"name": "wrong.pem", "content": other.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()}}
        with self.assertRaises(ValueError): validate_materials({"ssl": True}, mismatched)

    def test_connection_options_reach_both_mysql_entrypoints(self):
        connection = asset(options={"connectTimeout": 11, "charset": "gbk", "parameters": {"readTimeout": 31, "writeTimeout": 32, "autocommit": True, "sqlMode": "ANSI", "timeZone": "+08:00"}, "readOnly": True})
        module = MagicMock()
        for connector in (adapters.connect, services.connect):
            module.reset_mock()
            with patch.object(adapters, "module_for", return_value=module):
                result = connector(connection, "tele")
                kwargs = module.connect.call_args.kwargs
                self.assertEqual((kwargs["connect_timeout"], kwargs["read_timeout"], kwargs["write_timeout"], kwargs["charset"], kwargs["database"], kwargs["autocommit"]), (11, 31, 32, "gbk", "tele", True))
                cursor = module.connect.return_value.cursor.return_value.__enter__.return_value
                self.assertTrue(any(call.args[0] == "SET SESSION TRANSACTION READ ONLY" for call in cursor.execute.call_args_list))
                result.close()
                module.connect.return_value.close.assert_called_once()

    def test_ssh_tls_uses_original_target_and_cleans_failure_and_success(self):
        connection = asset(options={"ssh": {"enabled": True}, "ssl": True})
        for fails in (False, True):
            module = MagicMock()
            module.connect.return_value.connect.side_effect = TimeoutError("timeout") if fails else None
            left, right = socket.socketpair()
            def tunnel(_asset, _secrets, _timeout, resources):
                resources.callback(left.close)
                resources.callback(right.close)
                return left
            with patch.object(mysql_connection, "ssh_socket", side_effect=tunnel), patch.object(mysql_connection, "ssl_context", return_value=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)):
                if fails:
                    with self.assertRaises(TimeoutError): mysql_connection.connect(connection, "tele", module)
                else:
                    with mysql_connection.connect(connection, "tele", module): pass
                self.assertEqual(module.connect.call_args.kwargs["host"], "db.example.test")
                module.connect.return_value.connect.assert_called_once_with(sock=left)
                self.assertEqual(left.fileno(), -1)
                module.connect.return_value.close.assert_called_once()

    def test_tls_rejects_plaintext_before_authentication(self):
        connection = asset(options={"ssl": True})
        module = MagicMock()
        raw = module.connect.return_value
        raw.server_capabilities = 0
        original_auth = raw._request_authentication
        def handshake(): raw._request_authentication()
        raw.connect.side_effect = handshake
        with self.assertRaisesRegex(ValueError, "TLS"):
            mysql_connection.connect(connection, "tele", module)
        original_auth.assert_not_called()
        raw.close.assert_called_once()

    def test_readonly_exports_use_trusted_readonly_snapshot(self):
        connection = asset(options={"readOnly": True})
        raw = MagicMock()
        managed = mysql_connection.ManagedConnection(raw, ExitStack(), connection)
        mysql_connection.prepare_export_snapshot(managed)
        sql = [call.args[0] for call in raw.cursor.return_value.__enter__.return_value.execute.call_args_list]
        self.assertIn("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY", sql)
        with self.assertRaises(ValueError): managed.cursor().execute("SET SESSION TRANSACTION READ WRITE")


class MysqlConnectionApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("connection-admin", "", "password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.asset = asset(password_encrypted=encrypt_password("db-secret"))
        self.asset.save()
        self.url = f"/api/database-management/assets/{self.asset.pk}/"

    def test_encrypted_material_status_replacement_removal_and_password(self):
        response = self.client.put(self.url, {"connectionSecrets": {"sshPassword": "jump-secret"}}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["connectionSecretStatus"], {"sshPassword": {"configured": True}})
        self.assertNotIn("jump-secret", str(response.data))
        self.assertNotIn("connectionSecrets", response.data)
        self.asset.refresh_from_db()
        self.assertNotIn("jump-secret", self.asset.connection_secrets_encrypted)
        self.assertEqual(secrets_for(self.asset)["sshPassword"], "jump-secret")
        self.client.put(self.url, {"password": ""}, format="json")
        self.asset.refresh_from_db()
        self.assertEqual(decrypt_password(self.asset.password_encrypted), "db-secret")
        response = self.client.put(self.url, {"options": {"authMethod": "none"}, "connectionSecrets": {"sshPassword": None}}, format="json")
        self.assertEqual(response.data["connectionSecretStatus"], {})
        self.asset.refresh_from_db()
        self.assertEqual(decrypt_password(self.asset.password_encrypted), "")

    def test_unsaved_test_merges_old_password_without_saving(self):
        conn = MagicMock()
        conn.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = [{"Database": "tele"}]
        with patch.object(adapters, "connection", return_value=conn) as connect:
            response = self.client.post("/api/database-management/connection-test/", {"assetId": self.asset.id, "name": "draft", "host": "other.test", "password": ""}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["databases"], ["tele"])
        tested = connect.call_args.args[0]
        self.assertIsNone(tested.pk)
        self.assertEqual(tested.host, "other.test")
        self.assertEqual(decrypt_password(tested.password_encrypted), "db-secret")
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.host, "db.example.test")
        self.assertEqual(DatabaseAsset.objects.count(), 1)

    def test_test_connection_requires_both_permissions(self):
        user = get_user_model().objects.create_user("limited")
        self.client.force_authenticate(user)
        with patch.object(adapters, "connection") as connect:
            self.assertEqual(self.client.post("/api/database-management/connection-test/", {"assetId": self.asset.id}, format="json").status_code, 403)
            connect.assert_not_called()

    def test_readonly_and_expiry_block_every_write_entry_before_driver(self):
        operations = [(f"{self.url}rows/", {"action": "insert"}), (f"{self.url}schema/", {"action": "add_column"}), (f"{self.url}objects/action/", {"action": "drop"}), (f"{self.url}accounts/", {"name": "new"}), (f"{self.url}database/", {"action": "create", "name": "newdb"}), (f"{self.url}sql/", {"sql": "UPDATE t SET a=1"}), ("/api/database-management/transfers/uploads/", {"assetId": self.asset.id, "scope": "database", "format": "sql"})]
        for options in ({"readOnly": True}, {"expiresAt": (timezone.now() - datetime.timedelta(seconds=1)).isoformat()}):
            self.asset.options = options
            self.asset.save()
            with patch.object(adapters, "connect") as connect, patch.object(adapters, "execute") as execute:
                for url, data in operations:
                    with self.subTest(options=options, url=url): self.assertEqual(self.client.post(url, data, format="json").status_code, 400)
                connect.assert_not_called()
                execute.assert_not_called()
        self.assertEqual(self.client.put(self.url, {"options": {}}, format="json").status_code, 200)

    def test_copy_and_manifest_do_not_leak_materials(self):
        self.asset.connection_secrets_encrypted = encode_secrets({"sshPassword": "sensitive"})
        self.asset.save()
        copy = duplicate_asset(self.asset, None)
        self.assertEqual(secrets_for(copy), secrets_for(self.asset))
        exported = exported_asset(self.asset, [])
        self.assertNotIn("sensitive", str(exported))
        result = import_manifest_payload(self.user, {"version": 1, "directories": [], "assets": [exported]})
        self.assertIn("warning", result)

    def test_background_batch_rechecks_expiry_and_readonly(self):
        task = transfers.create_task(owner=self.user, asset=self.asset, direction="import", scope="database", format="sql", database="tele")
        for options in ({"readOnly": True}, {"expiresAt": (timezone.now() - datetime.timedelta(seconds=1)).isoformat()}):
            DatabaseAsset.objects.filter(pk=self.asset.pk).update(options=options)
            with self.assertRaises(ConnectionPolicyError): transfers.progress(task, rows=20)
            self.assertEqual(task.processed_rows, 0)

    def test_expiry_blocks_confirmation_retry_but_allows_completed_download(self):
        self.asset.options = {"expiresAt": (timezone.now() - datetime.timedelta(seconds=1)).isoformat()}
        self.asset.save()
        task = transfers.create_task(owner=self.user, asset=self.asset, direction="import", scope="database", format="sql", database="tele", status="awaiting_confirmation")
        base = f"/api/database-management/transfers/{task.id}/"
        response = self.client.post(base + "confirm/", {"confirmed": True}, format="json")
        self.assertEqual(response.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.status, "awaiting_confirmation")
        task.status = "failed"; task.save()
        self.assertEqual(self.client.post(base + "retry/", {"confirmed": True}, format="json").status_code, 400)
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "done.sql"
            output.write_text("SELECT 1;", encoding="utf-8")
            task.direction = "export"; task.status = "succeeded"; task.output_path = str(output); task.save()
            response = self.client.get(base + "download/")
            self.assertEqual(response.status_code, 200)
            response.close()
