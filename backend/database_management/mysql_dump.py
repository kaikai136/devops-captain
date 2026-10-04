"""Restricted, streaming MySQL table dumps; never execute arbitrary uploaded SQL."""

import io
import json
import math
import re
import shutil
import tempfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import sqlparse
from django.conf import settings
from django.utils import timezone

from . import adapters


class DumpError(ValueError):
    pass


IDENTIFIER = re.compile(r"^[\w$]+$", re.UNICODE)
TOKEN = re.compile(
    r"\s+|'(?:\\.|''|[^'\\])*'|\"(?:\\.|\"\"|[^\"\\])*\"|`(?:``|[^`])*`"
    r"|0[xX][0-9a-fA-F]+|[bB]'[01]+'|[xX]'[0-9a-fA-F]*'"
    r"|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[\w$]+|[(),.=+*/%-]",
    re.UNICODE,
)


def quote(name):
    if not name or len(name) > 64 or any(char in name for char in "\x00\r\n./\\"):
        raise DumpError("标识符为空、过长或包含不支持的字符")
    return "`" + name.replace("`", "``") + "`"


def identifier(token):
    if token.startswith("`"):
        name = token[1:-1].replace("``", "`")
    elif IDENTIFIER.fullmatch(token):
        name = token
    else:
        raise DumpError("表名或字段名格式不正确")
    quote(name)
    return name


def tokens(sql):
    result, end = [], 0
    for match in TOKEN.finditer(sql):
        if match.start() != end:
            raise DumpError("SQL 包含不支持的语法")
        end = match.end()
        if not match.group().isspace():
            result.append(match.group())
    if end != len(sql):
        raise DumpError("SQL 包含不支持的语法")
    return result


def statements(source, limit=None):
    """Two-character lookahead survives read boundaries, including comments and escapes."""
    limit = limit or getattr(settings, "DATABASE_TRANSFER_MAX_SQL_STATEMENT_BYTES", 64 * 1024 * 1024)
    chars = (char for chunk in iter(lambda: source.read(65536), "") for char in chunk)
    char = next(chars, "")
    following = next(chars, "")
    buffer, size, quoted, comment = io.StringIO(), 0, None, None

    def append(value):
        nonlocal size
        size += len(value.encode("utf-8"))
        if size > limit:
            raise DumpError("单条 SQL 超过内存保护限制，请拆分 INSERT")
        buffer.write(value)

    while char:
        consume = 1
        if comment == "line":
            if char in "\r\n":
                comment = None
                append(" ")
        elif comment == "block":
            if char == "*" and following == "/":
                comment, consume = None, 2
                append(" ")
        elif quoted:
            append(char)
            if char == "\\" and quoted != "`":
                if not following:
                    raise DumpError("字符串转义不完整")
                append(following)
                consume = 2
            elif char == quoted:
                if following == quoted:
                    append(following)
                    consume = 2
                else:
                    quoted = None
        elif char in "'\"`":
            quoted = char
            append(char)
        elif char == "#":
            comment = "line"
        elif char == "-" and following == "-":
            comment, consume = "line", 2
        elif char == "/" and following == "*":
            # Executable version comments must not silently disappear.
            third = next(chars, "")
            if third in {"!", "M"}:
                raise DumpError("不支持可执行版本注释")
            comment = "block"
            char, following = third, next(chars, "")
            continue
        elif char == ";":
            sql = buffer.getvalue().strip()
            if sql:
                yield sql
            buffer, size = io.StringIO(), 0
        else:
            append(char)
        if consume == 2:
            char, following = next(chars, ""), next(chars, "")
        else:
            char, following = following, next(chars, "")
    if quoted or comment == "block":
        raise DumpError("SQL 字符串或注释未闭合")
    sql = buffer.getvalue().strip()
    if sql:
        yield sql


