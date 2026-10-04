import csv
import datetime
import io
import json
import re
import time
from pathlib import Path

import sqlparse
from sqlparse.tokens import Comment, DDL, DML
from django.conf import settings
from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import require_feature_permission
from operations.responses import bad_request, get_object_or_error
from system_management.services import record_operation_log

from . import adapters
from .models import DatabaseAsset


def checked(request, asset_id, action):
    denied = require_feature_permission(request, "databaseManagement", action, "没有应用管理权限")
    if denied:
        return None, denied
    return get_object_or_error(DatabaseAsset, id=asset_id, error_message="数据库资产不存在")


def failed(exc):
    return bad_request(adapters.connection_error(exc))


@api_view(["GET"])
def types_view(request):
    denied = require_feature_permission(request, "databaseManagement", "view")
    return denied or Response({"types": adapters.type_metadata()})


@api_view(["GET"])
def sqlite_files(request):
    denied = require_feature_permission(request, "databaseManagement", "view")
    if denied: return denied
    root = Path(settings.DATABASE_ASSET_SQLITE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    app_database = Path(settings.DATABASES["default"]["NAME"]).resolve()
    return Response({"files": sorted(path.name for path in root.iterdir()
                               if path.is_file() and path.resolve().parent == root.resolve()
                               and path.resolve() != app_database
                               and path.suffix.lower() in {".db", ".sqlite", ".sqlite3"})})


@api_view(["GET"])
def asset_tree(request, asset_id):
    asset, denied = checked(request, asset_id, "view_data")
    if denied: return denied
    try:
        names = adapters.schema_names(asset)
        database = request.query_params.get("database", "")
        return Response({"databases": names, "schemas": adapters.schemas(asset, database) if database else [], "kind": asset.db_type})
    except Exception as exc: return failed(exc)


@api_view(["GET"])
def asset_objects(request, asset_id):
    asset, denied = checked(request, asset_id, "view_data")
    if denied: return denied
    try:
        objects = adapters.object_list(asset, request.query_params.get("database", ""), request.query_params.get("schema"), request.query_params.get("type"))
        capabilities = next((item["capabilities"] for item in adapters.type_metadata() if item["key"] == asset.db_type), [])
        return Response({"objects": [{**item, "capabilities": capabilities} for item in objects]})
    except Exception as exc: return failed(exc)


@api_view(["GET"])
def asset_ddl(request, asset_id):
    asset, denied = checked(request, asset_id, "view_data")
    if denied: return denied
    try:
        ddl = adapters.object_ddl(asset, request.query_params.get("database", ""),
                                  request.query_params.get("table", ""), request.query_params.get("schema"),
                                  request.query_params.get("objectType", "table"), request.query_params.get("signature"))
        return Response({"ddl": ddl})
    except Exception as exc: return failed(exc)


@api_view(["GET"])
def asset_columns_v2(request, asset_id):
    asset, denied = checked(request, asset_id, "view_data")
    if denied: return denied
    try:
        return Response({"columns": adapters.columns(asset, request.query_params.get("database", ""), request.query_params.get("table", ""), request.query_params.get("schema"))})
    except Exception as exc: return failed(exc)


@api_view(["GET"])
def asset_indexes(request, asset_id):
    asset, denied = checked(request, asset_id, "view_data")
    if denied: return denied
    try:
        return Response({"indexes": adapters.indexes(asset, request.query_params.get("database", ""), request.query_params.get("table", ""), request.query_params.get("schema"))})
    except Exception as exc: return failed(exc)


COLUMN_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]*(?:\([0-9]{1,5}(?:\s*,\s*[0-9]{1,5})?\))?$", re.ASCII)


