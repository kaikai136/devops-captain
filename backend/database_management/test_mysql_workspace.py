from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from . import database_admin
from .models import DatabaseAsset


class MysqlDatabaseEncodingTests(SimpleTestCase):
    def setUp(self):
        self.asset = SimpleNamespace(db_type="mysql")
        self.data = {"name": "tele", "charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"}

    def test_only_server_supported_charset_collation_pair_can_execute(self):
        conn = MagicMock()
        with patch.object(database_admin.adapters, "connection", return_value=conn), patch.object(database_admin.adapters, "run", side_effect=[([{"collation": self.data["collation"]}], 1), ([], 0)]) as run:
            database_admin.alter_mysql_database(self.asset, self.data)
        self.assertEqual(run.call_args_list[0].args[2], ("utf8mb4", "utf8mb4_unicode_ci"))
        self.assertEqual(run.call_args_list[1].args[1], "ALTER DATABASE `tele` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.__enter__.return_value.commit.assert_called_once()

    def test_rejects_mismatched_pair_identifiers_and_other_engines(self):
        with patch.object(database_admin.adapters, "connection"), patch.object(database_admin.adapters, "run", return_value=([], 0)) as run:
            with self.assertRaises(ValueError): database_admin.alter_mysql_database(self.asset, self.data)
            self.assertEqual(run.call_count, 1)
        for key, value in [("name", "bad; DROP DATABASE tele"), ("charset", "utf8;--"), ("collation", "x y")]:
            with self.subTest(key=key), patch.object(database_admin.adapters, "connection") as connection:
                with self.assertRaises(ValueError): database_admin.alter_mysql_database(self.asset, {**self.data, key: value})
                connection.assert_not_called()
        with self.assertRaises(ValueError): database_admin.alter_mysql_database(SimpleNamespace(db_type="postgresql"), self.data)


class MysqlWorkspaceApiTests(TestCase):
    def setUp(self):
        self.asset = DatabaseAsset.objects.create(name="workspace", db_type="mysql", host="localhost", username="test", database="tele")
        self.user = get_user_model().objects.create_user(username="workspace-user")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = f"/api/database-management/assets/{self.asset.pk}"

    def test_metadata_edit_and_delete_require_permissions_before_connecting(self):
        with patch.object(database_admin.adapters, "connection") as connection:
            for path in ["/mysql-metadata/?name=tele", "/mysql-metadata/?name=tele&diagram=1"]:
                self.assertEqual(self.client.get(self.base + path).status_code, 403)
            for action in ["edit", "delete"]:
                self.assertEqual(self.client.post(self.base + "/database/", {"action": action, "name": "tele"}, format="json").status_code, 403)
            connection.assert_not_called()

    def test_metadata_and_diagram_use_bound_database_names(self):
        self.user.is_superuser = True; self.user.save()
        with patch.object(database_admin.adapters, "connection"), patch.object(database_admin.adapters, "run", side_effect=[([{"charset": "utf8mb4", "collation": "utf8mb4_bin"}], 1), ([{"charset": "utf8mb4", "collation": "utf8mb4_bin"}], 1)]) as run:
            response = self.client.get(self.base + "/mysql-metadata/?name=tele")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["charset"], "utf8mb4")
            self.assertEqual(run.call_args_list[0].args[2], ("tele",))
        with patch.object(database_admin.adapters, "connection"), patch.object(database_admin.adapters, "run", side_effect=[([{"table_name": "orders", "name": "id"}], 1), ([{"source": "orders", "target": "users"}], 1)]) as run:
            response = self.client.get(self.base + "/mysql-metadata/?name=tele&diagram=1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["relations"][0]["source"], "orders")
            self.assertEqual(run.call_args_list[1].args[2], ("tele", "tele"))

    def test_existing_delete_endpoint_keeps_database_target(self):
        self.user.is_superuser = True; self.user.save()
        with patch.object(database_admin, "run_ddl") as ddl:
            response = self.client.post(self.base + "/database/", {"action": "delete", "name": "tele"}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(ddl.call_args.args[1], "DROP DATABASE `tele`")
