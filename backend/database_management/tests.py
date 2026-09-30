import sqlite3
import json
import tempfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient, APIRequestFactory

from system_management.services import (
    FEATURE_PERMISSION_CODE_BY_KEY, PAGE_ACTION_PERMISSION_CODE_BY_KEY,
    ensure_feature_permissions, inherit_created_action_permissions,
)

from . import adapters, advanced
from .models import DatabaseAsset
from .serializers import DatabaseAssetSerializer
from .services import decrypt_password, encrypt_password, validate_identifier


class DatabaseManagementServiceTests(SimpleTestCase):
    def test_database_password_is_reversible_without_exposing_plaintext(self):
        encrypted = encrypt_password("p@ss word")
        self.assertNotEqual(encrypted, "p@ss word")
        self.assertEqual(decrypt_password(encrypted), "p@ss word")

    def test_identifier_validation_rejects_sql_fragments(self):
        self.assertEqual(validate_identifier("orders_2026"), "orders_2026")
        with self.assertRaises(ValueError):
            validate_identifier("orders` UNION SELECT")

    def test_all_supported_types_have_metadata_and_driver_selection(self):
        metadata = adapters.type_metadata()
        self.assertEqual(len(metadata), 10)
        self.assertEqual({item["key"] for item in metadata}, {item[0] for item in DatabaseAsset.DB_TYPES})
        self.assertEqual(next(item["defaultPort"] for item in metadata if item["key"] == "redis"), 6379)
        for kind in adapters.TYPE_INFO:
            with self.subTest(kind=kind), patch.object(adapters.importlib, "import_module") as importer:
                adapters.module_for(kind)
                importer.assert_called_once_with(adapters.TYPE_INFO[kind][2])

    def test_metadata_aliases_are_case_insensitive(self):
        self.assertEqual(adapters.metadata_rows([{"NAME": "USERS", "TYPE": "TABLE"}]),
                         [{"name": "USERS", "type": "TABLE"}])

    def test_table_list_includes_available_engine_and_update_metadata(self):
        asset = SimpleNamespace(db_type="mysql", database="sample")
        metadata = [{"name": "orders", "type": "BASE TABLE", "rows_count": 12,
                     "engine": "InnoDB", "update_time": "2026-01-01"}]
        with patch.object(adapters, "connection"), patch.object(adapters, "run", return_value=(metadata, 1)) as run:
            result = adapters.object_list(asset, "sample", object_type="table")
        self.assertEqual(result[0]["engine"], "InnoDB")
        self.assertEqual(result[0]["rows_count"], 12)
        self.assertEqual(result[0]["update_time"], "2026-01-01")
        self.assertIn("update_time", run.call_args.args[1])

    def test_table_list_normalizes_all_metadata_fields_and_mysql_aliases(self):
        asset = SimpleNamespace(db_type="mysql", database="sample")
        metadata = [{"name": "orders", "type": "BASE TABLE"}]
        with patch.object(adapters, "connection"), patch.object(adapters, "run", return_value=(metadata, 1)) as run:
            result = adapters.object_list(asset, "sample", object_type="table")
        self.assertEqual(set(result[0]), set(adapters.OBJECT_FIELDS))
        self.assertIsNone(result[0]["data_length"])
        sql = run.call_args.args[1].lower()
        for alias in ("rows_count", "data_length", "index_length", "auto_increment", "charset", "update_time", "create_time", "comment"):
            self.assertIn(alias, sql)

    def test_serializer_never_returns_password(self):
        asset = DatabaseAsset(name="test", db_type="mysql", host="localhost", port=3306,
                              username="user", password_encrypted=encrypt_password("secret"))
        payload = DatabaseAssetSerializer(asset).data
        self.assertNotIn("password", payload)
        self.assertNotIn("secret", str(payload))

    def test_sql_action_rejects_batches_and_classifies_writes(self):
        self.assertEqual(advanced.sql_action("SELECT 1"), "read")
        self.assertEqual(advanced.sql_action("WITH x AS (SELECT 1) SELECT * FROM x"), "read")
        self.assertEqual(advanced.sql_action("UPDATE sample SET name='a'"), "modify_data")
        self.assertEqual(advanced.sql_action("DROP TABLE sample"), "manage_schema")
        self.assertEqual(advanced.sql_action("EXPLAIN ANALYZE UPDATE sample SET name='a'"), "modify_data")
        self.assertEqual(advanced.sql_action("WITH changed AS (DELETE FROM sample RETURNING *) SELECT * FROM changed"), "modify_data")
        self.assertEqual(advanced.sql_action("SELECT * INTO copied FROM sample"), "manage_schema")
        self.assertEqual(advanced.sql_action("PRAGMA foreign_keys=OFF"), "manage_schema")
        with self.assertRaises(ValueError):
            advanced.sql_action("SELECT 1; DROP TABLE sample")