@api_view(["POST"])
def asset_schema(request, asset_id):
    asset, denied = checked(request, asset_id, "manage_schema")
    if denied: return denied
    kind = asset.db_type
    if kind == "redis": return bad_request("Redis 不支持表结构操作")
    action = request.data.get("action")
    try:
        table = adapters.quote(request.data.get("table"), kind)
        schema = request.data.get("schema")
        qualified = f"{adapters.quote(schema, kind)}.{table}" if schema else table
        name = adapters.quote(request.data.get("name"), kind)
        if action == "add_column":
            column_type = str(request.data.get("columnType", "")).strip().upper()
            if not COLUMN_TYPE.fullmatch(column_type) or len(column_type) > 80:
                raise ValueError("字段类型格式不正确")
            clause = f"{name} {column_type}"
            sql = (f"ALTER TABLE {qualified} ADD ({clause})" if kind in {"oracle", "dameng"}
                   else f"ALTER TABLE {qualified} ADD {clause}" if kind == "sqlserver"
                   else f"ALTER TABLE {qualified} ADD COLUMN {clause}")
        elif action == "drop_column":
            sql = f"ALTER TABLE {qualified} DROP COLUMN {name}"
        elif action == "create_index":
            if kind == "clickhouse": raise ValueError("ClickHouse 索引请使用 SQL 编辑器按引擎语法创建")
            fields = request.data.get("columns")
            if not isinstance(fields, list) or not fields or len(fields) > 16:
                raise ValueError("请选择 1 至 16 个索引字段")
            columns = ", ".join(adapters.quote(field, kind) for field in fields)
            unique = "UNIQUE " if request.data.get("unique") else ""
            sql = f"CREATE {unique}INDEX {name} ON {qualified} ({columns})"
        elif action == "drop_index":
            if kind == "clickhouse": raise ValueError("ClickHouse 索引请使用 SQL 编辑器按引擎语法删除")
            if kind == "sqlite" and name.startswith('"sqlite_'):
                raise ValueError("不能删除 SQLite 系统索引")
            sql = (f"DROP INDEX {name} ON {qualified}" if kind in {"mysql", "mariadb", "sqlserver"}
                   else f"DROP INDEX {adapters.quote(schema, kind)}.{name}" if schema and kind in {"postgresql", "kingbase"}
                   else f"DROP INDEX {name}")
        else:
            return bad_request("不支持的结构操作")
        adapters.execute(asset, request.data.get("database"), sql, commit=True)
        record_operation_log(request, "应用管理", "修改表结构", asset.name, f"操作={action}; 表={request.data.get('table')}")
        return Response({"ok": True})
    except Exception as exc: return failed(exc)


@api_view(["GET"])
def asset_data_v2(request, asset_id):
    asset, denied = checked(request, asset_id, "view_data")
    if denied: return denied
    try:
        page = min(max(int(request.query_params.get("page", 1)), 1), 100000)
        size = min(max(int(request.query_params.get("pageSize", 25)), 1), 200)
        fields = [field for field in request.query_params.get("fields", "").split(",") if field]
        return Response(adapters.table_data(asset, request.query_params.get("database", ""), request.query_params.get("table", ""), request.query_params.get("schema"), page, size, request.query_params.get("sort"), request.query_params.get("direction", "asc"), fields, request.query_params.get("whereField"), request.query_params.get("whereValue")))
    except Exception as exc: return failed(exc)


READ_SQL = {"SELECT", "SHOW", "DESCRIBE", "EXPLAIN"}
DDL_SQL = {"CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME"}


def sql_action(sql):
    statements = sqlparse.parse(sql)
    if len(statements) != 1:
        raise ValueError("每次只能执行一条 SQL 语句")
    kind = statements[0].get_type().upper()
    tokens = [token for token in statements[0].flatten()
              if not token.is_whitespace and token.ttype not in Comment]
    first = tokens[0].value.upper() if tokens else ""
    if re.search(r"\bINTO\s+(OUTFILE|DUMPFILE)\b", sql, re.I):
        return "modify_data"
    nested_ddl = any(token.ttype in DDL for token in tokens)
    nested_dml = any(token.ttype in DML and token.value.upper() in {"INSERT", "UPDATE", "DELETE", "MERGE", "REPLACE"}
                     for token in tokens)
    if nested_ddl or re.search(r"^\s*SELECT\b[\s\S]*\bINTO\s+(?!OUTFILE\b|DUMPFILE\b)", sql, re.I):
        return "manage_schema"
    if nested_dml:
        return "modify_data"
    if first in {"PRAGMA", "SET", "USE", "CALL", "EXEC", "EXECUTE"}:
        return "manage_schema"
    if kind in DDL_SQL or first in DDL_SQL:
        return "manage_schema"
    if kind in READ_SQL or first in READ_SQL:
        return "read"
    return "modify_data"


def validate_sql_for_asset(asset, sql):
    if asset.db_type == "sqlite" and re.search(r"\b(?:ATTACH|DETACH)\b|\bVACUUM\s+INTO\b", sql, re.I):
        raise ValueError("SQLite 资产不允许挂载或写入其他数据库文件")


