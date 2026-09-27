"""Database-level operations with bounded, portable data snapshots."""

import json
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
    tables = adapters.object_list(asset, name, object_type="table")
    if len(tables) > MAX_TABLES: raise ValueError("数据库表超过导出上限")
    result = []
    row_count = 0
    for item in tables:
        table = item["name"]
        data = []
        page = 1
        while True:
            chunk = adapters.table_data(asset, name, table, page=page, page_size=200)
            data.extend(chunk["rows"])
            row_count += len(chunk["rows"])
            if row_count > MAX_ROWS: raise ValueError("数据库行数超过导出上限")
            if not chunk["hasNext"]: break
            page += 1
        result.append({"name": table, "columns": adapters.columns(asset, name, table), "rows": data})
    return {"version": 1, "dbType": asset.db_type, "database": name, "tables": result}


def import_snapshot(asset, name, payload):
    if not isinstance(payload, dict) or payload.get("version") != 1 or payload.get("dbType") != asset.db_type:
        raise ValueError("数据包版本或数据库类型不匹配")
    if asset.db_type == "redis":
        raise ValueError("Redis 整库导入请使用现有 JSON 键值导入功能")
    tables = payload.get("tables")
    if not isinstance(tables, list) or len(tables) > MAX_TABLES:
        raise ValueError("数据包表列表无效")
    available = {item["name"] for item in adapters.object_list(asset, name, object_type="table")}
    total = 0
    with adapters.connection(asset, name) as conn:
        try:
            for item in tables:
                if not isinstance(item, dict) or item.get("name") not in available or not isinstance(item.get("rows"), list):
                    raise ValueError("目标数据库缺少数据包中的表")
                table = adapters.quote(item["name"], asset.db_type)
                for row in item["rows"]:
                    if not isinstance(row, dict) or not row: raise ValueError("数据包包含无效数据行")
                    columns = ", ".join(adapters.quote(key, asset.db_type) for key in row)
                    markers = ", ".join(adapters.marker(asset.db_type, index + 1) for index in range(len(row)))
                    adapters.run(conn, f"INSERT INTO {table} ({columns}) VALUES ({markers})", list(row.values()), db_type=asset.db_type)
                    total += 1
                    if total > MAX_ROWS: raise ValueError("导入行数超过上限")
            if hasattr(conn, "commit"): conn.commit()
        except Exception:
            if hasattr(conn, "rollback"): conn.rollback()
            raise
    return {"imported": total}


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
        _, name = database_name(asset, name)
        if action == "create": result = create_database(asset, name)
        elif action == "delete": result = delete_database(asset, name)
        elif action == "clear": result = clear_database(asset, name)
        elif action == "export":
            result = snapshot(asset, name)
            data = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
            if len(data) > MAX_BYTES: raise ValueError("数据库数据包超过 5 MB")
            response = HttpResponse(data, content_type="application/json; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="database-export.json"'
            record_operation_log(request, "应用管理", "导出数据库数据", asset.name, f"类型={asset.db_type}; 数据库={name}")
            return response
        elif action == "import":
            content = request.data.get("snapshot")
            if len(json.dumps(content, default=str).encode("utf-8")) > MAX_BYTES:
                raise ValueError("数据库数据包超过 5 MB")
            result = import_snapshot(asset, name, content)
        else: return bad_request("不支持的数据库操作")
        record_operation_log(request, "应用管理", "数据库级操作", asset.name, f"动作={action}; 类型={asset.db_type}; 数据库={name}")
        return Response(result)
    except Exception as exc: return bad_request(adapters.connection_error(exc))
