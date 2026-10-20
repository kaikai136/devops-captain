from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

from system_management.services import ensure_feature_permissions
from . import adapters, services
from .catalog import duplicate_asset, exported_asset, import_manifest_payload
from .credentials import resolve_credentials
from .connection_config import ConnectionPolicyError
from .models import ApplicationKey, DatabaseAsset


class ApplicationKeyTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("keys-admin", "", "test-password")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = "/api/application-keys/"
        self.key = ApplicationKey.objects.create(name="shared", username="dbuser", password_encrypted=services.encrypt_password(" original password "))

    def payload(self, kind="mysql", **changes):
        return {"name": f"db-{kind}", "dbType": kind, "host": "db.test", "port": 3306, "username": "ignored", "password": "ignored", "databaseName": "test", "options": {"authMethod": "applicationKey"}, "applicationKeyId": self.key.id, **changes}

    def create_asset(self, kind="mysql"):
        response = self.client.post("/api/database-management/assets/", self.payload(kind), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return DatabaseAsset.objects.get(pk=response.data["id"])

    def limited_user(self, *codes):
        ensure_feature_permissions()
        user = get_user_model().objects.create_user(f"limited-{get_user_model().objects.count()}")
        user.user_permissions.set(Permission.objects.filter(codename__in=codes))
        self.client.force_authenticate(user)
        return user

    def test_password_is_encrypted_write_only_preserves_whitespace_and_blank_edit(self):
        response = self.client.post(self.url, {"name": "new", "username": "", "password": " secret ", "remark": "redis"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["hasPassword"])
        self.assertEqual(response.data["connectionCount"], 0)
        self.assertNotIn("password", response.data)
        self.assertNotIn("password_encrypted", response.data)
        key = ApplicationKey.objects.get(pk=response.data["id"])
        self.assertNotIn(" secret ", key.password_encrypted)
        self.assertEqual(services.decrypt_password(key.password_encrypted), " secret ")
        response = self.client.put(f"{self.url}{key.id}/", {"password": "", "remark": "edited"}, format="json")
        self.assertEqual(response.status_code, 200)
        key.refresh_from_db()
        self.assertEqual(services.decrypt_password(key.password_encrypted), " secret ")
        for payload in ({"name": "new", "password": "x"}, {"name": "", "password": "x"}, {"name": "missing"}):
            self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)

    def test_selector_has_separate_use_permission_and_minimal_response(self):
        self.limited_user("access_applicationKeys", "action_applicationKeys_use")
        response = self.client.get(self.url, {"select": "1"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data[0]), {"id", "name", "username"})
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"name": "denied", "password": "x"}, format="json").status_code, 403)
        self.assertEqual(self.client.put(f"{self.url}{self.key.id}/", {"password": "x"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"{self.url}{self.key.id}/").status_code, 403)
        self.limited_user("access_applicationKeys", "action_applicationKeys_view")
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.url, {"select": "1"}).status_code, 403)

    def test_management_actions_can_be_granted_independently(self):
        self.limited_user("access_applicationKeys", "action_applicationKeys_create")
        response = self.client.post(self.url, {"name": "created", "password": "secret"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.limited_user("access_applicationKeys", "action_applicationKeys_edit")
        response = self.client.put(f"{self.url}{self.key.id}/", {"remark": "updated"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.delete(f"{self.url}{self.key.id}/").status_code, 403)
        self.limited_user("access_applicationKeys", "action_applicationKeys_delete")
        self.assertEqual(self.client.delete(f"{self.url}{self.key.id}/").status_code, 200)

    def test_invalid_options_are_validation_errors(self):
        for options in (["applicationKey"], "applicationKey", {"authMethod": "unknown"}):
            response = self.client.post("/api/database-management/assets/", self.payload(options=options), format="json")
            self.assertEqual(response.status_code, 400, response.data)

    def test_reference_only_delete_protection_unlink_and_manual_compatibility(self):
        asset = self.create_asset()
        self.assertEqual(asset.username, "")
        self.assertEqual(asset.password_encrypted, "")
        self.assertEqual(resolve_credentials(asset), ("dbuser", " original password "))
        response = self.client.get(self.url)
        self.assertEqual(response.data[0]["connectionCount"], 1)
        self.assertEqual(self.client.delete(f"{self.url}{self.key.id}/").status_code, 400)
        response = self.client.put(f"/api/database-management/assets/{asset.id}/", {"options": {"authMethod": "password"}, "username": "manual", "password": " manual "}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        asset.refresh_from_db()
        self.assertIsNone(asset.application_key_id)
        self.assertEqual(resolve_credentials(asset), ("manual", " manual "))
        self.assertEqual(self.client.delete(f"{self.url}{self.key.id}/").status_code, 200)

    def test_invalid_reference_empty_username_and_sqlite_are_rejected(self):
        for key_id in (None, 999999):
            response = self.client.post("/api/database-management/assets/", self.payload(applicationKeyId=key_id), format="json")
            self.assertEqual(response.status_code, 400)
        self.key.username = ""; self.key.save()
        self.assertEqual(self.client.post("/api/database-management/assets/", self.payload(), format="json").status_code, 400)
        redis = self.create_asset("redis")
        self.assertEqual(resolve_credentials(redis)[0], "")
        self.assertEqual(self.client.post("/api/database-management/assets/", self.payload("sqlite"), format="json").status_code, 400)

    def test_binding_requires_use_but_existing_connection_operations_do_not(self):
        asset = self.create_asset()
        codes = ("access_databaseManagement", "action_databaseManagement_view", "action_databaseManagement_create", "action_databaseManagement_edit", "action_databaseManagement_test_connection")
        self.limited_user(*codes)
        self.assertEqual(self.client.post("/api/database-management/assets/", self.payload(), format="json").status_code, 400)
        other = ApplicationKey.objects.create(name="other", username="other", password_encrypted=services.encrypt_password("new"))
        self.assertEqual(self.client.put(f"/api/database-management/assets/{asset.id}/", {"applicationKeyId": other.id}, format="json").status_code, 400)
        response = self.client.put(f"/api/database-management/assets/{asset.id}/", {"remark": "still bound", "username": "override", "password": "override"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        asset.refresh_from_db()
        self.assertEqual(resolve_credentials(asset), ("dbuser", " original password "))
        with patch.object(adapters, "test") as test:
            self.assertEqual(self.client.post(f"/api/database-management/assets/{asset.id}/test/").status_code, 200)
            test.assert_called_once()
        with patch.object(adapters, "connection") as connect:
            response = self.client.post("/api/database-management/connection-test/", self.payload(), format="json")
            self.assertEqual(response.status_code, 400)
            connect.assert_not_called()

    def test_all_drivers_and_legacy_entry_resolve_latest_key_on_each_connection(self):
        for kind in ("mysql", "mariadb", "postgresql", "kingbase", "sqlserver", "redis", "clickhouse", "oracle", "dameng"):
            with self.subTest(kind=kind):
                asset = self.create_asset(kind)
                # Cache the relation deliberately; resolver must bypass this object.
                _ = asset.application_key
                for password in ("before", " after "):
                    ApplicationKey.objects.filter(pk=self.key.pk).update(password_encrypted=services.encrypt_password(password))
                    module = MagicMock()
                    with patch.object(adapters, "module_for", return_value=module):
                        connection = services.connect(asset)
                        connection.close()
                    driver = module.Redis if kind == "redis" else module.get_client if kind == "clickhouse" else module.connect
                    self.assertEqual(driver.call_args.kwargs["password"], password)
                    self.assertEqual(driver.call_args.kwargs["username" if kind == "redis" else "user"], "dbuser")

    def test_unsaved_test_uses_key_and_does_not_persist_or_override_materials(self):
        conn = MagicMock()
        conn.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value = [("tele",)]
        with patch.object(adapters, "connection", return_value=conn) as connect:
            response = self.client.post("/api/database-management/connection-test/", self.payload(), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        ephemeral = connect.call_args.args[0]
        self.assertIsNone(ephemeral.pk)
        self.assertEqual(resolve_credentials(ephemeral), ("dbuser", " original password "))
        self.assertEqual(DatabaseAsset.objects.count(), 0)

    def test_copy_retains_reference_and_export_import_requires_reselection(self):
        asset = self.create_asset()
        copied = duplicate_asset(asset, None)
        self.assertEqual(copied.application_key_id, self.key.id)
        manifest_asset = exported_asset(asset, [])
        self.assertNotIn("applicationKeyId", manifest_asset)
        self.assertNotIn("password", manifest_asset)
        self.assertEqual(manifest_asset["username"], "")
        result = import_manifest_payload(self.admin, {"version": 1, "directories": [], "assets": [manifest_asset]})
        self.assertIn("应用密钥", result["warning"])
        imported = DatabaseAsset.objects.exclude(pk__in=[asset.pk, copied.pk]).get()
        self.assertIsNone(imported.application_key_id)
        self.assertEqual(imported.options["authMethod"], "applicationKey")
        with self.assertRaisesMessage(ValueError, "应用密钥"):
            resolve_credentials(imported)

    def test_bound_sql_username_cannot_be_cleared_and_driver_errors_hide_password(self):
        asset = self.create_asset()
        response = self.client.put(f"{self.url}{self.key.pk}/", {"username": ""}, format="json")
        self.assertEqual(response.status_code, 400)
        module = MagicMock()
        module.connect.side_effect = RuntimeError("driver echoed  original password  in error")
        with patch.object(adapters, "module_for", return_value=module), self.assertRaises(ValueError) as error:
            adapters.connect(asset)
        self.assertNotIn("original password", str(error.exception))

    def test_redaction_precedes_whitespace_normalization_and_truncation(self):
        asset = self.create_asset()
        password = " secret\n with  spaces "
        ApplicationKey.objects.filter(pk=self.key.id).update(password_encrypted=services.encrypt_password(password))
        for reason in (RuntimeError(password + " rejected"), ValueError(password + " rejected")):
            module = MagicMock()
            module.connect.side_effect = reason
            with patch.object(adapters, "module_for", return_value=module), self.assertRaises(ValueError) as error:
                adapters.connect(asset)
            self.assertNotIn("secret", str(error.exception))
            self.assertIn("已隐藏", str(error.exception))

    def test_expired_connections_keep_policy_exception_for_transfer_cancellation(self):
        asset = self.create_asset()
        asset.options["expiresAt"] = "2000-01-01T00:00:00Z"
        asset.save(update_fields=["options"])
        with patch.object(adapters, "module_for", return_value=MagicMock()), self.assertRaises(ConnectionPolicyError):
            adapters.connect(asset)
