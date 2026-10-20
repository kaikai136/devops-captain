"""Database-level operations with bounded, portable data snapshots."""

import json
import re
import sqlite3
from pathlib import Path

from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import require_feature_permission
from operations.responses import bad_request, get_object_or_error
from system_management.services import record_operation_log

from . import adapters
from .catalog import copy_name, duplicate_asset
from .models import DatabaseAsset


MAX_TABLES = 100
MAX_ROWS = 10000
MAX_BYTES = 5_000_000


def maintenance_database(asset):
    return {"mysql": "information_schema", "mariadb": "information_schema",
            "postgresql": "postgres", "kingbase": "postgres", "sqlserver": "master",
            "clickhouse": "default"}.get(asset.db_type)


def database_name(asset, value):
    if asset.db_type == "sqlite":
        path = adapters.sqlite_path(value)
        return path, path.name
    if asset.db_type == "redis":
        try: number = int(value)
        except (TypeError, ValueError) as exc: raise ValueError("Redis DB 必须为 0 至 255 的整数") from exc
        if not 0 <= number <= 255: raise ValueError("Redis DB 必须为 0 至 255 的整数")
        return number, str(number)
    return adapters.quote(value, asset.db_type), str(value)


def run_ddl(asset, statement):
    with adapters.connection(asset, maintenance_database(asset)) as conn:
        if asset.db_type in {"postgresql", "kingbase"}:
            conn.autocommit = True
        adapters.run(conn, statement, db_type=asset.db_type)
        if hasattr(conn, "commit"): conn.commit()


def create_database(asset, value):
    target, label = database_name(asset, value)
    kind = asset.db_type
    if kind == "sqlite":
        if target.exists(): raise ValueError("SQLite 文件已存在")
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(target) as conn:
            conn.execute("PRAGMA user_version=1")
        return {"name": label}
    if kind == "redis":
        clone = duplicate_asset(asset)
        clone.options = {**asset.options, "db": target}
        clone.name = copy_name(f"{asset.name} DB {target}", clone.directory, DatabaseAsset)
        clone.save(update_fields=["options", "name"])
        return {"name": label, "assetId": clone.pk}
    if kind in {"oracle", "dameng"}:
        raise ValueError("该类型无法通过普通连接创建实例；请由数据库管理员创建 Schema 或实例")
    run_ddl(asset, f"CREATE DATABASE {target}")
    return {"name": label}


def delete_database(asset, value):
    target, label = database_name(asset, value)
    kind = asset.db_type
    if kind == "sqlite":
        if not target.is_file(): raise ValueError("SQLite 文件不存在")
        if DatabaseAsset.objects.filter(db_type="sqlite", options__file=label).exclude(pk=asset.pk).exists():
            raise ValueError("其他资产仍在使用该 SQLite 文件")
        target.unlink()
        return {"name": label}
    if kind == "redis":
        raise ValueError("Redis DB 编号不能删除；可清空指定 DB 的键")
    if kind in {"oracle", "dameng"}:
        raise ValueError("该类型无法通过普通连接删除实例或 Schema")
    run_ddl(asset, f"DROP DATABASE {target}")
    return {"name": label}


def alter_mysql_database(asset, data):
    if asset.db_type != "mysql": raise ValueError("当前操作仅支持 MySQL")
    _, name = database_name(asset, data.get("name"))
    charset = str(data.get("charset", "")).strip()
    collation = str(data.get("collation", "")).strip()
    if not charset or not collation: raise ValueError("请选择字符编码和字符集排序规则")
    if not all(re.fullmatch(r"[A-Za-z0-9_]+", value) for value in (charset, collation)): raise ValueError("字符集参数不合法")
    with adapters.connection(asset, "information_schema") as conn:
        rows, _ = adapters.run(conn, "SELECT COLLATION_NAME AS collation FROM COLLATIONS WHERE CHARACTER_SET_NAME=%s AND COLLATION_NAME=%s", (charset, collation), db_type=asset.db_type)
        if not rows: raise ValueError("字符集排序规则与字符编码不匹配")
        adapters.run(conn, f"ALTER DATABASE {adapters.quote(name, asset.db_type)} CHARACTER SET {charset} COLLATE {collation}", db_type=asset.db_type)
        conn.commit()
    return {"name": name, "charset": charset, "collation": collation}


@api_view(["GET"])
def mysql_metadata(request, asset_id):
    diagram = request.query_params.get("diagram") == "1"
    denied = require_feature_permission(request, "databaseManagement", "view_data" if diagram else "database_admin")
    if denied: return denied
    asset, error = get_object_or_error(DatabaseAsset, pk=asset_id, error_message="数据库资产不存在")
    if error: return error
    if asset.db_type != "mysql": return bad_request("当前操作仅支持 MySQL")
    try:
        _, name = database_name(asset, request.query_params.get("name"))
        with adapters.connection(asset, "information_schema") as conn:
            if diagram:
                fields, _ = adapters.run(conn, "SELECT TABLE_NAME AS table_name, COLUMN_NAME AS name, COLUMN_TYPE AS type, COLUMN_KEY AS column_key, COLUMN_COMMENT AS comment FROM COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME, ORDINAL_POSITION", (name,), db_type="mysql", max_rows=20000)
                links, _ = adapters.run(conn, "SELECT CONSTRAINT_NAME AS name, TABLE_NAME AS source, COLUMN_NAME AS source_column, REFERENCED_TABLE_NAME AS target, REFERENCED_COLUMN_NAME AS target_column FROM KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION", (name, name), db_type="mysql", max_rows=20000)
                return Response({"columns": fields, "relations": links})
            current, _ = adapters.run(conn, "SELECT DEFAULT_CHARACTER_SET_NAME AS charset, DEFAULT_COLLATION_NAME AS collation FROM SCHEMATA WHERE SCHEMA_NAME=%s", (name,), db_type="mysql")
            if not current: raise ValueError("数据库不存在")
            choices, _ = adapters.run(conn, "SELECT CHARACTER_SET_NAME AS charset, COLLATION_NAME AS collation FROM COLLATIONS ORDER BY CHARACTER_SET_NAME, COLLATION_NAME", db_type="mysql", max_rows=5000)
            return Response({"name": name, **current[0], "choices": choices})
    except Exception as exc: return bad_request(adapters.connection_error(exc))


