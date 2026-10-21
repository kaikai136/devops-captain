import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from . import table_imports
from .mysql_dump import DumpError


class TableImportFormatTests(SimpleTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "input.csv"
        self.task = SimpleNamespace(input_path=str(self.path), format="csv", object_name="sample", parameters={})

    def write_csv(self, content, format="csv"):
        self.task.format = format
        self.path.write_text(content, encoding="utf-8")

    def test_csv_and_txt_read_headered_rows(self):
        self.write_csv('id,name\r\n1,"中文,值"\r\n')
        self.assertEqual(list(table_imports.read_rows(self.task)), [["id", "name"], ["1", "中文,值"]])

        self.write_csv("id\tname\n2\trow\n", "txt")
        self.assertEqual(list(table_imports.read_rows(self.task)), [["id", "name"], ["2", "row"]])

    def test_json_accepts_object_arrays_and_current_table_envelopes(self):
        for payload in [
            [{"id": 1, "name": "first"}],
            {"sample": [{"id": 1, "name": "first"}]},
        ]:
            with self.subTest(payload=payload):
                self.task.format = "json"
                self.path.write_text(json.dumps(payload), encoding="utf-8")
                self.assertEqual(list(table_imports.read_rows(self.task)), [["id", "name"], [1, "first"]])

    def test_json_rejects_other_tables_and_inconsistent_rows(self):
        for payload in [{"other": [{"id": 1}]}, [{"id": 1}, {"name": "missing id"}]]:
            with self.subTest(payload=payload), self.assertRaises(DumpError):
                self.task.format = "json"
                self.path.write_text(json.dumps(payload), encoding="utf-8")
                list(table_imports.read_rows(self.task))

    def test_excel_reads_only_first_sheet_and_rejects_invalid_archives(self):
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active.append(["id", "name"])
        workbook.active.append([1, "first"])
        workbook.create_sheet("ignored").append(["id", "other"])
        workbook.save(self.path)
        workbook.close()
        self.task.format = "xlsx"
        self.assertEqual(list(table_imports.read_rows(self.task)), [["id", "name"], [1, "first"]])

        self.path.write_text("not an Excel archive", encoding="utf-8")
        with self.assertRaisesMessage(DumpError, "Excel 文件格式无效"):
            list(table_imports.read_rows(self.task))

    def test_field_mapping_rejects_duplicates_generated_and_missing_required_fields(self):
        columns = [
            {"name": "id", "nullable": "NO", "default": None, "extra": "auto_increment", "type": "int"},
            {"name": "name", "nullable": "NO", "default": None, "extra": "", "type": "varchar(8)"},
            {"name": "calc", "nullable": "YES", "default": None, "extra": "VIRTUAL GENERATED", "type": "int"},
        ]
        with self.assertRaisesMessage(DumpError, "多个来源字段"):
            table_imports.mapping_for(["first", "second"], columns, {"first": "name", "second": "name"})
        with self.assertRaisesMessage(DumpError, "必填字段"):
            table_imports.mapping_for(["id"], columns, {})
        with self.assertRaisesMessage(DumpError, "生成字段"):
            table_imports.mapping_for(["calc"], columns, {})

    def test_row_validation_checks_numeric_ranges_dates_and_text_lengths(self):
        integer = {"name": "id", "type": "tinyint unsigned", "nullable": "NO", "extra": ""}
        self.assertEqual(table_imports.typed_value("255", integer), 255)
        with self.assertRaises(ValueError):
            table_imports.typed_value("256", integer)
        with self.assertRaises(ValueError):
            table_imports.typed_value("not-a-date", {"name": "created", "type": "date", "nullable": "YES"})
        with self.assertRaises(ValueError):
            table_imports.typed_value("too long", {"name": "name", "type": "varchar(3)", "nullable": "YES"})

    def test_preview_reports_mapping_or_row_errors_without_accepting_the_import(self):
        self.write_csv("id,name\n1,ok\n2,too-long\n")
        columns = [
            {"name": "id", "type": "int", "nullable": "NO", "default": None, "extra": "auto_increment"},
            {"name": "name", "type": "varchar(3)", "nullable": "NO", "default": None, "extra": ""},
        ]
        with patch.object(table_imports, "target_columns", return_value=columns):
            preview = table_imports.inspect_rows(self.task, lambda *args, **kwargs: None, strict=False)
        self.assertEqual(preview["rows"], 2)
        self.assertIn("第 3 行", preview["validationError"])
        with patch.object(table_imports, "target_columns", return_value=columns):
            with self.assertRaisesMessage(DumpError, "第 3 行"):
                table_imports.inspect_rows(self.task, lambda *args, **kwargs: None)


class TableImportExecutionTests(SimpleTestCase):
    def test_skip_policy_only_skips_duplicate_keys_and_rolls_back_other_integrity_errors(self):
        task = SimpleNamespace(
            parameters={}, object_name="sample", asset=SimpleNamespace(db_type="mysql"),
            database="tele", conflict_policy="skip",
        )
        columns = [{"name": "id", "type": "int", "nullable": "NO", "default": None, "extra": ""}]
        for code in (1062, 1452):
            with self.subTest(code=code):
                conn = MagicMock()

                def run(_connection, sql, _params=(), **_kwargs):
                    if sql.startswith("INSERT"):
                        self.assertNotIn("IGNORE", sql)
                        raise RuntimeError(code, "write error")
                    return [], 0

                with patch.object(table_imports, "inspect_rows", return_value={"rows": 1}), \
                     patch.object(table_imports, "target_columns", return_value=columns), \
                     patch.object(table_imports, "read_rows", return_value=iter([["id"], [1]])), \
                     patch.object(table_imports.adapters, "connection") as connection, \
                     patch.object(table_imports.adapters, "run", side_effect=run):
                    connection.return_value.__enter__.return_value = conn
                    if code == 1062:
                        table_imports.import_rows(task, lambda *_args, **_kwargs: None)
                        conn.commit.assert_called_once()
                        conn.rollback.assert_not_called()
                    else:
                        with self.assertRaises(RuntimeError):
                            table_imports.import_rows(task, lambda *_args, **_kwargs: None)
                        conn.rollback.assert_called_once()
                        conn.commit.assert_not_called()

    def test_row_import_uses_transaction_and_rolls_back_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.csv"
            path.write_text("id,name\n1,first\n2,second\n", encoding="utf-8")
            task = SimpleNamespace(
                input_path=str(path), format="csv", object_name="sample", parameters={"fieldMapping": {}},
                asset=SimpleNamespace(db_type="mysql"), database="tele", schema="", conflict_policy="append",
            )
            columns = [
                {"name": "id", "type": "int", "nullable": "NO", "default": None, "extra": "auto_increment"},
                {"name": "name", "type": "varchar(20)", "nullable": "NO", "default": None, "extra": ""},
            ]
            conn = MagicMock()

            def run(_conn, sql, params=(), **_kwargs):
                if "information_schema.COLUMNS" in sql:
                    return ([{"name": "id", "extra": "auto_increment"}, {"name": "name", "extra": ""}], 2)
                if "information_schema.TABLES" in sql:
                    return ([{"engine": "InnoDB"}], 1)
                return ([], 1)

            with patch.object(table_imports.adapters, "columns", return_value=columns), \
                 patch.object(table_imports.adapters, "connection") as connection, \
                 patch.object(table_imports.adapters, "run", side_effect=run) as execute, \
                 patch.object(table_imports, "resource_guard"):
                connection.return_value.__enter__.return_value = conn
                table_imports.import_rows(task, lambda *args, **kwargs: None)

            statements = [call.args[1] for call in execute.call_args_list]
            self.assertIn("START TRANSACTION", statements)
            self.assertIn("INSERT INTO `sample` (`id`, `name`) VALUES (%s, %s)", statements)
            self.assertEqual(statements.count("INSERT INTO `sample` (`id`, `name`) VALUES (%s, %s)"), 2)
            conn.commit.assert_called_once()
            conn.rollback.assert_not_called()

            conn.reset_mock()
            insert_count = 0

            def fail_on_second_insert(_conn, sql, params=(), **_kwargs):
                nonlocal insert_count
                if sql.startswith("INSERT INTO"):
                    insert_count += 1
                    if insert_count == 2:
                        raise RuntimeError("write failed")
                return run(_conn, sql, params, **_kwargs)

            with patch.object(table_imports.adapters, "columns", return_value=columns), \
                 patch.object(table_imports.adapters, "connection") as connection, \
                 patch.object(table_imports.adapters, "run", side_effect=fail_on_second_insert), \
                 patch.object(table_imports, "resource_guard"), self.assertRaisesRegex(RuntimeError, "write failed"):
                connection.return_value.__enter__.return_value = conn
                table_imports.import_rows(task, lambda *args, **kwargs: None)

            conn.rollback.assert_called_once()