def string_value(token):
    delimiter = token[0]
    text, index, result = token[1:-1], 0, []
    escapes = {"0": "\x00", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a"}
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 1
            if index >= len(text):
                raise DumpError("字符串转义不完整")
            escaped = text[index]
            result.append(escapes.get(escaped, "\\" + escaped if escaped in {"%", "_"} else escaped))
        elif char == delimiter and index + 1 < len(text) and text[index + 1] == delimiter:
            result.append(char)
            index += 1
        else:
            result.append(char)
        index += 1
    return "".join(result)


def literal(token):
    if token.upper() == "NULL":
        return None
    if token[0] in "'\"":
        return string_value(token)
    if token.lower().startswith("0x"):
        value = token[2:]
        return bytes.fromhex(value if len(value) % 2 == 0 else "0" + value)
    if token.lower().startswith("x'"):
        return bytes.fromhex(token[2:-1])
    if token.lower().startswith("b'"):
        return int(token[2:-1], 2)
    if re.fullmatch(r"[+-]?\d+", token):
        return int(token)
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", token):
        return Decimal(token)
    raise DumpError("INSERT 仅支持常量，不支持表达式、函数或子查询")


def parse_statement(sql):
    parts = tokens(sql)
    upper = [part.upper() for part in parts]
    if not parts:
        raise DumpError("空 SQL")
    if upper[:2] == ["SET", "NAMES"]:
        if len(parts) != 3 or parts[2].strip("'\"").lower() not in {"utf8", "utf8mb4"}:
            raise DumpError("仅支持 UTF-8 字符集")
        return {"kind": "setting"}
    if upper[:1] == ["SET"]:
        if len(parts) == 4 and upper[1:3] == ["SQL_MODE", "="] and parts[3] == "'NO_AUTO_VALUE_ON_ZERO'":
            return {"kind": "setting"}
        if upper[1:] not in (["FOREIGN_KEY_CHECKS", "=", "0"], ["FOREIGN_KEY_CHECKS", "=", "1"]):
            raise DumpError("不支持此 SET 语句")
        return {"kind": "setting"}
    if upper[:4] == ["DROP", "TABLE", "IF", "EXISTS"] and len(parts) == 5:
        return {"kind": "drop", "name": identifier(parts[4])}
    if upper[:2] == ["CREATE", "TABLE"]:
        if len(parts) < 6 or parts[3] != "(":
            raise DumpError("仅支持不带数据库限定名的 CREATE TABLE")
        name = identifier(parts[2])
        # Use the existing lexer to distinguish identifiers/strings from executable words.
        forbidden = {"SELECT", "OUTFILE", "INFILE", "DIRECTORY", "TABLESPACE", "CONNECTION", "UNION",
                     "LOAD_FILE", "SLEEP", "BENCHMARK", "GET_LOCK", "RELEASE_LOCK", "SERVER", "PARTITION"}
        for kind, value in sqlparse.lexer.tokenize(sql):
            if kind in sqlparse.tokens.Literal.String or value.startswith("`"):
                continue
            if value.upper() in forbidden or value == ".":
                raise DumpError("CREATE TABLE 含不支持的外部资源、跨库引用或语法")
        depth, end, columns, segment = 0, None, [], []
        for index, part in enumerate(parts[3:], 3):
            if part == "(":
                depth += 1
            elif part == ")":
                depth -= 1
                if depth == 0:
                    if segment: columns.append(segment)
                    end = index
                    break
            if depth == 1 and part == ",":
                columns.append(segment); segment = []
            elif index > 3:
                segment.append(part)
        if end is None:
            raise DumpError("CREATE TABLE 括号不完整")
        names = []
        for column in columns:
            # Defaults, generated expressions and checks may call only known pure built-ins.
            expression = False
            safe_functions = {"CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME", "NOW", "LOCALTIME", "LOCALTIMESTAMP",
                              "CAST", "CONVERT", "ABS", "ROUND", "CEIL", "CEILING", "FLOOR", "MOD", "COALESCE", "IFNULL",
                              "NULLIF", "IF", "CONCAT", "CONCAT_WS", "LOWER", "UPPER", "LENGTH", "CHAR_LENGTH", "SUBSTRING",
                              "TRIM", "REPLACE", "JSON_EXTRACT", "JSON_UNQUOTE", "JSON_VALID", "JSON_OBJECT", "JSON_ARRAY",
                              "YEAR", "MONTH", "DAY", "DATE", "CHECK", "IN", "AS", "DEFAULT"}
            for offset, part in enumerate(column):
                if part.upper() in {"DEFAULT", "AS", "CHECK"}: expression = True
                if expression and offset + 1 < len(column) and column[offset + 1] == "(" and (part.startswith("`") or IDENTIFIER.fullmatch(part)):
                    if part.upper() not in safe_functions:
                        raise DumpError("表表达式含不支持的函数")
            if column and column[0].upper() not in {"PRIMARY", "KEY", "INDEX", "UNIQUE", "CONSTRAINT", "FOREIGN", "CHECK", "FULLTEXT", "SPATIAL"}:
                names.append(identifier(column[0]))
        if not names or len(set(names)) != len(names):
            raise DumpError("CREATE TABLE 字段为空或重复")
        allowed_options = {"ENGINE", "AUTO_INCREMENT", "DEFAULT", "CHARSET", "CHARACTER", "SET", "COLLATE", "COMMENT",
                           "ROW_FORMAT", "KEY_BLOCK_SIZE", "STATS_PERSISTENT", "STATS_AUTO_RECALC", "STATS_SAMPLE_PAGES",
                           "PACK_KEYS", "CHECKSUM", "DELAY_KEY_WRITE", "COMPRESSION", "ENCRYPTION"}
        tail = parts[end + 1:]
        index = 0
        while index < len(tail):
            key = tail[index].upper(); index += 1
            if key not in allowed_options:
                raise DumpError("不支持此表选项")
            if key == "DEFAULT":
                continue
            if key == "CHARACTER":
                if index >= len(tail) or tail[index].upper() != "SET": raise DumpError("表字符集格式错误")
                index += 1
            if index < len(tail) and tail[index] == "=": index += 1
            if index >= len(tail): raise DumpError("表选项缺少值")
            value = tail[index].strip("'\"")
            if key == "ENGINE" and value.lower() not in {"innodb", "myisam", "memory"}:
                raise DumpError("仅支持 InnoDB、MyISAM、MEMORY 表引擎")
            index += 1
        return {"kind": "create", "name": name, "ddl": sql, "columns": names}
    if upper[:2] != ["INSERT", "INTO"] or len(parts) < 6:
        raise DumpError("仅支持表结构及 INSERT VALUES 转储，不支持任意 SQL")
    name, index, columns = identifier(parts[2]), 3, None
    if parts[index] == "(":
        columns, index = [], index + 1
        while index < len(parts):
            columns.append(identifier(parts[index])); index += 1
            if index < len(parts) and parts[index] == ")": index += 1; break
            if index >= len(parts) or parts[index] != ",": raise DumpError("INSERT 字段列表格式错误")
            index += 1
        if not columns or len(set(columns)) != len(columns): raise DumpError("INSERT 字段为空或重复")
    if index >= len(parts) or upper[index] != "VALUES": raise DumpError("仅支持 INSERT VALUES")
    index += 1
    rows = []
    while index < len(parts):
        if parts[index] != "(": raise DumpError("INSERT 行格式错误")
        index += 1
        row = []
        while index < len(parts):
            row.append(literal(parts[index])); index += 1
            if index < len(parts) and parts[index] == ")": index += 1; break
            if index >= len(parts) or parts[index] != ",": raise DumpError("INSERT 常量列表格式错误")
            index += 1
        else:
            raise DumpError("INSERT 行未闭合")
        if columns is not None and len(row) != len(columns): raise DumpError("INSERT 值数量与字段不一致")
        if rows and len(row) != len(rows[0]): raise DumpError("INSERT 行宽度不一致")
        rows.append(row)
        if index == len(parts): break
        if parts[index] != "," or index + 1 == len(parts): raise DumpError("INSERT 包含不支持的后缀")
        index += 1
    if not rows: raise DumpError("INSERT 没有数据")
    return {"kind": "insert", "name": name, "columns": columns, "rows": rows}


def query(conn, sql, params=()):
    with conn.cursor() as cursor:
        cursor.execute(sql, params or None)
        return cursor.fetchall() if cursor.description else []


def table_metadata(conn, database):
    return {row["TABLE_NAME"]: row for row in query(conn,
        "SELECT TABLE_NAME, ENGINE FROM information_schema.tables WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME", (database,))}


def table_columns(conn, database, table):
    return query(conn, "SELECT COLUMN_NAME, EXTRA FROM information_schema.columns WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION", (database, table))


def generated_column(extra):
    return bool(re.search(r"\b(?:VIRTUAL|STORED) GENERATED\b", str(extra).upper()))


def scan_dump(task, spool=None, heartbeat=None):
    definitions, drops, details = {}, set(), {}
    indices = {}
    statement_count = 0
    with Path(task.input_path).open("r", encoding="utf-8-sig") as source:
        for sql in statements(source):
            item = parse_statement(sql)
            statement_count += 1
            if heartbeat and statement_count % max(1, settings.DATABASE_TRANSFER_BATCH_ROWS) == 0: heartbeat()
            if item["kind"] == "setting": continue
            name = item["name"]
            if name not in indices: indices[name] = len(indices)
            detail = details.setdefault(name, {"name": name, "hasStructure": False, "rows": 0, "hasDrop": False, "fields": [], "implicitWidths": []})
            if item["kind"] == "create":
                if name in definitions: raise DumpError("文件包含重复的表定义")
                definitions[name] = item
                detail["hasStructure"] = True
            elif item["kind"] == "drop":
                drops.add(name); detail["hasDrop"] = True
            else:
                detail["rows"] += len(item["rows"])
                if item["columns"]:
                    detail["fields"] = sorted(set(detail["fields"]) | set(item["columns"]))
                elif len(item["rows"][0]) not in detail["implicitWidths"]:
                    detail["implicitWidths"].append(len(item["rows"][0]))
                if spool:
                    if shutil.disk_usage(spool).free < settings.DATABASE_TRANSFER_MIN_FREE_BYTES:
                        raise DumpError("服务器临时磁盘空间不足")
                    path = spool / f"{indices[name]}.jsonl"
                    with path.open("a", encoding="utf-8") as output:
                        output.write(json.dumps(sql, ensure_ascii=False) + "\n")
    if heartbeat: heartbeat()
    if not details: raise DumpError("文件不包含表结构或数据")
    if drops - definitions.keys(): raise DumpError("DROP TABLE 必须有对应的 CREATE TABLE 定义")
    if task.scope == "table" and (len(details) != 1 or task.object_name not in details):
        raise DumpError("表导入必须只包含与当前表同名的对象；多表文件请从数据库入口导入")
    max_tables = settings.DATABASE_TRANSFER_MAX_TABLES
    max_rows = settings.DATABASE_TRANSFER_MAX_ROWS
    if max_tables and len(details) > max_tables: raise DumpError("表数量超过系统配置上限")
    if max_rows and sum(item["rows"] for item in details.values()) > max_rows: raise DumpError("行数超过系统配置上限")
    return definitions, list(details.values())


def inspect_dump(task, heartbeat=None):
    definitions, details = scan_dump(task, heartbeat=heartbeat)
    with Path(task.input_path).open("r", encoding="utf-8-sig") as source:
        header = source.read(16384)
    initial_comment = re.match(r"\s*/\*(.*?)\*/", header, re.S)
    header = initial_comment.group(1) if initial_comment else ""
    source_type = re.search(r"Source Server Type:\s*([^\r\n]+)", header, re.I)
    source_version = re.search(r"(?:Source )?Server Version:\s*([^\r\n]+)", header, re.I)
    source_type = source_type.group(1).strip() if source_type else ""
    source_version = source_version.group(1).strip() if source_version else ""
    if source_type and source_type.lower() not in {"mysql", "mariadb"}:
        raise DumpError("不支持跨数据库类型导入")
    with adapters.connection(task.asset, task.database) as conn:
        existing = table_metadata(conn, task.database)
        version = query(conn, "SELECT VERSION() AS version")[0]["version"]
        collations = {row["Collation"] for row in query(conn, "SHOW COLLATION")}
        for item in details:
            item["exists"] = item["name"] in existing
            definition = definitions.get(item["name"])
            if not item["exists"] and not definition: raise DumpError("仅数据导入要求目标表已存在")
            target_columns = table_columns(conn, task.database, item["name"]) if item["exists"] else []
            available = [row["COLUMN_NAME"] for row in target_columns] if target_columns else definition["columns"]
            generated = {row["COLUMN_NAME"] for row in target_columns if generated_column(row["EXTRA"])}
            item["appendCompatible"] = not (set(item["fields"]) - set(available) or set(item["fields"]) & generated)
            widths = item["implicitWidths"]
            implicit_fields = definition["columns"] if definition else available
            if widths and (any(width != len(implicit_fields) for width in widths) or set(implicit_fields) - set(available) or set(implicit_fields) & generated):
                item["appendCompatible"] = False
    warnings = []
    if source_version and source_version != str(version): warnings.append("源库和目标库版本不同，请检查字段类型及排序规则兼容性")
    for item in details:
        if not item["appendCompatible"]: warnings.append(f"{item['name']} 的字段与目标结构不兼容，不能追加；请检查结构或选择覆盖/跳过")
        if item["exists"] and str(existing[item["name"]]["ENGINE"]).lower() != "innodb":
            warnings.append(f"{item['name']} 非事务表，失败或取消可能留下部分数据，重试前请核对")
    for definition in definitions.values():
        for collation in re.findall(r"\bCOLLATE\s*=?\s*(\w+)", definition["ddl"], re.I):
            if collation not in collations:
                warnings.append(f"目标不支持排序规则 {collation}，创建该表会失败")
    if any(item["hasDrop"] for item in details): warnings.append("文件包含 DROP TABLE；只在选择覆盖并确认后重建目标表")
    warnings.append("覆盖表结构涉及 MySQL DDL，无法保证事务回滚；不同版本的字段或排序规则可能不兼容")
    return {"tables": len(details), "objects": details, "rows": sum(item["rows"] for item in details),
            "databaseType": task.asset.db_type, "sourceVersion": source_version, "targetVersion": str(version), "warnings": warnings,
            "requiresExplicitConfirmation": True, "fileBytes": Path(task.input_path).stat().st_size, "format": "sql"}


def sql_literal(value):
    if value is None: return "NULL"
    if isinstance(value, (bytes, bytearray, memoryview)): return "X'" + bytes(value).hex() + "'"
    if isinstance(value, bool): return "1" if value else "0"
    if isinstance(value, Decimal) and not value.is_finite(): raise DumpError("无法导出非有限小数")
    if isinstance(value, (int, Decimal)): return str(value)
    if isinstance(value, float):
        if not math.isfinite(value): raise DumpError("无法导出非有限浮点数")
        return repr(value)
    if isinstance(value, timedelta):
        seconds = value.days * 86400 + value.seconds
        sign = "-" if value < timedelta(0) else ""
        absolute = abs(value)
        micros = (absolute.days * 86400 + absolute.seconds) * 1000000 + absolute.microseconds
        seconds, fraction = divmod(micros, 1000000)
        value = f"{sign}{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}.{fraction:06}"
    elif isinstance(value, (date, datetime, time)): value = value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    elif isinstance(value, (dict, list)): value = json.dumps(value, ensure_ascii=False)
    elif not isinstance(value, str): raise DumpError("数据库返回了不支持的数据类型")
    escapes = {"\\": "\\\\", "'": "\\'", "\x00": "\\0", "\n": "\\n", "\r": "\\r", "\x1a": "\\Z"}
    return "'" + "".join(escapes.get(char, char) for char in value) + "'"


def resource_guard(task, output_bytes=0):
    if shutil.disk_usage(Path(task.input_path or task.output_path).parent).free < settings.DATABASE_TRANSFER_MIN_FREE_BYTES:
        raise DumpError("服务器临时磁盘空间不足")
    if task.started_at and (timezone.now() - task.started_at).total_seconds() > settings.DATABASE_TRANSFER_TASK_TIMEOUT_SECONDS:
        raise DumpError("任务超过执行超时时间")
    if settings.DATABASE_TRANSFER_MAX_RESULT_BYTES and output_bytes > settings.DATABASE_TRANSFER_MAX_RESULT_BYTES:
        raise DumpError("结果超过系统配置上限")


def export_dump(task, output, report):
    from pymysql.cursors import SSCursor
    total, batch_size = 0, max(1, settings.DATABASE_TRANSFER_BATCH_ROWS)
    content = task.parameters.get("content", "structure_data")
    with adapters.connection(task.asset, task.database) as conn:
        metadata = table_metadata(conn, task.database)
        names = task.parameters.get("tables") or sorted(metadata)
        if not names or any(name not in metadata for name in names): raise DumpError("导出目标表不存在或范围为空")
        if settings.DATABASE_TRANSFER_MAX_TABLES and len(names) > settings.DATABASE_TRANSFER_MAX_TABLES: raise DumpError("表数量超过系统配置上限")
        warnings = [f"{name} 非 InnoDB 表，无法保证数据快照一致性" for name in names if str(metadata[name]["ENGINE"]).lower() != "innodb"]
        from .transfers import update
        update(task, preview={"warnings": warnings, "tables": len(names), "content": content})
        query(conn, "SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'")
        query(conn, "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        query(conn, "START TRANSACTION WITH CONSISTENT SNAPSHOT")
        version = query(conn, "SELECT VERSION() AS version")[0]["version"]
        output.write(f"/* DevOps Captain Dump SQL\n Source Server Type: {task.asset.db_type}\n Server Version: {str(version).replace('*/', '')}\n Date: {timezone.now().isoformat()}\n File Encoding: UTF-8\n*/\n\nSET NAMES utf8mb4;\nSET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';\nSET FOREIGN_KEY_CHECKS = 0;\n\n")
        for index, name in enumerate(names):
            from .transfers import require_task_permissions
            if not require_task_permissions(task.owner, task): raise PermissionError("任务所需权限已被撤销")
            resource_guard(task, output.tell())
            report(task, stage=f"exporting_table:{name}", rows=total)
            if content != "data":
                ddl = query(conn, f"SHOW CREATE TABLE {quote(name)}")[0]["Create Table"]
                output.write(f"-- ----------------------------\n-- Table structure for {name}\n-- ----------------------------\nDROP TABLE IF EXISTS {quote(name)};\n{ddl.rstrip(';')};\n\n")
            if content != "structure":
                fields = [row["COLUMN_NAME"] for row in table_columns(conn, task.database, name) if not generated_column(row["EXTRA"])]
                if not fields: raise DumpError("表没有可导出数据的非生成字段")
                columns = ", ".join(quote(field) for field in fields)
                output.write(f"-- ----------------------------\n-- Records of {name}\n-- ----------------------------\n")
                with conn.cursor(SSCursor) as cursor:
                    cursor.execute(f"SELECT {columns} FROM {quote(name)}")
                    while True:
                        rows = cursor.fetchmany(batch_size)
                        if not rows: break
                        for row in rows:
                            output.write(f"INSERT INTO {quote(name)} ({columns}) VALUES ({', '.join(sql_literal(value) for value in row)});\n")
                        total += len(rows)
                        if not require_task_permissions(task.owner, task): raise PermissionError("任务所需权限已被撤销")
                        if settings.DATABASE_TRANSFER_MAX_ROWS and total > settings.DATABASE_TRANSFER_MAX_ROWS: raise DumpError("行数超过系统配置上限")
                        output.flush(); resource_guard(task, output.tell())
                        report(task, stage=f"exporting_table:{name}", rows=total, byte_count=output.tell())
                output.write("\n")
            from .transfers import update
            update(task, progress=min(99, int((index + 1) * 100 / len(names))))
        conn.rollback()
        output.write("SET FOREIGN_KEY_CHECKS = 1;\n")
        output.flush()
        resource_guard(task, output.tell())


def import_dump(task, report):
    from .transfers import require_task_permissions, update
    batch_size = max(1, settings.DATABASE_TRANSFER_BATCH_ROWS)
    with tempfile.TemporaryDirectory(prefix=f"{task.pk}-", dir=Path(task.input_path).parent) as folder:
        def heartbeat():
            resource_guard(task); report(task, stage="validating_sql")
        definitions, details = scan_dump(task, Path(folder), heartbeat)
        if not require_task_permissions(task.owner, task): raise PermissionError("任务所需权限已被撤销")
        completed = set(task.checkpoints.get("completedTables", []))
        done_rows = task.processed_rows
        total_rows = sum(item["rows"] for item in details)
        with adapters.connection(task.asset, task.database) as conn:
            original_fk = query(conn, "SELECT @@FOREIGN_KEY_CHECKS AS value")[0]["value"]
            query(conn, "SET SESSION sql_mode='STRICT_ALL_TABLES,NO_AUTO_VALUE_ON_ZERO'")
            try:
                query(conn, "SET FOREIGN_KEY_CHECKS=0")
                existing = table_metadata(conn, task.database)
                for index, detail in enumerate(details):
                    if not require_task_permissions(task.owner, task): raise PermissionError("任务所需权限已被撤销")
                    name = detail["name"]
                    if name in completed: continue
                    report(task, stage=f"importing_table:{name}", rows=done_rows, total=total_rows)
                    resource_guard(task)
                    definition, exists = definitions.get(name), name in existing
                    if task.conflict_policy == "skip" and exists:
                        completed.add(name)
                        update(task, checkpoints={**task.checkpoints, "completedTables": sorted(completed)})
                        continue
                    if not exists and not definition: raise DumpError("目标表不存在且文件不包含结构")
                    try:
                        if task.conflict_policy == "overwrite" and definition and exists:
                            update(task, checkpoints={**task.checkpoints, "currentTable": name, "ddlMayBeCommitted": True})
                            query(conn, f"DROP TABLE {quote(name)}")
                            exists = False
                        if not exists:
                            update(task, checkpoints={**task.checkpoints, "currentTable": name, "ddlMayBeCommitted": True})
                            query(conn, definition["ddl"])
                            existing[name] = {}
                        columns = table_columns(conn, task.database, name)
                        all_fields = [row["COLUMN_NAME"] for row in columns]
                        generated = {row["COLUMN_NAME"] for row in columns if generated_column(row["EXTRA"])}
                        if task.conflict_policy == "overwrite" and exists and not definition:
                            query(conn, f"DELETE FROM {quote(name)}")
                        count, data_path = 0, Path(folder) / f"{index}.jsonl"
                        if data_path.exists():
                            with data_path.open(encoding="utf-8") as source:
                                for line in source:
                                    item = parse_statement(json.loads(line))
                                    fields = item["columns"] or (definition["columns"] if definition else all_fields)
                                    if any(field not in all_fields or field in generated for field in fields): raise DumpError("INSERT 字段与目标结构不兼容")
                                    if len(fields) != len(item["rows"][0]): raise DumpError("INSERT 值数量与目标结构不兼容")
                                    sql = f"INSERT INTO {quote(name)} ({', '.join(quote(field) for field in fields)}) VALUES ({', '.join(['%s'] * len(fields))})"
                                    for offset in range(0, len(item["rows"]), batch_size):
                                        if not require_task_permissions(task.owner, task): raise PermissionError("任务所需权限已被撤销")
                                        batch = item["rows"][offset:offset + batch_size]
                                        with conn.cursor() as cursor: cursor.executemany(sql, batch)
                                        count += len(batch)
                                        report(task, stage=f"importing_table:{name}", rows=done_rows + count, total=total_rows)
                                        resource_guard(task)
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        update(task, processed_rows=done_rows)
                        raise
                    done_rows += count
                    completed.add(name)
                    update(task, processed_rows=done_rows, checkpoints={"completedTables": sorted(completed), "currentTable": "", "ddlMayBeCommitted": False})
            finally:
                conn.rollback()
                query(conn, "SET FOREIGN_KEY_CHECKS=%s", (original_fk,))