def snapshot(asset, name):
    if asset.db_type == "redis":
        selected = int(name)
        clone = DatabaseAsset(db_type="redis", host=asset.host, port=asset.port,
                              username=asset.username, password_encrypted=asset.password_encrypted,
                              options={**asset.options, "db": selected})
        with adapters.connection(clone) as client:
            keys = []
            for key in client.scan_iter(count=200):
                if len(keys) >= MAX_ROWS: raise ValueError("Redis 键超过导出上限")
                kind = client.type(key)
                from .advanced import redis_export_value
                keys.append({"key": key, "type": kind, "ttl": client.ttl(key),
                             "value": redis_export_value(client, key, kind)})
        return {"version": 1, "dbType": "redis", "database": str(selected), "keys": keys}
    raise ValueError("关系库快照已移除，请提交 SQL 转储任务")



def import_snapshot(asset, name, payload):
    if not isinstance(payload, dict) or payload.get("version") != 1 or payload.get("dbType") != asset.db_type:
        raise ValueError("数据包版本或数据库类型不匹配")
    if asset.db_type == "redis":
        raise ValueError("Redis 整库导入请使用现有 JSON 键值导入功能")
    raise ValueError("关系库快照已移除，请通过分片上传任务导入 SQL")



def clear_database(asset, name):
    if asset.db_type == "redis":
        clone = DatabaseAsset(db_type="redis", host=asset.host, port=asset.port,
                              username=asset.username, password_encrypted=asset.password_encrypted,
                              options={**asset.options, "db": int(name)})
        with adapters.connection(clone) as client:
            return {"deleted": client.flushdb(asynchronous=False)}
    tables = adapters.object_list(asset, name, object_type="table")
    if len(tables) > MAX_TABLES: raise ValueError("数据库表超过操作上限")
    with adapters.connection(asset, name) as conn:
        try:
            for item in tables:
                table = adapters.quote(item["name"], asset.db_type)
                adapters.run(conn, f"DELETE FROM {table}", db_type=asset.db_type)
            if hasattr(conn, "commit"): conn.commit()
        except Exception:
            if hasattr(conn, "rollback"): conn.rollback()
            raise
    return {"cleared": len(tables)}


@api_view(["GET", "POST"])
def database_operation(request, asset_id):
    denied = require_feature_permission(request, "databaseManagement", "database_admin")
    if denied: return denied
    asset, error = get_object_or_error(DatabaseAsset, pk=asset_id, error_message="数据库资产不存在")
    if error: return error
    action = "export" if request.method == "GET" else request.data.get("action")
    name = request.query_params.get("name") if request.method == "GET" else request.data.get("name")
    try:
        if request.method == "POST" and request.data.get("action") == "edit":
            result = alter_mysql_database(asset, request.data)
            record_operation_log(request, "应用管理", "编辑数据库", result["name"], f"字符集={result['charset']}; 排序规则={result['collation']}")
            return Response(result)
        _, name = database_name(asset, name)
        if action == "create": result = create_database(asset, name)
        elif action == "delete": result = delete_database(asset, name)
        elif action == "clear": result = clear_database(asset, name)
        elif action == "export":
            if asset.db_type != "redis":
                from .transfers import export_response
                return export_response(request.user, {"assetId": asset_id, "database": name, "scope": "database", "direction": "export", "format": "sql"})
            result = snapshot(asset, name)
            data = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
            if len(data) > MAX_BYTES: raise ValueError("数据库数据包超过 5 MB")
            response = HttpResponse(data, content_type="application/json; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="database-export.json"'
            record_operation_log(request, "应用管理", "导出数据库数据", asset.name, f"类型={asset.db_type}; 数据库={name}")
            return response
        elif action == "import":
            if asset.db_type != "redis": return bad_request("旧快照导入已移除，请通过分片上传任务接口导入 SQL")
            content = request.data.get("snapshot")
            if len(json.dumps(content, default=str).encode("utf-8")) > MAX_BYTES:
                raise ValueError("数据库数据包超过 5 MB")
            result = import_snapshot(asset, name, content)
        else: return bad_request("不支持的数据库操作")
        record_operation_log(request, "应用管理", "数据库级操作", asset.name, f"动作={action}; 类型={asset.db_type}; 数据库={name}")
        return Response(result)
    except Exception as exc: return bad_request(adapters.connection_error(exc))