@api_view(["POST"])
def asset_sql(request, asset_id):
    asset, denied = checked(request, asset_id, "execute_sql")
    if denied: return denied
    sql = str(request.data.get("sql", "")).strip()
    if not sql or len(sql) > 100000: return bad_request("SQL 不能为空且最多 100000 字符")
    if asset.db_type == "redis": return bad_request("Redis 请使用命令视图")
    try:
        action = sql_action(sql)
        validate_sql_for_asset(asset, sql)
    except ValueError as exc:
        return bad_request(str(exc))
    if action != "read":
        denied = require_feature_permission(request, "databaseManagement", action)
        if denied: return denied
    start = time.monotonic()
    try:
        result = adapters.execute(asset, request.data.get("database"), sql, commit=True)
        result["elapsedMs"] = round((time.monotonic() - start) * 1000)
        if action != "read":
            record_operation_log(request, "应用管理", "执行 SQL", asset.name,
                                 f"类型={asset.db_type}; 影响行数={result['affected']}")
        return Response(result)
    except Exception as exc: return failed(exc)


def row_statement(asset, payload):
    kind = asset.db_type
    table = adapters.quote(payload.get("table"), kind)
    schema = payload.get("schema")
    target = f"{adapters.quote(schema, kind)}.{table}" if schema else table
    action = payload.get("action")
    values = payload.get("values") or {}
    keys = payload.get("key") or {}
    if not isinstance(values, dict) or not isinstance(keys, dict): raise ValueError("行数据格式不正确")
    if action == "insert" and values:
        fields = list(values)
        columns = ", ".join(adapters.quote(field, kind) for field in fields)
        marks = ", ".join(adapters.marker(kind, index + 1) for index in range(len(fields)))
        return f"INSERT INTO {target} ({columns}) VALUES ({marks})", list(values.values())
    if action in {"update", "delete"} and keys:
        predicate = " AND ".join(f"{adapters.quote(field, kind)}={adapters.marker(kind, index + 1 + (len(values) if action == 'update' else 0))}" for index, field in enumerate(keys))
        if action == "delete": return f"DELETE FROM {target} WHERE {predicate}", list(keys.values())
        if values:
            assignments = ", ".join(f"{adapters.quote(field, kind)}={adapters.marker(kind, index + 1)}" for index, field in enumerate(values))
            return f"UPDATE {target} SET {assignments} WHERE {predicate}", [*values.values(), *keys.values()]
    raise ValueError("行操作需要有效动作、值和主键条件")


def apply_rows(request, asset, changes):
    if not isinstance(changes, list) or not changes or len(changes) > 500:
        raise ValueError("单次操作必须包含 1 至 500 行")
    with adapters.connection(asset, request.data.get("database")) as conn:
        try:
            affected = 0
            for change in changes:
                sql, params = row_statement(asset, change)
                _, count = adapters.run(conn, sql, params, db_type=asset.db_type)
                if change.get("action") in {"update", "delete"} and count != 1:
                    raise ValueError("行修改必须精确命中一条记录；请检查主键条件")
                affected += count
            if hasattr(conn, "commit"): conn.commit()
        except Exception:
            if hasattr(conn, "rollback"): conn.rollback()
            raise
    record_operation_log(request, "应用管理", "修改数据行", asset.name, f"操作数={len(changes)}; 影响行数={affected}")
    return Response({"affected": affected})


@api_view(["POST"])
def asset_rows(request, asset_id):
    asset, denied = checked(request, asset_id, "modify_data")
    if denied: return denied
    if asset.db_type in {"redis", "clickhouse"}: return bad_request("该类型不支持表格行修改，请使用命令或 SQL 编辑器")
    try: return apply_rows(request, asset, [request.data])
    except Exception as exc: return failed(exc)


@api_view(["POST"])
def asset_transaction(request, asset_id):
    asset, denied = checked(request, asset_id, "modify_data")
    if denied: return denied
    if request.data.get("action") == "rollback": return Response({"rolledBack": True})
    if request.data.get("action") != "commit": return bad_request("请提交或回滚暂存修改")
    try: return apply_rows(request, asset, request.data.get("changes"))
    except Exception as exc: return failed(exc)


def redis_value(client, key, kind):
    if kind == "string": return client.get(key)
    if kind == "list": return client.lrange(key, 0, 499)
    if kind == "set": return sorted(client.smembers(key))[:500]
    if kind == "zset": return client.zrange(key, 0, 499, withscores=True)
    if kind == "hash": return dict(list(client.hgetall(key).items())[:500])
    return None


