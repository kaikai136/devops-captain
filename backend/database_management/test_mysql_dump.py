import io
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .mysql_dump import DumpError, generated_column, literal, parse_statement, scan_dump, sql_literal, statements, unspool_value
from . import mysql_dump, transfers
from .models import DatabaseAsset, DatabaseTransferTask


@override_settings(DATABASE_TRANSFER_MAX_ROWS=0, DATABASE_TRANSFER_MAX_TABLES=0, DATABASE_TRANSFER_BATCH_ROWS=2)
class MysqlDumpParserTests(SimpleTestCase):
    def test_navicat_structure_and_values(self):
        sql = """/* dump */ SET NAMES utf8mb4; SET FOREIGN_KEY_CHECKS=0;
        DROP TABLE IF EXISTS `sample`;
        CREATE TABLE `sample` (
          `id` int NOT NULL AUTO_INCREMENT,
          `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'name',
          `amount` decimal(20, 4),
          PRIMARY KEY (`id`) USING BTREE,
          INDEX `name_idx` (`name` ASC) USING BTREE
        ) ENGINE=InnoDB AUTO_INCREMENT=15 CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=Dynamic;
        INSERT INTO `sample` VALUES (1, 'hello', 123456789012.1234);
        SET FOREIGN_KEY_CHECKS=1;"""
        parsed = [parse_statement(item) for item in statements(io.StringIO(sql))]
        self.assertEqual(parsed[3]["columns"], ["id", "name", "amount"])
        self.assertEqual(parsed[4]["rows"], [[1, "hello", Decimal("123456789012.1234")]])

    def test_literal_round_trip(self):
        for value in [None, 3, -9, Decimal("12345678901234567890.1234"), 0.125,
                      "中文'\\\n\r\x00\x1a;--", b"\x00\xff", "double''quote"]:
            with self.subTest(value=value):
                self.assertEqual(literal(sql_literal(value)), value)

    def test_splitter_handles_every_chunk_boundary(self):
        class TinyReader(io.StringIO):
            def read(self, size=-1): return super().read(1)
        sql = "/* comment */ INSERT INTO `t` VALUES ('a\\\'b;--', 'c''d'); -- comment\nINSERT INTO `t` VALUES (NULL, X'ff');"
        self.assertEqual(len(list(statements(TinyReader(sql)))), 2)
        self.assertEqual(parse_statement(list(statements(TinyReader(sql)))[0])["rows"], [["a'b;--", "c'd"]])

    def test_splitter_reports_read_progress_with_one_long_statement(self):
        sql = "INSERT INTO sample VALUES ('" + "x" * 150000 + "');"
        positions = []
        parsed = list(statements(io.StringIO(sql), on_read=positions.append))
        self.assertEqual(parsed, [sql[:-1]])
        self.assertGreater(len(positions), 1)
        self.assertLess(positions[0], len(sql))
        self.assertEqual(positions[-1], len(sql))

    def test_large_insert_parser_sends_heartbeat(self):
        sql = "INSERT INTO sample VALUES " + ",".join("(1)" for _ in range(25000))
        heartbeat = MagicMock()
        parsed = parse_statement(sql, heartbeat=heartbeat)
        self.assertEqual(len(parsed["rows"]), 25000)
        heartbeat.assert_called()

    def test_rejects_unsafe_and_malformed_statements(self):
        for sql in ["DROP DATABASE test", "DROP TABLE `t`", "INSERT INTO other.t VALUES (1)",
                    "INSERT INTO t SELECT 1", "INSERT INTO t VALUES (SLEEP(1))", "INSERT INTO t VALUES (1) ON DUPLICATE KEY UPDATE id=1",
                    "CREATE TABLE t AS SELECT 1", "CREATE TABLE other.t (id int)",
                    "CREATE TABLE t (id int) ENGINE=FEDERATED", "CREATE TABLE t (id int) DATA DIRECTORY='/tmp'",
                    "CREATE TABLE t (id int REFERENCES other.t(id))", "SET GLOBAL x=1", "USE other",
                    "CREATE TABLE t (id int DEFAULT (evil()))", "CREATE TABLE t (id int AS (`evil`()))",
                    "INSERT INTO t VALUES (1,)", "INSERT INTO t VALUES (1", "SET NAMES latin1"]:
            with self.subTest(sql=sql), self.assertRaises(DumpError): parse_statement(sql)
        for sql in ["/*!50000 DROP TABLE t */;", "INSERT INTO t VALUES ('unfinished)", "/* unclosed"]:
            with self.assertRaises(DumpError): list(statements(io.StringIO(sql)))

    def test_statement_memory_guard(self):
        with self.assertRaises(DumpError): list(statements(io.StringIO("INSERT INTO t VALUES ('large')"), limit=12))

    def test_scan_targets_duplicates_and_drop_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dump.sql"
            task = SimpleNamespace(input_path=str(path), scope="table", object_name="sample")
            path.write_text("CREATE TABLE sample (id int); INSERT INTO sample VALUES (1), (2);", encoding="utf-8")
            definitions, details = scan_dump(task, Path(folder))
            self.assertEqual(details[0]["rows"], 2)
            self.assertTrue((Path(folder) / "0.jsonl").is_file())
            self.assertIn("sample", definitions)
            for sql in ["CREATE TABLE other (id int);", "DROP TABLE IF EXISTS sample;",
                        "CREATE TABLE sample (id int); CREATE TABLE sample (id int);"]:
                path.write_text(sql, encoding="utf-8")
                with self.assertRaises(DumpError): scan_dump(task)

    def test_scan_spools_parsed_rows_and_preserves_decimal_and_binary_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dump.sql"
            task = SimpleNamespace(input_path=str(path), scope="table", object_name="sample")
            path.write_text("INSERT INTO sample (id, amount, payload) VALUES (1, 123.4500, X'00ff');", encoding="utf-8")
            (Path(folder) / "spool").mkdir()
            scan_dump(task, Path(folder) / "spool")
            item = json.loads((Path(folder) / "spool" / "0.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(item["kind"], "insert")
            self.assertEqual(item["rows"][0][0], 1)
            self.assertEqual(unspool_value(item["rows"][0][1]), Decimal("123.4500"))
            self.assertEqual(unspool_value(item["rows"][0][2]), b"\x00\xff")

    @override_settings(DATABASE_TRANSFER_MIN_FREE_BYTES=5)
    def test_scan_checks_disk_space_during_a_single_large_insert(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dump.sql"
            spool = Path(folder) / "spool"
            spool.mkdir()
            task = SimpleNamespace(input_path=str(path), scope="table", object_name="sample")
            path.write_text("INSERT INTO sample (id) VALUES (1);", encoding="utf-8")
            with patch.object(mysql_dump.clock, "monotonic", side_effect=[0, 2]), patch.object(
                mysql_dump.shutil, "disk_usage", side_effect=[SimpleNamespace(free=10), SimpleNamespace(free=5)]
            ):
                with self.assertRaisesRegex(DumpError, "临时磁盘空间不足"):
                    scan_dump(task, spool)

    def test_default_generated_is_not_a_generated_column(self):
        self.assertFalse(generated_column("DEFAULT_GENERATED on update CURRENT_TIMESTAMP"))
        self.assertTrue(generated_column("VIRTUAL GENERATED"))
        self.assertTrue(generated_column("STORED GENERATED"))

    def test_generated_expression_and_timestamp_default(self):
        item = parse_statement("CREATE TABLE t (id int, doubled int GENERATED ALWAYS AS (id * 2) STORED, created timestamp DEFAULT CURRENT_TIMESTAMP(6)) ENGINE=InnoDB")
        self.assertEqual(item["columns"], ["id", "doubled", "created"])


@override_settings(DATABASE_TRANSFER_MIN_FREE_BYTES=0, DATABASE_TRANSFER_BATCH_ROWS=2,
                   DATABASE_TRANSFER_MAX_ROWS=0, DATABASE_TRANSFER_MAX_TABLES=0,
                   DATABASE_TRANSFER_MAX_RESULT_BYTES=0)
class MysqlDumpExecutionTests(SimpleTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "input.sql"
        self.task = SimpleNamespace(pk="sample", input_path=str(self.path), output_path=str(self.path),
                                    parameters={"tables": ["sample"], "content": "structure_data"},
                                    asset=SimpleNamespace(db_type="mysql"), database="test", scope="table",
                                    object_name="sample", owner=None, started_at=None, checkpoints={}, processed_rows=0,
                                    conflict_policy="append", preview={})
        self.conn = MagicMock()
        self.conn.__enter__.return_value = self.conn
        self.queries = []

    def query(self, conn, sql, params=()):
        self.queries.append((sql, params))
        if "@@FOREIGN_KEY_CHECKS" in sql: return [{"value": 1}]
        if "VERSION()" in sql: return [{"version": "8.0"}]
        if "SHOW CREATE TABLE" in sql: return [{"Create Table": "CREATE TABLE `sample` (`id` int, `doubled` int GENERATED ALWAYS AS (`id` * 2) STORED) ENGINE=InnoDB"}]
        return []

    def update(self, task, **values):
        for key, value in values.items(): setattr(task, key, value)

    def context(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(mysql_dump.adapters, "connection", return_value=self.conn))
        stack.enter_context(patch.object(mysql_dump, "query", side_effect=self.query))
        stack.enter_context(patch.object(mysql_dump, "table_metadata", return_value={"sample": {"ENGINE": "InnoDB"}}))
        stack.enter_context(patch.object(mysql_dump, "table_columns", return_value=[{"COLUMN_NAME": "id", "EXTRA": ""}, {"COLUMN_NAME": "doubled", "EXTRA": "STORED GENERATED"}]))
        stack.enter_context(patch.object(transfers, "require_task_permissions", return_value=True))
        from . import connection_config
        stack.enter_context(patch.object(connection_config, "enforce_policy"))
        stack.enter_context(patch.object(transfers, "update", side_effect=self.update))
        return stack

    def test_export_modes_use_server_cursor_and_exclude_generated_fields(self):
        from pymysql.cursors import SSCursor
        for content in ("structure_data", "structure", "data"):
            with self.subTest(content=content), self.context():
                self.task.parameters["content"] = content
                cursor = self.conn.cursor.return_value.__enter__.return_value
                cursor.fetchmany.side_effect = [[(0,), (2,)], [(3,)], []]
                output = io.StringIO()
                mysql_dump.export_dump(self.task, output, MagicMock())
                dump = output.getvalue()
                parsed = [parse_statement(sql) for sql in statements(io.StringIO(dump))]
                self.assertEqual(any(item["kind"] == "create" for item in parsed), content != "data")
                self.assertEqual(sum(len(item["rows"]) for item in parsed if item["kind"] == "insert"), 0 if content == "structure" else 3)
                if content != "structure":
                    self.conn.cursor.assert_called_with(SSCursor)
                    self.assertIn("INSERT INTO `sample` (`id`) VALUES (0)", dump)
                self.assertIn("DevOps Captain", dump)
                self.assertNotIn("Navicat", dump)

    def test_import_strategies_parameterize_values_and_checkpoint(self):
        self.path.write_text("DROP TABLE IF EXISTS sample; CREATE TABLE sample (id int); INSERT INTO sample (id) VALUES (1),(2),(3);", encoding="utf-8")
        for policy in ("append", "overwrite", "skip"):
            with self.subTest(policy=policy), self.context():
                self.queries.clear(); self.conn.reset_mock()
                self.task.conflict_policy = policy
                self.task.checkpoints = {}; self.task.processed_rows = 0
                mysql_dump.import_dump(self.task, MagicMock())
                self.assertEqual(self.task.checkpoints["completedTables"], ["sample"])
                cursor = self.conn.cursor.return_value.__enter__.return_value
                self.assertEqual(cursor.executemany.call_count, 0 if policy == "skip" else 2)
                sqls = [sql for sql, _ in self.queries]
                self.assertEqual(any(sql.startswith("DROP TABLE") for sql in sqls), policy == "overwrite")
                self.assertEqual(self.task.processed_rows, 0 if policy == "skip" else 3)
                self.assertEqual(self.queries[-1], ("SET FOREIGN_KEY_CHECKS=%s", (1,)))

    def test_import_batches_consecutive_single_row_inserts_by_columns(self):
        self.path.write_text(
            "INSERT INTO sample (id) VALUES (1); INSERT INTO sample (id) VALUES (2); "
            "INSERT INTO sample (id) VALUES (3); INSERT INTO sample (other) VALUES (4); "
            "INSERT INTO sample (other) VALUES (5);",
            encoding="utf-8",
        )
        with self.context(), patch.object(
            mysql_dump,
            "table_columns",
            return_value=[
                {"COLUMN_NAME": "id", "EXTRA": ""},
                {"COLUMN_NAME": "other", "EXTRA": ""},
                {"COLUMN_NAME": "doubled", "EXTRA": "STORED GENERATED"},
            ],
        ):
            mysql_dump.import_dump(self.task, MagicMock())
        calls = self.conn.cursor.return_value.__enter__.return_value.executemany.call_args_list
        self.assertEqual(
            [(call.args[0], call.args[1]) for call in calls],
            [
                ("INSERT INTO `sample` (`id`) VALUES (%s)", [[1], [2]]),
                ("INSERT INTO `sample` (`id`) VALUES (%s)", [[3]]),
                ("INSERT INTO `sample` (`other`) VALUES (%s)", [[4], [5]]),
            ],
        )

    @override_settings(DATABASE_TRANSFER_BATCH_ROWS=1)
    def test_import_throttles_batch_reports_and_forces_table_completion_report(self):
        self.path.write_text(
            "INSERT INTO sample (id) VALUES (1); INSERT INTO sample (id) VALUES (2); INSERT INTO sample (id) VALUES (3);",
            encoding="utf-8",
        )
        report = MagicMock()
        with self.context(), patch.object(mysql_dump.clock, "monotonic", return_value=10):
            mysql_dump.import_dump(self.task, report)
        self.assertEqual(report.call_count, 3)
        self.assertEqual(report.call_args_list[0].kwargs["stage"], "validating_sql")
        self.assertEqual(report.call_args_list[1].kwargs["stage"], "importing_table:sample")
        self.assertEqual(report.call_args_list[2].kwargs, {"stage": "importing_table:sample", "rows": 3, "total": 3})

    def test_import_checks_revoked_permissions_before_each_batch_write(self):
        self.path.write_text("INSERT INTO sample (id) VALUES (1);", encoding="utf-8")
        with self.context() as stack:
            stack.enter_context(patch.object(transfers, "require_task_permissions", side_effect=[True, True, False]))
            with self.assertRaises(PermissionError):
                mysql_dump.import_dump(self.task, MagicMock())
        self.conn.cursor.return_value.__enter__.return_value.executemany.assert_not_called()

    def test_import_checks_cancellation_before_each_batch_write(self):
        self.path.write_text("INSERT INTO sample (id) VALUES (1);", encoding="utf-8")
        self.task.cancel_requested = True
        with self.context(), self.assertRaises(InterruptedError):
            mysql_dump.import_dump(self.task, MagicMock())
        self.conn.cursor.return_value.__enter__.return_value.executemany.assert_not_called()

    def test_data_only_overwrite_deletes_without_drop(self):
        self.path.write_text("INSERT INTO sample (id) VALUES (1);", encoding="utf-8")
        self.task.conflict_policy = "overwrite"
        with self.context(): mysql_dump.import_dump(self.task, MagicMock())
        self.assertIn(("DELETE FROM `sample`", ()), self.queries)
        self.assertFalse(any(sql.startswith("DROP") for sql, _ in self.queries))

    def test_unsafe_tail_is_rejected_before_any_target_mutation(self):
        self.path.write_text("CREATE TABLE sample (id int); INSERT INTO sample VALUES (1); DROP DATABASE test;", encoding="utf-8")
        with self.context(), self.assertRaises(DumpError): mysql_dump.import_dump(self.task, MagicMock())
        self.assertEqual(self.queries, [])

    def test_insert_failure_rolls_back_and_restores_foreign_keys(self):
        self.path.write_text("INSERT INTO sample (id) VALUES (1);", encoding="utf-8")
        self.conn.cursor.return_value.__enter__.return_value.executemany.side_effect = RuntimeError("driver secret")
        with self.context(), self.assertRaises(RuntimeError): mysql_dump.import_dump(self.task, MagicMock())
        self.conn.rollback.assert_called()
        self.assertEqual(self.task.processed_rows, 0)
        self.assertEqual(self.queries[-1], ("SET FOREIGN_KEY_CHECKS=%s", (1,)))


    def test_continue_on_error_finishes_remaining_tables_and_reports_failure(self):
        self.path.write_text("CREATE TABLE first (id int); INSERT INTO first VALUES (1); CREATE TABLE sample (id int); INSERT INTO sample VALUES (2);", encoding="utf-8")
        self.task.scope = "database"
        self.task.parameters["options"] = {"continueOnError": True, "asyncInsert": False}
        self.conn.cursor.return_value.__enter__.return_value.executemany.side_effect = [RuntimeError("bad row"), None]
        with self.context(), self.assertRaises(DumpError): mysql_dump.import_dump(self.task, MagicMock())
        self.assertEqual(self.task.checkpoints["failedTables"], ["first"])
        self.assertEqual(self.task.checkpoints["completedTables"], ["sample"])
        self.assertEqual(self.conn.cursor.return_value.__enter__.return_value.executemany.call_count, 2)
        self.assertTrue(self.task.preview["warnings"])

    def test_disabled_batching_writes_one_row_at_a_time(self):
        self.path.write_text("INSERT INTO sample (id) VALUES (1),(2),(3);", encoding="utf-8")
        self.task.parameters["options"] = {"asyncInsert": False}
        with self.context(): mysql_dump.import_dump(self.task, MagicMock())
        calls = self.conn.cursor.return_value.__enter__.return_value.executemany.call_args_list
        self.assertEqual([len(call.args[1]) for call in calls], [1, 1, 1])

    def test_continue_never_swallows_cancellation_permissions_or_resource_limits(self):
        for error in [InterruptedError("cancel"), PermissionError("revoked"), mysql_dump.ResourceLimitError("limit")]:
            with self.subTest(error=error):
                self.path.write_text("INSERT INTO sample (id) VALUES (1);", encoding="utf-8")
                self.task.parameters["options"] = {"continueOnError": True}
                self.conn.cursor.return_value.__enter__.return_value.executemany.side_effect = error
                with self.context(), self.assertRaises(type(error)): mysql_dump.import_dump(self.task, MagicMock())


class MysqlDumpTaskTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.override = override_settings(DATABASE_TRANSFER_DIR=self.folder.name, DATABASE_TRANSFER_MIN_FREE_BYTES=0,
                                          DATABASE_TRANSFER_CHUNK_BYTES=8, DATABASE_TRANSFER_MAX_UPLOAD_BYTES=0)
        self.override.enable(); self.addCleanup(self.override.disable)
        self.user = get_user_model().objects.create_superuser(username="dump-user", password="test-password")
        self.asset = DatabaseAsset.objects.create(name="dump", db_type="mysql", host="localhost", username="test", database="test")
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.emit_patch = patch.object(transfers, "emit"); self.emit_patch.start(); self.addCleanup(self.emit_patch.stop)
        self.base = "/api/database-management/transfers/"

    def test_export_validates_format_and_scope(self):
        data = {"assetId": self.asset.pk, "direction": "export", "scope": "table", "format": "sql", "objectName": "sample"}
        self.assertEqual(self.client.post(self.base, data, format="json").status_code, 202)
        for changes in ({"format": "csv"}, {"tables": ["sample", "other"]}, {"tables": ["bad.name"]}):
            self.assertEqual(self.client.post(self.base, {**data, **changes}, format="json").status_code, 400)

    def test_upload_persists_validated_import_options(self):
        payload = {"assetId": self.asset.pk, "scope": "database", "format": "sql", "fileName": "dump.sql", "chunks": 1, "totalBytes": 0,
                   "options": {"continueOnError": True, "asyncInsert": False}}
        response = self.client.post(self.base + "uploads/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(DatabaseTransferTask.objects.get(pk=response.data["id"]).parameters["options"], payload["options"])
        self.assertEqual(self.client.post(self.base + "uploads/", {**payload, "options": {"continueOnError": "yes"}}, format="json").status_code, 400)

    def test_chunk_upload_streams_past_request_memory_limit_and_cleans_oversized_chunks(self):
        payload = {"assetId": self.asset.pk, "scope": "table", "format": "sql", "objectName": "sample",
                   "fileName": "sample.sql", "chunks": 1, "totalBytes": 8}
        response = self.client.post(self.base + "uploads/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        task_id = response.data["id"]
        oversized_payload = {**payload, "chunks": 2, "totalBytes": 9}
        response = self.client.post(self.base + "uploads/", oversized_payload, format="json")
        self.assertEqual(response.status_code, 201)
        oversized_id = response.data["id"]
        with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=1):
            response = self.client.put(f"{self.base}{task_id}/chunks/0/", b"12345678", content_type="application/octet-stream")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(Path(transfers.task_path(task_id, ".chunk.0")).read_bytes(), b"12345678")

            response = self.client.put(f"{self.base}{oversized_id}/chunks/0/", b"123456789", content_type="application/octet-stream")
            self.assertEqual(response.status_code, 400)
            self.assertFalse(Path(transfers.task_path(oversized_id, ".chunk.0")).exists())
            self.assertFalse(Path(transfers.task_path(oversized_id, ".chunk.0.tmp")).exists())

    def test_export_normalizes_format_and_database_type(self):
        self.asset.db_type = "MySQL"
        self.asset.save(update_fields=["db_type"])
        data = {"assetId": self.asset.pk, "direction": "EXPORT", "scope": "DATABASE", "format": ".SQL", "database": "test"}
        self.assertEqual(self.client.post(self.base, data, format="json").status_code, 202)

    def test_multi_format_exports_are_versioned_and_preserve_sql_options(self):
        self.asset.db_type = "sqlite"
        self.asset.save(update_fields=["db_type"])
        payload = {"assetId": self.asset.pk, "direction": "export", "scope": "database", "database": "test",
                   "tables": ["sample"], "format": "csv", "exportVersion": 2}
        response = self.client.post(self.base, payload, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["sourceName"], "database-export.zip")
        self.assertEqual(response.data["format"], "csv")
        task = DatabaseTransferTask.objects.get(pk=response.data["id"])
        self.assertEqual(task.parameters["exportVersion"], 2)
        self.assertEqual(task.parameters["tables"], ["sample"])
        invalid = self.client.post(self.base, {**payload, "options": {"upsert": "yes"}}, format="json")
        self.assertEqual(invalid.status_code, 400)

    def test_multi_format_sql_remains_mysql_only(self):
        self.asset.db_type = "sqlite"
        self.asset.save(update_fields=["db_type"])
        payload = {"assetId": self.asset.pk, "direction": "export", "scope": "database", "database": "test",
                   "tables": ["sample"], "format": "sql", "exportVersion": 2}
        self.assertEqual(self.client.post(self.base, payload, format="json").status_code, 400)

    def test_connection_export_does_not_require_asset(self):
        response = self.client.post(self.base, {"direction": "export", "scope": "connections", "format": "json"}, format="json")
        self.assertEqual(response.status_code, 202)

    def test_upload_inspection_confirmation_and_worker_claim(self):
        sql = b"INSERT INTO sample (id) VALUES (1);"
        count = (len(sql) + 7) // 8
        response = self.client.post(self.base + "uploads/", {"assetId": self.asset.pk, "scope": "table", "format": "sql", "objectName": "sample", "fileName": "sample.sql", "chunks": count, "totalBytes": len(sql)}, format="json")
        self.assertEqual(response.status_code, 201)
        task_id = response.data["id"]
        for index in range(count):
            chunk = sql[index * 8:(index + 1) * 8]
            self.assertEqual(self.client.put(f"{self.base}{task_id}/chunks/{index}/", chunk, content_type="application/octet-stream").status_code, 200)
        response = self.client.post(f"{self.base}{task_id}/complete/", {"chunks": count}, format="json")
        self.assertEqual(response.status_code, 202)
        task = transfers.claim_one()
        self.assertEqual(task.stage, "inspection_running")
        self.assertEqual(task.processed_bytes, 0)
        self.assertEqual(task.progress, 0)
        self.assertIsNone(transfers.claim_one())
        with patch.object(transfers, "inspect_input", return_value={"requiresExplicitConfirmation": True, "objects": [{"name": "sample", "hasStructure": False}]}):
            transfers.run_task(task)
        task.refresh_from_db()
        self.assertEqual(task.progress, 100)
        self.assertEqual(self.client.post(f"{self.base}{task_id}/confirm/", {"conflictPolicy": "overwrite"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"{self.base}{task_id}/confirm/", {"conflictPolicy": "append", "confirmed": True}, format="json").status_code, 202)

    def test_legacy_pending_tasks_fail_without_deleting_history(self):
        task = transfers.create_task(self.user, asset=self.asset, scope="database", format="zip", direction="export", status="awaiting_confirmation")
        transfers.claim_one(); task.refresh_from_db()
        self.assertEqual(task.status, "failed")
        self.assertIn("重新提交", task.error)
        self.assertTrue(DatabaseTransferTask.objects.filter(pk=task.pk).exists())