class SQLiteAdapterTests(SimpleTestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "data.sqlite3"
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
            connection.executemany("INSERT INTO sample (name) VALUES (?)", [("alpha",), ("beta",)])
            connection.execute("CREATE TABLE binary_sample (id INTEGER PRIMARY KEY, payload BLOB)")
            connection.execute("INSERT INTO binary_sample (payload) VALUES (?)", (b"\xa4\xff",))
            connection.commit()
        self.settings_override = override_settings(DATABASE_ASSET_SQLITE_ROOT=self.root.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.asset = SimpleNamespace(name="test", db_type="sqlite", options={"file": self.path.name},
                                     password_encrypted="", username="", database="")

    def test_path_restriction_blocks_escape_and_app_database(self):
        for filename in ("../data.sqlite3", str(self.path), "missing.txt"):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                adapters.sqlite_path(filename)
        with patch.object(adapters.settings, "DATABASES", {"default": {"NAME": str(self.path)}}):
            with self.assertRaises(ValueError):
                adapters.sqlite_path(self.path.name)

    def test_tree_columns_filter_sort_and_pagination(self):
        adapters.test(self.asset)
        self.assertEqual(adapters.schema_names(self.asset), ["main"])
        self.assertIn("sample", {item["name"] for item in adapters.object_list(self.asset, "main")})
        columns = adapters.columns(self.asset, "main", "sample")
        self.assertEqual(columns[0]["column_key"], "PRI")
        result = adapters.table_data(self.asset, "main", "sample", page=1, page_size=1,
                                     sort="name", direction="desc", fields=["name"])
        self.assertEqual(result["rows"], [{"name": "beta"}])
        self.assertTrue(result["hasNext"])
        filtered = adapters.table_data(self.asset, "main", "sample", where_field="name", where_value="alpha")
        self.assertEqual(filtered["total"], 1)

    def test_table_data_normalizes_binary_values_for_json(self):
        result = adapters.table_data(self.asset, "main", "binary_sample")
        self.assertEqual(result["rows"], [{"id": 1, "payload": "0xa4ff"}])

    def test_sqlite_cannot_attach_or_export_other_files(self):
        with self.assertRaises(ValueError):
            advanced.validate_sql_for_asset(self.asset, "VACUUM INTO 'outside.db'")
        with adapters.connection(self.asset) as connection:
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("ATTACH DATABASE ':memory:' AS other")

    def test_row_changes_are_atomic_and_reject_non_unique_keys(self):
        request = SimpleNamespace(data={"database": "main"})
        with patch.object(advanced, "record_operation_log"):
            response = advanced.apply_rows(request, self.asset, [
                {"table": "sample", "action": "update", "key": {"id": 1}, "values": {"name": "changed"}},
            ])
            self.assertEqual(response.data["affected"], 1)
            with self.assertRaises(ValueError):
                advanced.apply_rows(request, self.asset, [
                    {"table": "sample", "action": "insert", "values": {"name": "temporary"}},
                    {"table": "sample", "action": "delete", "key": {"name": "temporary"}},
                    {"table": "sample", "action": "update", "key": {"name": "changed"}, "values": {"name": "ignored"}},
                    {"table": "sample", "action": "delete", "key": {"id": 999}},
                ])
        result = adapters.table_data(self.asset, "main", "sample")
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["rows"][0]["name"], "changed")

    def test_csv_export_spans_pages_and_import_preserves_schema(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executemany("INSERT INTO sample (name) VALUES (?)",
                                   [(f"item-{index}",) for index in range(600)])
            connection.commit()
        factory = APIRequestFactory()
        with patch.object(advanced, "checked", return_value=(self.asset, None)), \
             patch.object(advanced, "record_operation_log"), \
             patch.object(advanced, "require_feature_permission", return_value=None):
            response = advanced.asset_export(factory.get("/export/", {
                "format": "csv", "database": "main", "table": "sample",
            }), 1)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.content.decode("utf-8-sig").splitlines()), 603)

            upload = SimpleUploadedFile("rows.csv", b"id,name\n700,imported\n", content_type="text/csv")
            response = advanced.asset_import(factory.post("/import/", {
                "format": "csv", "database": "main", "schema": "main",
                "table": "sample", "file": upload,
            }, format="multipart"), 1)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["imported"], 1)
        result = adapters.table_data(self.asset, "main", "sample", where_field="id", where_value=700)
        self.assertEqual(result["rows"][0]["name"], "imported")

    def test_sql_export_includes_table_definition(self):
        factory = APIRequestFactory()
        with patch.object(advanced, "checked", return_value=(self.asset, None)), \
             patch.object(advanced, "record_operation_log"):
            response = advanced.asset_export(factory.get("/export/", {
                "format": "sql", "database": "main", "table": "sample",
            }), 1)
        self.assertEqual(response.status_code, 200)
        self.assertIn("CREATE TABLE sample", response.content.decode())
        self.assertIn("INSERT INTO", response.content.decode())

    def test_ddl_endpoint_uses_view_permission_and_returns_sql(self):
        factory = APIRequestFactory()
        with patch.object(advanced, "checked", return_value=(self.asset, None)):
            response = advanced.asset_ddl(factory.get("/ddl/", {
                "database": "main", "table": "sample",
            }), 1)
        self.assertEqual(response.status_code, 200)
        self.assertIn("CREATE TABLE sample", response.data["ddl"])

    def test_indexes_and_schema_operations_use_safe_identifiers(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE INDEX sample_name_idx ON sample(name)")
            connection.commit()
        self.assertEqual(adapters.indexes(self.asset, "main", "sample")[0]["name"], "sample_name_idx")
        factory = APIRequestFactory()
        with (patch.object(advanced, "checked", return_value=(self.asset, None)),
              patch.object(advanced, "record_operation_log")):
            response = advanced.asset_schema(factory.post("/schema/", {
                "database": "main", "table": "sample", "action": "add_column",
                "name": "status", "columnType": "TEXT",
            }, format="json"), 1)
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", {item["name"] for item in adapters.columns(self.asset, "main", "sample")})
        with (patch.object(advanced, "checked", return_value=(self.asset, None)),
              patch.object(advanced, "record_operation_log")):
            response = advanced.asset_schema(factory.post("/schema/", {
                "database": "main", "table": "sample", "action": "add_column",
                "name": "bad;drop", "columnType": "TEXT",
            }, format="json"), 1)
        self.assertEqual(response.status_code, 400)


class DatabasePermissionTests(TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.settings_override = override_settings(DATABASE_ASSET_SQLITE_ROOT=self.root.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        path = Path(self.root.name) / "permission.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
            connection.execute("CREATE TABLE binary_sample (id INTEGER PRIMARY KEY, payload BLOB)")
            connection.execute("INSERT INTO binary_sample (payload) VALUES (?)", (b"\xa4\xff",))
            connection.commit()
        self.asset = DatabaseAsset.objects.create(name="permission-test", db_type="sqlite",
                                                  host="", port=0, username="", options={"file": path.name})
        self.user = get_user_model().objects.create_user(username="db-reader", password="test-password")
        ensure_feature_permissions()
        self.user.user_permissions.add(Permission.objects.get(codename=FEATURE_PERMISSION_CODE_BY_KEY["databaseManagement"]))
        self.client = APIClient()
        self.client.force_login(self.user)

    def grant(self, action):
        self.user.user_permissions.add(Permission.objects.get(
            codename=PAGE_ACTION_PERMISSION_CODE_BY_KEY[("databaseManagement", action)]))
        for key in ("_perm_cache", "_user_perm_cache"):
            self.user.__dict__.pop(key, None)

    def test_sql_and_import_require_separate_action_permissions(self):
        sql_url = f"/api/database-management/assets/{self.asset.id}/sql/"
        import_url = f"/api/database-management/assets/{self.asset.id}/import/"
        self.assertEqual(self.client.post(sql_url, {"sql": "SELECT 1"}, format="json").status_code, 403)
        self.grant("execute_sql")
        self.assertEqual(self.client.post(sql_url, {"sql": "SELECT 1"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(sql_url, {"sql": "INSERT INTO sample (name) VALUES ('secret')"}, format="json").status_code, 403)
        self.assertEqual(self.client.post(sql_url, {"sql": "CREATE TABLE hidden (id INTEGER)"}, format="json").status_code, 403)
        upload = SimpleUploadedFile("rows.csv", b"id,name\n1,secret\n", content_type="text/csv")
        self.assertEqual(self.client.post(import_url, {"format": "csv", "table": "sample", "file": upload}, format="multipart").status_code, 403)
        self.grant("import_export")
        upload = SimpleUploadedFile("rows.csv", b"id,name\n1,secret\n", content_type="text/csv")
        self.assertEqual(self.client.post(import_url, {"format": "csv", "table": "sample", "file": upload}, format="multipart").status_code, 403)
        self.grant("modify_data")
        self.assertEqual(self.client.post(sql_url, {"sql": "INSERT INTO sample (name) VALUES ('allowed')"}, format="json").status_code, 200)

    def test_ddl_requires_view_data_permission(self):
        ddl_url = f"/api/database-management/assets/{self.asset.id}/ddl/?database=main&table=sample"
        self.assertEqual(self.client.get(ddl_url).status_code, 403)
        self.grant("view_data")
        response = self.client.get(ddl_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("CREATE TABLE sample", response.data["ddl"])

    def test_data_endpoint_serializes_binary_columns(self):
        data_url = f"/api/database-management/assets/{self.asset.id}/data/?database=main&table=binary_sample"
        self.assertEqual(self.client.get(data_url).status_code, 403)
        self.grant("view_data")
        response = self.client.get(data_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"][0]["payload"], "0xa4ff")

    def test_schema_mutation_requires_manage_schema(self):
        url = f"/api/database-management/assets/{self.asset.id}/schema/"
        payload = {"database": "main", "table": "sample", "action": "add_column",
                   "name": "status", "columnType": "TEXT"}
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 403)
        self.grant("manage_schema")
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 200)
        with closing(sqlite3.connect(Path(self.root.name) / "permission.sqlite3")) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(sample)")]
        self.assertIn("status", columns)

    def test_direct_page_grants_inherit_new_actions(self):
        page_permission = Permission.objects.get(codename=FEATURE_PERMISSION_CODE_BY_KEY["databaseManagement"])
        action_permission = Permission.objects.get(codename=PAGE_ACTION_PERMISSION_CODE_BY_KEY[("databaseManagement", "execute_sql")])
        self.assertFalse(self.user.user_permissions.filter(id=action_permission.id).exists())
        inherit_created_action_permissions({"databaseManagement": page_permission},
                                           {"databaseManagement": [action_permission]})
        self.assertTrue(self.user.user_permissions.filter(id=action_permission.id).exists())

    def test_directory_crud_and_asset_scoped_manifest(self):
        self.grant("create")
        self.grant("edit")
        self.grant("delete")
        self.grant("import_export")
        root = self.client.post("/api/database-management/directories/", {"name": "Operations"}, format="json")
        self.assertEqual(root.status_code, 201)
        child = self.client.post("/api/database-management/directories/", {
            "name": "Production", "parentId": root.data["id"],
        }, format="json")
        self.assertEqual(child.status_code, 201)
        self.assertEqual(child.data["parentId"], root.data["id"])
        moved = self.client.post(f"/api/database-management/assets/{self.asset.id}/move/", {
            "directoryId": child.data["id"],
        }, format="json")
        self.assertEqual(moved.status_code, 200)
        response = self.client.get(f"/api/database-management/connections/?assetId={self.asset.id}")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(len(payload["assets"]), 1)
        self.assertEqual(payload["assets"][0]["directory"], ["Operations", "Production"])
        deleted = self.client.delete(f"/api/database-management/directories/{root.data['id']}/")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(DatabaseAsset.objects.filter(pk=self.asset.id).exists())

    def test_connection_manifest_rejects_non_string_nested_paths(self):
        self.grant("import_export")
        response = self.client.post("/api/database-management/connections/", {
            "version": 1,
            "directories": [["Operations", {"unexpected": True}]],
            "assets": [],
        }, format="json")
        self.assertEqual(response.status_code, 400)


class RedisAdapterTests(SimpleTestCase):
    def test_redis_key_list_returns_sixteen_database_counts(self):
        asset = SimpleNamespace(db_type="redis", options={"db": 0})
        client = SimpleNamespace(scan_iter=lambda **_kwargs: iter(()),
                                 info=lambda section: {"db0": {"keys": 1}, "db5": {"keys": 3}})
        with patch.object(advanced, "checked", return_value=(asset, None)), \
             patch.object(advanced.adapters, "connection") as connection:
            connection.return_value.__enter__.return_value = client
            response = advanced.asset_redis(APIRequestFactory().get("/redis/?db=5"), 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["counts"], [1, 0, 0, 0, 0, 3] + [0] * 10)
        connection.assert_called_once_with(asset, database=5)

    def test_redis_database_number_is_limited_to_visible_range(self):
        asset = SimpleNamespace(options={"db": 0})
        self.assertEqual(advanced.selected_redis_database(asset, "15"), 15)
        self.assertEqual(advanced.selected_redis_database(asset, "255"), 255)
        with self.assertRaises(ValueError):
            advanced.selected_redis_database(asset, "256")

    def test_connect_uses_redis_username_parameter(self):
        asset = SimpleNamespace(db_type="redis", host="redis.example", port=6379,
                                username="admin", password_encrypted="", options={"db": 2})
        fake_module = SimpleNamespace(Redis=lambda **kwargs: kwargs)
        with patch.object(adapters, "module_for", return_value=fake_module):
            options = adapters.connect(asset)
        self.assertEqual(options["username"], "admin")
        self.assertEqual(options["password"], None)
        self.assertEqual(options["db"], 2)
        with patch.object(adapters, "module_for", return_value=fake_module):
            selected = adapters.connect(asset, database=5)
        self.assertEqual(selected["db"], 5)

    def test_connect_omits_empty_redis_credentials(self):
        asset = SimpleNamespace(db_type="redis", host="redis.example", port=6379,
                                username="", password_encrypted="", options={})
        fake_module = SimpleNamespace(Redis=lambda **kwargs: kwargs)
        with patch.object(adapters, "module_for", return_value=fake_module):
            options = adapters.connect(asset)
        self.assertIsNone(options["username"])
        self.assertIsNone(options["password"])

    def test_export_refuses_truncated_collection_values(self):
        client = SimpleNamespace(llen=lambda _key: 501)
        with self.assertRaisesMessage(ValueError, "超过 500 个成员"):
            advanced.redis_export_value(client, "large-list", "list")

    def test_zset_editor_accepts_redis_pairs_and_form_objects(self):
        self.assertEqual(advanced.redis_zset_mapping([("one", 1.5), {"member": "two", "score": 2}]),
                         {"one": 1.5, "two": 2.0})