def redis_export_value(client, key, kind):
    size_commands = {"list": "llen", "set": "scard", "zset": "zcard", "hash": "hlen"}
    if kind in size_commands and getattr(client, size_commands[kind])(key) > 500:
        raise ValueError("Redis 键包含超过 500 个成员，请缩小导出范围")
    return redis_value(client, key, kind)


def redis_key_size(client, key):
    try:
        return client.memory_usage(key) or 0
    except Exception:
        return 0


def redis_zset_mapping(value):
    mapping = {}
    for item in value:
        member, score = (item["member"], item["score"]) if isinstance(item, dict) else item
        mapping[str(member)] = float(score)
    return mapping


def selected_redis_database(asset, value):
    try:
        database = int(value if value is not None and value != "" else (asset.options or {}).get("db", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Redis DB 编号必须是 0 至 255") from exc
    if not 0 <= database <= 255:
        raise ValueError("Redis DB 编号必须是 0 至 255")
    return database


@api_view(["GET", "POST", "DELETE"])
def asset_redis(request, asset_id):
    asset, denied = checked(request, asset_id, "view_data" if request.method == "GET" else "redis_command")
    if denied: return denied
    if asset.db_type != "redis": return bad_request("该资产不是 Redis")
    try:
        requested_db = request.query_params.get("db") if request.method == "GET" else request.data.get("db")
        database = selected_redis_database(asset, requested_db)
        with adapters.connection(asset, database=database) as client:
            if request.method == "GET":
                key = request.query_params.get("key")
                if key:
                    kind = client.type(key)
                    return Response({"key": key, "type": kind, "ttl": client.ttl(key), "value": redis_value(client, key, kind)})
                keys = []
                for item in client.scan_iter(match=request.query_params.get("pattern", "*"), count=200):
                    keys.append({"key": item, "type": client.type(item), "ttl": client.ttl(item),
                                 "size": redis_key_size(client, item)})
                    if len(keys) == 500: break
                keyspace = client.info("keyspace")
                counts = [int(keyspace.get(f"db{number}", {}).get("keys", 0)) for number in range(16)]
                return Response({"keys": keys, "counts": counts})
            if request.method == "DELETE":
                count = client.delete(request.data.get("key", ""))
                record_operation_log(request, "应用管理", "删除 Redis 键", asset.name, f"数量={count}")
                return Response({"deleted": count})
            action = request.data.get("action")
            key = request.data.get("key", "")
            if action in {"set_value", "set_ttl"}:
                if not key:
                    return bad_request("请指定 Redis 键")
                if action == "set_ttl":
                    ttl = int(request.data.get("ttl", -1))
                    result = client.persist(key) if ttl < 0 else client.expire(key, ttl)
                else:
                    current_type = client.type(key)
                    value = request.data.get("value")
                    if current_type == "string":
                        result = client.set(key, value)
                    elif current_type == "hash" and isinstance(value, dict):
                        client.delete(key); result = client.hset(key, mapping=value)
                    elif current_type == "list" and isinstance(value, list):
                        client.delete(key); result = client.rpush(key, *value) if value else 0
                    elif current_type == "set" and isinstance(value, list):
                        client.delete(key); result = client.sadd(key, *value) if value else 0
                    elif current_type == "zset" and isinstance(value, list):
                        client.delete(key); result = client.zadd(key, redis_zset_mapping(value)) if value else 0
                    else:
                        return bad_request("键类型与提交的数据结构不匹配")
                record_operation_log(request, "应用管理", "修改 Redis 键", asset.name, f"动作={action}; 类型={client.type(key)}")
                return Response({"result": result})
            command = request.data.get("command")
            if not isinstance(command, list) or not command or len(command) > 20:
                return bad_request("请提供最多 20 个参数的 Redis 命令")
            if str(command[0]).upper() in {"FLUSHALL", "FLUSHDB", "SHUTDOWN", "CONFIG", "ACL", "MODULE", "REPLICAOF", "SLAVEOF"}:
                return bad_request("出于安全原因不允许执行 Redis 管理级命令")
            result = client.execute_command(*command)
            record_operation_log(request, "应用管理", "执行 Redis 命令", asset.name, f"操作={str(command[0])[:32]}")
            return Response({"result": result})
    except Exception as exc: return failed(exc)


def download(text, filename, content_type):
    response = HttpResponse(text, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime.date, datetime.time, datetime.datetime)):
        value = value.isoformat()
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return "'" + str(value).replace("'", "''") + "'"


@api_view(["GET"])
def asset_export(request, asset_id):
    asset, denied = checked(request, asset_id, "import_export")
    if denied: return denied
    if asset.db_type != "redis":
        from .transfers import export_response
        payload = {**request.query_params.dict(), "assetId": asset_id, "scope": "table", "direction": "export", "format": request.query_params.get("format", "sql"), "objectName": request.query_params.get("table", "")}
        return export_response(request.user, payload)
    fmt = request.query_params.get("format", "csv")
    try:
        if asset.db_type == "redis":
            if fmt not in {"json", "csv"}: return bad_request("Redis 仅支持 JSON/CSV")
            with adapters.connection(asset, database=selected_redis_database(asset, request.query_params.get("database"))) as client:
                rows = []
                for key in client.scan_iter(count=200):
                    if len(rows) >= 500:
                        raise ValueError("Redis 单次最多导出 500 个键，请先缩小键空间")
                    kind = client.type(key)
                    rows.append({"key": key, "type": kind, "ttl": client.ttl(key), "value": redis_export_value(client, key, kind)})
        if fmt == "json": text = json.dumps(rows, ensure_ascii=False, default=str)
        elif fmt == "csv":
            fields = list(rows[0]) if rows else (["key", "type", "ttl", "value"] if asset.db_type == "redis" else
                                                  [item["name"] for item in adapters.columns(asset, database, table, schema)])
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
            for row in rows:
                writer.writerow({**row, "value": json.dumps(row["value"], ensure_ascii=False, default=str)} if asset.db_type == "redis" and row["type"] != "string" else row)
            text = "\ufeff" + stream.getvalue()
        record_operation_log(request, "应用管理", "导出数据", asset.name, f"格式={fmt}; 行数={len(rows)}")
        return download(text, f"database-export.{fmt}", "application/json" if fmt == "json" else "text/plain; charset=utf-8")
    except Exception as exc: return failed(exc)


@api_view(["POST"])
def asset_import(request, asset_id):
    asset, denied = checked(request, asset_id, "import_export")
    if denied: return denied
    if asset.db_type != "redis":
        from .transfers import uploaded_dump_response
        return uploaded_dump_response(request.user, asset, request.data, request.FILES.get("file"))
    upload = request.FILES.get("file")
    if not upload or upload.size > 10 * 1024 * 1024: return bad_request("请选择不超过 10MB 的文件")
    fmt = request.data.get("format", "csv")
    try:
        content = upload.read().decode("utf-8-sig")
        if asset.db_type == "redis":
            if fmt not in {"json", "csv"}:
                return bad_request("Redis 仅支持 JSON/CSV")
            denied = require_feature_permission(request, "databaseManagement", "redis_command")
            if denied: return denied
            rows = json.loads(content) if fmt == "json" else list(csv.DictReader(io.StringIO(content)))
            if not isinstance(rows, list) or len(rows) > 10000: raise ValueError("导入数量不得超过 10000")
            with adapters.connection(asset, database=selected_redis_database(asset, request.data.get("database"))) as client:
                for row in rows:
                    key, kind = row["key"], row.get("type") or "string"
                    value = row["value"]
                    if fmt == "csv" and kind != "string":
                        value = json.loads(value)
                    if kind == "string":
                        client.set(key, value)
                    elif kind == "list" and isinstance(value, list):
                        client.delete(key)
                        if value: client.rpush(key, *value)
                    elif kind == "set" and isinstance(value, list):
                        client.delete(key)
                        if value: client.sadd(key, *value)
                    elif kind == "hash" and isinstance(value, dict):
                        client.delete(key)
                        if value: client.hset(key, mapping=value)
                    elif kind == "zset" and isinstance(value, list):
                        client.delete(key)
                        if value: client.zadd(key, {str(member): float(score) for member, score in value})
                    else:
                        raise ValueError("Redis 数据类型或结构无效")
                    if int(row.get("ttl") or -1) > 0: client.expire(key, int(row["ttl"]))
        record_operation_log(request, "应用管理", "导入数据", asset.name, f"格式={fmt}; 条数={len(rows)}")
        return Response({"imported": len(rows)})
    except Exception as exc: return failed(exc)
