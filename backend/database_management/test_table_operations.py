from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from . import object_operations, table_operations, task_permissions, transfers
from .models import DatabaseAsset, DatabaseTransferTask


class TableOperationSqlTests(SimpleTestCase):
    def test_mysql_table_ddl_returns_the_complete_native_create_statement(self):
        ddl = "CREATE TABLE `sample` (`id` int NOT NULL AUTO_INCREMENT, PRIMARY KEY (`id`)) ENGINE=InnoDB AUTO_INCREMENT=42 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='sample table'"
        connection = patch.object(table_operations.adapters, "connection")
        with connection as connect, patch.object(table_operations.adapters, "run", return_value=([{"Create Table": ddl}], 1)):
            connect.return_value.__enter__.return_value = object()
            result = table_operations.adapters.table_ddl(
                SimpleNamespace(db_type="mysql"), "tele", "sample"
            )

        self.assertEqual(result, ddl)

    def test_ddl_parser_preserves_quoted_commas_and_extracts_keys(self):
        ddl = "CREATE TABLE `sample` (`id` int NOT NULL, `note` varchar(40) DEFAULT 'a,b', PRIMARY KEY (`id`), UNIQUE KEY `uq_note` (`note`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='table, note'"

        fields, indexes, unsupported = table_operations.definitions(ddl)

        self.assertEqual(set(fields), {"id", "note"})
        self.assertIn("DEFAULT 'a,b'", fields["note"])
        self.assertEqual(set(indexes), {"PRIMARY", "uq_note"})
        self.assertEqual(unsupported, [])

    def test_structure_sync_keeps_target_only_objects_by_default(self):
        source = {
            "fields": {"id": "`id` int NOT NULL", "name": "`name` varchar(40) DEFAULT NULL"},
            "indexes": {"PRIMARY": "PRIMARY KEY (`id`)", "name_idx": "KEY `name_idx` (`name`)"},
        }
        target = {
            "fields": {"id": "`id` int NOT NULL", "legacy": "`legacy` varchar(20) DEFAULT NULL"},
            "indexes": {"PRIMARY": "PRIMARY KEY (`id`)", "legacy_idx": "KEY `legacy_idx` (`legacy`)"},
        }

        safe_sql = " ".join(table_operations.structure_sql(source, target, "target"))
        destructive_sql = " ".join(table_operations.structure_sql(source, target, "target", delete_extras=True))

        self.assertIn("ADD COLUMN `name`", safe_sql)
        self.assertNotIn("DROP COLUMN", safe_sql)
        self.assertNotIn("DROP INDEX", safe_sql)
        self.assertIn("DROP COLUMN `legacy`", destructive_sql)
        self.assertIn("DROP INDEX `legacy_idx`", destructive_sql)

    def test_data_sync_without_matching_primary_keys_is_blocked(self):
        source = {"fields": {"id": "`id` int NOT NULL"}, "indexes": {}, "unsupported": [], "primaryKey": ["id"], "rows": 1, "ddl": "ENGINE=InnoDB"}
        target = {"fields": {"id": "`id` int NOT NULL"}, "indexes": {}, "unsupported": [], "primaryKey": [], "rows": 1, "ddl": "ENGINE=InnoDB", "columns": []}

        preview = table_operations.build_preview(source, target, "data")

        self.assertFalse(preview["canExecute"])
        self.assertFalse(preview["matchingPrimaryKey"])
        self.assertTrue(any("主键" in conflict for conflict in preview["conflicts"]))

    def test_update_requires_matching_primary_key_names(self):
        source = {"fields": {"id": "`id` int NOT NULL", "value": "`value` int"}, "indexes": {}, "unsupported": [], "primaryKey": ["id"], "rows": 1, "ddl": "ENGINE=InnoDB"}
        target = {"fields": {"id": "`id` int NOT NULL", "value": "`value` int"}, "indexes": {}, "unsupported": [], "primaryKey": ["other"], "rows": 1, "ddl": "ENGINE=InnoDB", "columns": []}

        preview = table_operations.build_preview(source, target, "copy")

        self.assertFalse(preview["matchingPrimaryKey"])

    def test_data_preview_accepts_the_full_sample_and_compares_binary_values_without_conversion(self):
        metadata = {"fields": {"id": "`id` int NOT NULL", "payload": "`payload` blob"}, "primaryKey": ["id"], "rows": 1000}
        asset = SimpleNamespace(db_type="mysql")
        reference = {"database": "tele", "table": "sample"}
        rows = [{"id": number, "payload": b"\x00\xff"} for number in range(1000)]

        def run(_connection, sql, _params=(), **options):
            self.assertFalse(options["json_safe"])
            if "LIMIT" in sql:
                self.assertEqual(options["max_rows"], 1000)
                return rows, len(rows)
            return [{"id": 0, "payload": b"\x00\xff"}], 1

        with patch.object(table_operations.adapters, "connection", side_effect=lambda *_args: nullcontext(object())), \
             patch.object(table_operations.adapters, "run", side_effect=run):
            result = table_operations.data_preview(asset, reference, asset, reference, metadata, metadata)

        self.assertEqual(result["sampledRows"], 1000)
        self.assertEqual(result["unchangedRows"], 1000)
        self.assertTrue(result["exact"])


class TableOperationConfirmationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="table-operations", password="test-password")
        self.asset = DatabaseAsset.objects.create(name="mysql", db_type="mysql", host="localhost", username="test", database="tele")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/database-management/assets/{self.asset.pk}/objects/action/"

    def test_table_destructive_actions_require_explicit_confirmation(self):
        with patch.object(object_operations.adapters, "connection") as connection:
            missing = self.client.post(self.url, {"action": "delete_rows", "database": "tele", "name": "sample", "objectType": "table"}, format="json")
            mismatch = self.client.post(self.url, {"action": "drop", "database": "tele", "name": "sample", "confirmName": "other", "confirmed": True, "objectType": "table"}, format="json")

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(mismatch.status_code, 400)
        connection.assert_not_called()

    def test_delete_rows_uses_modify_data_permission_and_confirmed_request(self):
        with patch.object(object_operations, "require_feature_permission", return_value=None) as permission, \
             patch.object(object_operations.adapters, "connection"), \
             patch.object(object_operations.adapters, "run", return_value=([], 0)):
            response = self.client.post(self.url, {"action": "delete_rows", "database": "tele", "name": "sample", "objectType": "table", "confirmed": True}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(permission.call_args.args[2], "modify_data")

    def test_table_operation_preview_requires_all_mode_permissions(self):
        with patch.object(table_operations, "has_feature_permission", side_effect=[True, False]):
            with self.assertRaises(PermissionError):
                table_operations.require_permissions(self.user, "copy")

    def test_table_operation_reference_rejects_read_only_write_targets(self):
        self.asset.options = {"readOnly": True}
        self.asset.save(update_fields=["options"])

        with self.assertRaisesMessage(ValueError, "只读模式"):
            table_operations.resolve_reference(
                {"assetId": self.asset.pk, "database": "tele", "table": "sample"}, write=True
            )

    def test_table_operation_preview_requires_confirmed_execution(self):
        source_ref = {"assetId": self.asset.pk, "database": "tele", "schema": "", "table": "source"}
        target_ref = {"assetId": self.asset.pk, "database": "tele", "schema": "", "table": "target"}
        metadata = {
            "ddl": "CREATE TABLE `sample` (`id` int NOT NULL) ENGINE=InnoDB",
            "fields": {"id": "`id` int NOT NULL"},
            "indexes": {"PRIMARY": "PRIMARY KEY (`id`)"},
            "unsupported": [], "columns": [{"name": "id", "column_key": "PRI"}],
            "primaryKey": ["id"], "rows": 1, "fingerprint": "same",
        }
        with patch.object(table_operations, "resolve_reference", side_effect=[(self.asset, source_ref), (self.asset, target_ref)]), \
             patch.object(table_operations, "metadata", side_effect=[metadata, metadata]), \
             patch.object(table_operations, "record_operation_log"):
            preview = self.client.post("/api/database-management/table-operations/preview/", {
                "mode": "structure", "source": source_ref, "target": target_ref,
            }, format="json")

        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertTrue(preview.data["canExecute"])
        task_id = preview.data["previewId"]
        denied = self.client.post("/api/database-management/table-operations/execute/", {
            "previewId": task_id, "confirmed": False,
        }, format="json")
        self.assertEqual(denied.status_code, 400)

        with patch.object(table_operations, "resolve_reference", side_effect=[(self.asset, source_ref), (self.asset, target_ref)]), \
             patch.object(table_operations, "record_operation_log"):
            queued = self.client.post("/api/database-management/table-operations/execute/", {
                "previewId": task_id, "confirmed": True,
            }, format="json")

        self.assertEqual(queued.status_code, 202, queued.data)

    def test_users_with_sync_permissions_can_list_only_their_authorized_table_tasks(self):
        expiry = timezone.now() + timedelta(days=1)
        common = {
            "owner": self.user,
            "asset": self.asset,
            "direction": "import",
            "format": "internal",
            "database": "tele",
            "expires_at": expiry,
        }
        structure = DatabaseTransferTask.objects.create(
            **common, scope="table-operation", parameters={"mode": "structure"}, source_name="结构同步"
        )
        data = DatabaseTransferTask.objects.create(
            **common, scope="table-operation", parameters={"mode": "data"}, source_name="数据同步"
        )
        export = DatabaseTransferTask.objects.create(
            **common, scope="table", parameters={}, source_name="database.sql"
        )

        def has_permission(_user, _feature, action):
            return action in {"view_data", "manage_schema"}

        with patch.object(transfers, "has_feature_permission", side_effect=has_permission), \
             patch.object(table_operations, "has_feature_permission", side_effect=has_permission):
            response = self.client.get("/api/database-management/transfers/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [str(structure.pk)])
        self.assertNotIn(str(data.pk), [item["id"] for item in response.data])
        self.assertNotIn(str(export.pk), [item["id"] for item in response.data])
        with patch.object(transfers, "has_feature_permission", side_effect=has_permission), \
             patch.object(table_operations, "has_feature_permission", side_effect=has_permission):
            denied_detail = self.client.get(f"/api/database-management/transfers/{data.pk}/")
            structure_detail = self.client.get(f"/api/database-management/transfers/{structure.pk}/")
        self.assertEqual(denied_detail.status_code, 403)
        self.assertEqual(structure_detail.status_code, 200)

    def test_transfer_creation_still_requires_import_export_permission(self):
        with patch.object(
            transfers,
            "require_feature_permission",
            return_value=Response({"error": "没有导入导出权限"}, status=403),
        ), patch.object(transfers, "export_response") as create_export:
            response = self.client.post("/api/database-management/transfers/", {}, format="json")

        self.assertEqual(response.status_code, 403)
        create_export.assert_not_called()

    def test_live_task_updates_are_filtered_by_operation_permission(self):
        def has_permission(_user, _feature, action):
            return action in {"view_data", "manage_schema"}

        with patch.object(task_permissions, "has_feature_permission", side_effect=has_permission):
            self.assertTrue(task_permissions.can_view_transfer_payload(self.user, {
                "scope": "table-operation", "operationMode": "structure",
            }))
            self.assertFalse(task_permissions.can_view_transfer_payload(self.user, {
                "scope": "table-operation", "operationMode": "data",
            }))
            self.assertFalse(task_permissions.can_view_transfer_payload(self.user, {
                "scope": "table", "operationMode": "",
            }))


class TableOperationWorkerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="table-operation-worker", password="test-password")
        self.source_asset = DatabaseAsset.objects.create(name="source", db_type="mysql", host="source", username="test", database="tele")
        self.target_asset = DatabaseAsset.objects.create(name="target", db_type="mysql", host="target", username="test", database="tele")
        self.source_ref = {"assetId": self.source_asset.pk, "database": "tele", "schema": "", "table": "source"}
        self.target_ref = {"assetId": self.target_asset.pk, "database": "tele", "schema": "", "table": "target"}
        self.metadata = {
            "ddl": "CREATE TABLE `sample` (`id` int NOT NULL AUTO_INCREMENT, `name` varchar(40) DEFAULT NULL, PRIMARY KEY (`id`)) ENGINE=InnoDB",
            "fields": {"id": "`id` int NOT NULL AUTO_INCREMENT", "name": "`name` varchar(40) DEFAULT NULL"},
            "indexes": {"PRIMARY": "PRIMARY KEY (`id`)"},
            "unsupported": [],
            "columns": [
                {"name": "id", "column_key": "PRI", "nullable": "NO", "default": None},
                {"name": "name", "column_key": "", "nullable": "YES", "default": None},
            ],
            "primaryKey": ["id"], "rows": 2, "fingerprint": "same",
        }
        self.task = SimpleNamespace(
            owner=self.user,
            parameters={
                "mode": "data", "source": self.source_ref, "target": self.target_ref,
                "sourceFingerprint": "same", "targetFingerprint": "same",
            },
            conflict_policy="update",
            pk="worker-test",
        )

    def run_worker(self, fail_on_insert=False, insert_error=None):
        source_connection, target_connection = Mock(), Mock()
        self.worker_target_connection = target_connection
        source_batches = [[{"id": 1, "name": "updated"}, {"id": 2, "name": "inserted"}], []]
        target_lookups = [[{"id": 1, "name": "old"}], []]
        statements = []

        def run(connection, sql, params=(), **_kwargs):
            statements.append((connection, sql, params))
            if sql.startswith("SELECT `id`, `name` FROM `source`"):
                self.assertFalse(_kwargs["json_safe"])
                return source_batches.pop(0), 0
            if sql.startswith("SELECT `id`, `name` FROM `target`"):
                self.assertFalse(_kwargs["json_safe"])
                return target_lookups.pop(0), 0
            if fail_on_insert and sql.startswith("INSERT INTO `target`"):
                raise RuntimeError("write failed")
            if insert_error and sql.startswith("INSERT INTO `target`"):
                raise insert_error
            return [], 0

        with patch.object(table_operations, "resolve_reference", side_effect=[(self.source_asset, self.source_ref), (self.target_asset, self.target_ref)]), \
             patch.object(table_operations, "metadata", side_effect=[self.metadata, self.metadata]), \
             patch.object(table_operations.adapters, "connection", side_effect=lambda asset, _database: nullcontext(source_connection if asset.pk == self.source_asset.pk else target_connection)), \
             patch.object(table_operations.adapters, "run", side_effect=run), \
             patch.object(table_operations, "enforce_policy"), \
             patch.object(table_operations, "resource_guard"):
            table_operations.execute_task(self.task, Mock())

        return target_connection, statements

    def test_data_sync_updates_matching_keys_inserts_missing_keys_and_commits(self):
        target_connection, statements = self.run_worker()

        target_writes = [(sql, params) for connection, sql, params in statements if connection is target_connection and sql.startswith(("UPDATE", "INSERT"))]
        self.assertEqual(target_writes, [
            ("UPDATE `target` SET `name`=%s WHERE `id`=%s", ("updated", 1)),
            ("INSERT INTO `target` (`id`, `name`) VALUES (%s, %s)", (2, "inserted")),
        ])
        target_connection.commit.assert_called_once()
        target_connection.rollback.assert_not_called()

    def test_data_sync_rolls_back_target_after_a_write_failure(self):
        with self.assertRaisesMessage(RuntimeError, "write failed"):
            self.run_worker(fail_on_insert=True)

        self.worker_target_connection.rollback.assert_called_once()
        self.worker_target_connection.commit.assert_not_called()

    def test_skip_policy_only_skips_duplicate_keys_and_rolls_back_other_integrity_errors(self):
        self.task.conflict_policy = "skip"
        target_connection, _ = self.run_worker(insert_error=RuntimeError(1062, "duplicate key"))
        target_connection.commit.assert_called_once()
        target_connection.rollback.assert_not_called()

        with self.assertRaises(RuntimeError):
            self.run_worker(insert_error=RuntimeError(1452, "foreign key violation"))
        self.worker_target_connection.rollback.assert_called_once()
        self.worker_target_connection.commit.assert_not_called()
