import csv
import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path

from channels.layers import get_channel_layer
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import has_feature_permission, require_feature_permission
from operations.responses import bad_request, get_object_or_error
from system_management.services import record_operation_log

from . import adapters
from .models import AssetDirectory, DatabaseAsset, DatabaseTransferTask, SavedDatabaseQuery
from .serializers import DatabaseAssetSerializer
from .catalog import exported_asset, unique_name


ACTIVE = {"uploading", "inspecting", "awaiting_confirmation", "queued", "running", "cancel_requested"}
FINISHED = {"cancelled", "succeeded", "failed", "expired"}


def storage_dir():
    path = Path(settings.DATABASE_TRANSFER_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_path(task_id, suffix=".part"):
    return storage_dir() / f"{task_id}{suffix}"


def serialize(task):
    return {
        "id": str(task.pk), "assetId": task.asset_id, "assetName": task.asset.name if task.asset_id else "",
        "direction": task.direction, "scope": task.scope, "format": task.format,
        "database": task.database, "schema": task.schema, "objectName": task.object_name,
        "status": task.status, "stage": task.stage, "progress": task.progress,
        "processedRows": task.processed_rows, "processedBytes": task.processed_bytes,
        "totalRows": task.total_rows, "totalBytes": task.total_bytes,
        "preview": task.preview, "checkpoints": task.checkpoints, "sourceName": task.source_name, "error": task.error,
        "conflictPolicy": task.conflict_policy, "cancelRequested": task.cancel_requested,
        "createdAt": task.created_at, "startedAt": task.started_at, "finishedAt": task.finished_at,
        "expiresAt": task.expires_at, "canDownload": task.status == "succeeded" and bool(task.output_path),
    }


def emit(task):
    try:
        layer = get_channel_layer()
        if layer:
            from asgiref.sync import async_to_sync
            async_to_sync(layer.group_send)(f"database_transfer_{task.owner_id}", {"type": "transfer.update", "task": serialize(task)})
    except Exception:
        pass


def update(task, **values):
    if "stage" in values: values["stage"] = values["stage"][:64]
    for key, value in values.items():
        setattr(task, key, value)
    task.save(update_fields=[*values.keys(), "updated_at"])
    emit(task)
    return task


def create_task(owner, **values):
    now = timezone.now()
    task = DatabaseTransferTask.objects.create(owner=owner, expires_at=now + timedelta(days=settings.DATABASE_TRANSFER_RETENTION_DAYS), **values)
    emit(task)
    return task


def fetch_task(request, task_id):
    task, error = get_object_or_error(DatabaseTransferTask, pk=task_id, owner=request.user, error_message="任务不存在")
    return task, error


def effective_permission(scope, direction, fmt):
    required = ["import_export"]
    if direction == "import":
        if scope in {"table", "database"} and fmt in {"csv", "snapshot", "zip"}:
            required.append("modify_data")
        if fmt == "sql": required.append("execute_sql")
        if scope == "redis": required.append("redis_command")
        if scope in {"connections", "queries"}: required.append("execute_sql" if scope == "queries" else "create")
    return required


def require_task_permissions(user, task):
    required = effective_permission(task.scope, task.direction, task.format)
    if task.scope in {"table", "database"}:
        if task.direction == "export":
            required.append("view_data")
            if task.parameters.get("content", "structure_data") != "data":
                required.append("manage_schema")
        else:
            required.append("modify_data")
            if any(item.get("hasStructure") for item in task.preview.get("objects", [])):
                required.append("manage_schema")
    for permission in required:
        if permission == "create":
            continue
        if not has_feature_permission(user, "databaseManagement", permission):
            return False
    return True


def validate_dump_target(asset, scope, fmt):
    scope = str(scope or "").strip().lower()
    fmt = str(fmt or "").strip().lower().lstrip(".")
    if scope in {"table", "database"}:
        db_type = str(getattr(asset, "db_type", "") or "").strip().lower()
        if not asset or db_type not in {"mysql", "mariadb"}:
            from .mysql_dump import DumpError
            raise DumpError("表转储目前仅支持 MySQL/MariaDB")
        if fmt != "sql":
            from .mysql_dump import DumpError
            raise DumpError("旧 CSV/ZIP/JSON 表转储已移除，请重新提交 SQL 任务")


def configure_asset(request, data):
    asset = None
    if data.get("assetId") is not None:
        asset, error = get_object_or_error(DatabaseAsset, pk=data.get("assetId"), error_message="数据库资产不存在")
        if error: raise ValueError("数据库资产不存在")
    return asset


@api_view(["GET", "POST"])
def task_collection(request):
    denied = require_feature_permission(request, "databaseManagement", "import_export")
    if denied: return denied
    if request.method == "GET":
        items = DatabaseTransferTask.objects.filter(owner=request.user).select_related("asset")[:200]
        return Response([serialize(item) for item in items])
    return export_response(request.user, request.data)


def export_response(user, data):
    try:
        direction = str(data.get("direction", "") or "").strip().lower()
        scope = str(data.get("scope", "") or "").strip().lower()
        fmt = str(data.get("format", "") or "").strip().lower().lstrip(".")
        if direction != "export" or scope not in {"table", "database", "redis", "connections", "queries"}:
            raise ValueError("导出任务类型无效")
        asset = configure_asset(None, data)
        validate_dump_target(asset, scope, fmt)
        if scope in {"table", "database", "redis", "queries"} and asset is None: raise ValueError("此导出任务需要数据库资产")
        if not has_feature_permission(user, "databaseManagement", "import_export"): raise ValueError("没有导入导出权限")
        db_type = str(getattr(asset, "db_type", "") or "").strip().lower()
        if scope == "redis" and db_type != "redis": raise ValueError("Redis 导出任务需要 Redis 资产")
        if scope != "redis" and asset and db_type == "redis": raise ValueError("Redis 资产请使用 Redis 导出范围")
        allowed_formats = {"json", "csv"} if scope == "redis" else {"sql"} if scope == "queries" else {"json"} if scope == "connections" else {"sql"}
        if fmt not in allowed_formats: raise ValueError("导出格式不支持")
        names = data.get("tables", [])
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names) or len(names) != len(set(names)):
            raise ValueError("导出表范围无效")
        if scope == "table" and not names:
            names = [str(data.get("objectName") or data.get("table") or "")]
        if scope == "table" and len(names) != 1: raise ValueError("单表导出只能选择一张表")
        content = data.get("content", "structure_data")
        if content not in {"structure_data", "structure", "data"}: raise ValueError("导出内容无效")
        from .mysql_dump import quote
        for name in names: quote(name)
        if scope in {"table", "database"} and not has_feature_permission(user, "databaseManagement", "view_data"):
            raise PermissionError("没有数据读取权限")
        if scope in {"table", "database"} and content != "data" and not has_feature_permission(user, "databaseManagement", "manage_schema"):
            raise PermissionError("没有结构读取权限")
        task = create_task(owner=user, asset=asset, direction=direction, scope=scope, format=fmt,
                           database=str(data.get("database") or (asset.database if asset else "")), schema=str(data.get("schema") or ""),
                           object_name=str(data.get("objectName") or ""), parameters={"tables": names, "content": content, "table": str(data.get("table") or ""), "queryId": data.get("queryId"), "directoryId": data.get("directoryId"), "assetId": data.get("assetId")},
                           source_name=str(data.get("fileName") or (f"{data.get('objectName') or data.get('table') or 'database-export'}.{fmt}")),
                           status="queued", stage="queued")
        return Response(serialize(task), status=202)
    except Exception as exc:
        return bad_request(str(exc))


def uploaded_dump_response(owner, asset, data, upload):
    task = None
    try:
        for permission in ("import_export", "execute_sql", "modify_data"):
            if not has_feature_permission(owner, "databaseManagement", permission):
                return Response({"error": "当前账号缺少导入所需权限"}, status=403)
        if not upload: raise ValueError("请选择 SQL 文件")
        validate_dump_target(asset, "table", data.get("format", "sql"))
        task = create_task(owner=owner, asset=asset, direction="import", scope="table", format="sql",
                           database=str(data.get("database") or asset.database), object_name=str(data.get("table") or ""),
                           source_name=Path(upload.name).name[:255], status="uploading", stage="uploading")
        if not require_task_permissions(owner, task): raise PermissionError("当前账号缺少导入所需权限")
        path = task_path(task.pk, ".upload")
        update(task, input_path=str(path))
        size = 0
        from .mysql_dump import resource_guard
        with path.open("wb") as output:
            for chunk in upload.chunks():
                size += len(chunk)
                if settings.DATABASE_TRANSFER_MAX_UPLOAD_BYTES and size > settings.DATABASE_TRANSFER_MAX_UPLOAD_BYTES:
                    raise ValueError("文件超过配置上限")
                resource_guard(task); output.write(chunk)
        update(task, status="inspecting", stage="inspection_queued", total_bytes=size, processed_bytes=size)
        return Response(serialize(task), status=202)
    except Exception as exc:
        if task: update(task, status="failed", stage="upload_failed", error="SQL 上传失败", finished_at=timezone.now())
        return bad_request(str(exc))


@api_view(["POST"])
def upload_init(request):
    denied = require_feature_permission(request, "databaseManagement", "import_export")
    if denied: return denied
    data = request.data
    try:
        scope, fmt = str(data.get("scope", "")), str(data.get("format", ""))
        if scope not in {"table", "database", "redis", "connections", "queries"}: raise ValueError("导入任务类型无效")
        asset = configure_asset(request, data)
        validate_dump_target(asset, scope, fmt)
        if scope in {"table", "database", "redis"} and asset is None: raise ValueError("导入任务需要数据库资产")
        if scope == "redis" and asset.db_type != "redis": raise ValueError("Redis 导入任务需要 Redis 资产")
        if scope in {"table", "database"} and asset.db_type == "redis": raise ValueError("Redis 资产请使用 Redis 导入范围")
        if not has_feature_permission(request.user, "databaseManagement", "import_export"): raise ValueError("没有导入导出权限")
        for permission in effective_permission(scope, "import", fmt):
            if permission != "create" and not has_feature_permission(request.user, "databaseManagement", permission):
                raise ValueError("当前账号缺少此导入操作所需权限")
        if scope in {"table", "database"}:
            for permission in ("modify_data",):
                if not has_feature_permission(request.user, "databaseManagement", permission):
                    return Response({"error": "当前账号缺少导入所需权限"}, status=403)
        original = Path(str(data.get("fileName", "import.data"))).name[:255]
        chunk_count = data.get("chunks")
        total_bytes = data.get("totalBytes")
        if not isinstance(chunk_count, int) or chunk_count < 1:
            raise ValueError("分片数量无效")
        if not isinstance(total_bytes, int) or total_bytes < 0:
            raise ValueError("文件大小无效")
        if chunk_count != max(1, (total_bytes + settings.DATABASE_TRANSFER_CHUNK_BYTES - 1) // settings.DATABASE_TRANSFER_CHUNK_BYTES):
            raise ValueError("分片数量与声明的文件大小不一致")
        if settings.DATABASE_TRANSFER_MAX_UPLOAD_BYTES and total_bytes > settings.DATABASE_TRANSFER_MAX_UPLOAD_BYTES:
            raise ValueError("上传文件超过系统配置上限")
        task = create_task(owner=request.user, asset=asset, direction="import", scope=scope, format=fmt,
                           database=str(data.get("database") or (asset.database if asset else "")),
                           schema=str(data.get("schema") or ""), object_name=str(data.get("objectName") or ""),
                           source_name=original, parameters={"directoryId": data.get("directoryId"), "chunkCount": chunk_count, "totalBytes": total_bytes}, status="uploading", stage="uploading")
        task.input_path = str(task_path(task.pk, ".upload"))
        task.save(update_fields=["input_path"])
        return Response({**serialize(task), "chunkBytes": settings.DATABASE_TRANSFER_CHUNK_BYTES}, status=201)
    except Exception as exc:
        return bad_request(str(exc))


@api_view(["PUT"])
def upload_chunk(request, task_id, index):
    task, error = fetch_task(request, task_id)
    if error: return error
    denied = require_feature_permission(request, "databaseManagement", "import_export")
    if denied: return denied
    if task.status != "uploading": return bad_request("任务不在分片上传状态")
    try:
        chunk = request.body
        if len(chunk) > settings.DATABASE_TRANSFER_CHUNK_BYTES: raise ValueError("上传分片超过配置大小")
        expected_count = task.parameters.get("chunkCount")
        if index < 0 or not isinstance(expected_count, int) or index >= expected_count: raise ValueError("分片序号无效")
        path = task_path(task.pk, f".chunk.{index}")
        path.write_bytes(chunk)
        return Response({"index": index, "bytes": len(chunk)})
    except Exception as exc:
        return bad_request(str(exc))


def merge_chunks(task, count, expected_hash=""):
    expected_count = task.parameters.get("chunkCount")
    if count != expected_count or not isinstance(count, int) or count < 1: raise ValueError("分片数量与初始化声明不一致")
    final = Path(task.input_path)
    digest = hashlib.sha256()
    total = 0
    for index in range(count):
        if not task_path(task.pk, f".chunk.{index}").is_file(): raise ValueError(f"缺少第 {index + 1} 个分片")
    with final.open("wb") as output:
        for index in range(count):
            part = task_path(task.pk, f".chunk.{index}")
            if not part.is_file(): raise ValueError(f"缺少第 {index + 1} 个分片")
            with part.open("rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk: break
                    if shutil.disk_usage(final.parent).free < settings.DATABASE_TRANSFER_MIN_FREE_BYTES:
                        raise ValueError("服务器临时磁盘空间不足")
                    output.write(chunk); digest.update(chunk); total += len(chunk)
    expected_bytes = task.parameters.get("totalBytes")
    if expected_bytes is not None and total != expected_bytes:
        final.unlink(missing_ok=True)
        raise ValueError("上传文件大小与初始化声明不一致")
    if expected_hash and digest.hexdigest().lower() != expected_hash.lower():
        final.unlink(missing_ok=True)
        raise ValueError("上传文件 SHA-256 校验失败")
    limit = settings.DATABASE_TRANSFER_MAX_UPLOAD_BYTES
    if limit and total > limit: final.unlink(missing_ok=True); raise ValueError("上传文件超过系统配置上限")
    if shutil.disk_usage(final.parent).free < settings.DATABASE_TRANSFER_MIN_FREE_BYTES:
        final.unlink(missing_ok=True); raise ValueError("服务器临时磁盘空间不足")
    for index in range(count): task_path(task.pk, f".chunk.{index}").unlink(missing_ok=True)
    return total, digest.hexdigest()


def inspect_input(task):
    path = Path(task.input_path)
    suffix = Path(task.source_name).suffix.lower()
    preview = {"fileBytes": path.stat().st_size, "format": task.format, "sourceName": task.source_name, "warnings": []}
    if task.scope in {"table", "database"}:
        validate_dump_target(task.asset, task.scope, task.format)
        from .mysql_dump import inspect_dump
        return inspect_dump(task, lambda: progress(task, stage="validating_sql"))
    if task.format == "snapshot" or suffix == ".json":
        with path.open("r", encoding="utf-8-sig") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict): raise ValueError("JSON 数据包格式无效")
        if "tables" in payload:
            preview["tables"] = len(payload["tables"])
            preview["rows"] = sum(len(item.get("rows", [])) for item in payload["tables"] if isinstance(item, dict))
        elif "assets" in payload:
            preview["assets"] = len(payload.get("assets", [])); preview["directories"] = len(payload.get("directories", []))
        else:
            preview["records"] = len(payload) if isinstance(payload, list) else 1
    elif task.format == "csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream); preview["columns"] = next(reader, []); preview["rows"] = sum(1 for _ in reader)
        if task.scope == "table" and not preview["columns"]: raise ValueError("CSV 文件缺少表头")
    elif task.format == "sql":
        preview["requiresExplicitConfirmation"] = True
        preview["fileBytes"] = path.stat().st_size
    else:
        raise ValueError("暂不支持此导入格式")
    return preview


@api_view(["POST"])
def upload_complete(request, task_id):
    task, error = fetch_task(request, task_id)
    if error: return error
    denied = require_feature_permission(request, "databaseManagement", "import_export")
    if denied: return denied
    if task.status != "uploading": return bad_request("任务不在上传状态")
    try:
        size, digest = merge_chunks(task, request.data.get("chunks"), request.data.get("sha256", ""))
        update(task, status="inspecting", stage="validating", total_bytes=size, processed_bytes=size)
        if task.scope in {"table", "database"}:
            update(task, parameters={**task.parameters, "sha256": digest}, stage="inspection_queued")
            return Response(serialize(task), status=202)
        preview = inspect_input(task)
        preview["sha256"] = digest
        update(task, status="awaiting_confirmation", stage="awaiting_confirmation", preview=preview)
        return Response(serialize(task))
    except Exception as exc:
        update(task, status="failed", stage="validation_failed", error=str(exc), finished_at=timezone.now())
        return bad_request(str(exc))


@api_view(["POST"])
def task_confirm(request, task_id):
    task, error = fetch_task(request, task_id)
    if error: return error
    if not require_task_permissions(request.user, task): return bad_request("permission revoked")
    if task.status != "awaiting_confirmation": return bad_request("任务未等待确认")
    policy = str(request.data.get("conflictPolicy", "append"))
    if policy not in {"append", "overwrite", "skip", "rename"}: return bad_request("冲突处理策略无效")
    if task.scope in {"table", "database"} and policy == "rename": return bad_request("表导入不支持重命名策略")
    if task.scope in {"table", "database"} and policy == "append" and any(item.get("appendCompatible") is False for item in task.preview.get("objects", [])):
        return bad_request("字段与目标结构不兼容，不能追加")
    if task.preview.get("requiresExplicitConfirmation") and request.data.get("confirmed") is not True:
        return bad_request("SQL 导入需要明确确认")
    if task.scope in {"database", "table", "redis"} and policy in {"overwrite", "skip"} and request.data.get("confirmed") is not True:
        return bad_request("覆盖或跳过操作需要明确确认")
    update(task, conflict_policy=policy, status="queued", stage="queued", error="")
    return Response(serialize(task), status=202)


@api_view(["GET"])
def task_detail(request, task_id):
    task, error = fetch_task(request, task_id)
    return error or Response(serialize(task))


@api_view(["POST"])
def task_cancel(request, task_id):
    task, error = fetch_task(request, task_id)
    if error: return error
    if task.status not in ACTIVE: return bad_request("任务已结束")
    if not require_task_permissions(request.user, task): return bad_request("任务所需权限已被撤销")
    if task.status in {"queued", "uploading", "awaiting_confirmation"} or (task.status == "inspecting" and task.stage == "inspection_queued"):
        update(task, status="cancelled", stage="cancelled", finished_at=timezone.now(), cancel_requested=True)
    else:
        update(task, status="cancel_requested", cancel_requested=True)
    return Response(serialize(task))


@api_view(["POST"])
def task_retry(request, task_id):
    source, error = fetch_task(request, task_id)
    if error: return error
    if source.status not in {"failed", "cancelled"}: return bad_request("仅失败或已取消任务可以重试")
    try: validate_dump_target(source.asset, source.scope, source.format)
    except ValueError as exc: return bad_request(str(exc))
    if source.direction == "import" and source.format == "sql" and request.data.get("confirmed") is not True: return bad_request("SQL 重试需再次确认可能重复执行")
    if not require_task_permissions(request.user, source): return bad_request("当前账号已不具备任务所需权限")
    source_input = Path(source.input_path) if source.input_path and Path(source.input_path).is_file() else None
    task = create_task(owner=request.user, asset=source.asset, direction=source.direction, scope=source.scope,
                       format=source.format, database=source.database, schema=source.schema,
                       object_name=source.object_name, parameters=source.parameters, conflict_policy=source.conflict_policy,
                       status="inspecting" if source.direction == "import" and not source.preview else "queued",
                       stage="inspection_queued" if source.direction == "import" and not source.preview else "queued", retry_of=source,
                       input_path="",
                       source_name=source.source_name, checkpoints=source.checkpoints,
                       preview=source.preview, processed_rows=source.processed_rows if source.direction == "import" else 0)
    if source.direction == "import":
        if source_input is None:
            task.delete()
            return bad_request("原始导入文件已过期或不存在")
        task.input_path = str(task_path(task.pk, ".upload"))
        shutil.copyfile(source_input, task.input_path)
        task.save(update_fields=["input_path", "updated_at"])
    return Response(serialize(task), status=202)


@api_view(["GET"])
def task_download(request, task_id):
    task, error = fetch_task(request, task_id)
    if error: return error
    if not require_task_permissions(request.user, task): return bad_request("任务所需权限已被撤销")
    if task.status != "succeeded" or not task.output_path or not Path(task.output_path).is_file(): return bad_request("导出文件尚未就绪")
    response = FileResponse(open(task.output_path, "rb"), as_attachment=True, filename=task.source_name or f"database-export-{task.pk}.{task.format}")
    return response


@api_view(["DELETE"])
def task_delete(request, task_id):
    task, error = fetch_task(request, task_id)
    if error: return error
    if task.status in ACTIVE: return bad_request("运行中的任务不能删除，请先取消")
    paths = [task.input_path, task.output_path]
    task.delete()
    for value in paths:
        if value: Path(value).unlink(missing_ok=True)
    return Response({"deleted": True})


def task_cancelled(task_id):
    return DatabaseTransferTask.objects.filter(pk=task_id, cancel_requested=True).exists()


def progress(task, *, stage=None, rows=None, byte_count=None, total=None):
    task.refresh_from_db()
    if task.cancel_requested: raise InterruptedError("用户取消任务")
    values = {}
    if stage is not None: values["stage"] = stage
    if rows is not None: values["processed_rows"] = rows
    if byte_count is not None: values["processed_bytes"] = byte_count
    if total is not None: values["total_rows"] = total
    if total and rows is not None: values["progress"] = min(99, int(rows * 100 / total))
    update(task, **values)




def connection_manifest_payload(task):
    folders = list(AssetDirectory.objects.all())
    folder_by_id = {folder.id: folder for folder in folders}
    def path_for(folder):
        path = []
        while folder:
            path.insert(0, folder.name); folder = folder_by_id.get(folder.parent_id)
        return path
    directory_id = task.parameters.get("directoryId")
    assets = DatabaseAsset.objects.filter(directory_id=directory_id) if directory_id else DatabaseAsset.objects.all()
    return {"version": 1, "directories": [path_for(folder) for folder in folders], "assets": [exported_asset(asset, path_for(folder_by_id.get(asset.directory_id))) for asset in assets]}


def export_small(task, output_path):
    if task.scope == "connections":
        output_path.write_text(json.dumps(connection_manifest_payload(task), ensure_ascii=False, indent=2), encoding="utf-8")
        task.processed_rows = len(connection_manifest_payload(task)["assets"])
    elif task.scope == "queries":
        query_id = task.parameters.get("queryId")
        query = SavedDatabaseQuery.objects.get(pk=query_id, owner=task.owner)
        output_path.write_text(query.sql, encoding="utf-8")
        task.processed_rows = 1
    else: raise ValueError("导出范围不支持")




def import_legacy_snapshot(task):
    with Path(task.input_path).open("r", encoding="utf-8-sig") as stream: payload = json.load(stream)
    if payload.get("version") != 1 or payload.get("dbType") != task.asset.db_type: raise ValueError("JSON 数据包版本或数据库类型不匹配")
    if task.asset.db_type == "redis":
        with adapters.connection(task.asset, task.database) as client:
            for row in payload.get("keys", []):
                if task.conflict_policy == "skip" and client.exists(row["key"]): continue
                from .advanced import redis_export_value
                kind, value = row["type"], row["value"]
                client.delete(row["key"])
                if kind == "string": client.set(row["key"], value)
                elif kind == "list" and value: client.rpush(row["key"], *value)
                elif kind == "set" and value: client.sadd(row["key"], *value)
                elif kind == "hash" and value: client.hset(row["key"], mapping=value)
                elif kind == "zset" and value: client.zadd(row["key"], {str(key): float(score) for key, score in value.items()})
                if int(row.get("ttl", -1)) > 0: client.expire(row["key"], int(row["ttl"]))
                task.processed_rows += 1
                if task.processed_rows % 100 == 0: progress(task, stage="importing_keys", rows=task.processed_rows)
        return


def import_task(task):
    fmt = task.format
    if task.scope in {"table", "database"}:
        validate_dump_target(task.asset, task.scope, fmt)
        from .mysql_dump import import_dump
        return import_dump(task, progress)
    if task.scope == "queries":
        sql = Path(task.input_path).read_text(encoding="utf-8-sig")
        name = Path(task.source_name).stem[:160] or "导入查询"
        existing = SavedDatabaseQuery.objects.filter(owner=task.owner, asset=task.asset, database=task.database, schema=task.schema, name=name).first()
        if existing and task.conflict_policy == "skip": return
        if existing and task.conflict_policy == "overwrite": existing.sql = sql; existing.save(update_fields=["sql", "updated_at"]); return
        if existing:
            for index in range(1, 1000):
                candidate = f"{name} - 副本" if index == 1 else f"{name} - 副本 {index}"
                if not SavedDatabaseQuery.objects.filter(owner=task.owner, asset=task.asset, database=task.database, schema=task.schema, name=candidate).exists(): name = candidate[:160]; break
        SavedDatabaseQuery.objects.create(owner=task.owner, asset=task.asset, database=task.database, schema=task.schema, name=name, sql=sql)
        return
    if task.scope == "connections":
        from .catalog import import_manifest_payload
        with Path(task.input_path).open("r", encoding="utf-8-sig") as source: return import_manifest_payload(task.owner, json.load(source), task.parameters.get("directoryId"), task.conflict_policy)
    if fmt == "snapshot" or Path(task.source_name).suffix.lower() == ".json": return import_legacy_snapshot(task)
    raise ValueError("导入范围不支持")


def run_task(task):
    validate_dump_target(task.asset, task.scope, task.format)
    if not require_task_permissions(task.owner, task): raise PermissionError("任务所需权限已被撤销")
    if task.stage == "inspection_running":
        preview = inspect_input(task)
        progress(task, stage="inspection_running")
        preview["sha256"] = task.parameters.get("sha256", "")
        update(task, status="awaiting_confirmation", stage="awaiting_confirmation", preview=preview)
        return
    if not require_task_permissions(task.owner, task): raise PermissionError("任务所需权限已被撤销")
    task.refresh_from_db()
    if task.cancel_requested: raise InterruptedError("用户取消任务")
    if task.direction == "import":
        if task.scope in {"table", "database"} and not task.preview.get("requiresExplicitConfirmation"):
            raise PermissionError("SQL 转储必须先预检并确认")
        import_task(task)
        update(task, status="succeeded", stage="complete", progress=100, finished_at=timezone.now())
        audit_task(task)
        return
    output_path = task_path(task.pk, f".result.{task.format}")
    update(task, output_path=str(output_path))
    if task.scope in {"table", "database"}:
        from .mysql_dump import export_dump
        with output_path.open("w", encoding="utf-8", newline="") as output:
            export_dump(task, output, progress)
    elif task.scope in {"connections", "queries"}:
        export_small(task, output_path)
    else:
        with output_path.open("w", encoding="utf-8-sig", newline="") as output:
            if task.scope == "redis":
                from .advanced import redis_export_value
                asset = task.asset
                with adapters.connection(asset, database=task.database) as client:
                    writer = csv.DictWriter(output, fieldnames=["key", "type", "ttl", "value"]) if task.format == "csv" else None
                    if writer: writer.writeheader()
                    for key in client.scan_iter(count=500):
                        progress(task, stage="exporting_keys", rows=task.processed_rows)
                        kind = client.type(key)
                        value = redis_export_value(client, key, kind)
                        row = {"key": key, "type": kind, "ttl": client.ttl(key), "value": json.dumps(value, ensure_ascii=False, default=str)}
                        if writer: writer.writerow(row)
                        else: output.write(json.dumps(row, ensure_ascii=False) + "\n")
                        task.processed_rows += 1
                        if task.processed_rows % 100 == 0: task.save(update_fields=["processed_rows", "updated_at"]); emit(task)
            else: raise ValueError("导出范围不支持")
    output_path = Path(output_path)
    output_size = output_path.stat().st_size
    if settings.DATABASE_TRANSFER_MAX_RESULT_BYTES and output_size > settings.DATABASE_TRANSFER_MAX_RESULT_BYTES:
        raise ValueError("结果超过系统配置上限")
    if shutil.disk_usage(output_path.parent).free < settings.DATABASE_TRANSFER_MIN_FREE_BYTES:
        raise ValueError("服务器临时磁盘空间不足")
    update(task, status="succeeded", stage="complete", progress=100, output_path=str(output_path),
           total_bytes=output_size, finished_at=timezone.now(), source_name=task.source_name or output_path.name)
    audit_task(task)


def audit_task(task):
    from django.test.client import RequestFactory
    record_operation_log(RequestFactory().get("/"), "应用管理", "数据库传输任务", str(task.pk), f"方向={task.direction}; 范围={task.scope}; 格式={task.format}; 状态={task.status}; 行数={task.processed_rows}", user=task.owner)


def claim_one():
    legacy = DatabaseTransferTask.objects.filter(scope__in={"table", "database"}, status__in=ACTIVE).exclude(format="sql").exclude(status__in={"running", "cancel_requested"})
    for task in legacy:
        update(task, status="failed", stage="unsupported_format", error="旧 CSV/ZIP/JSON 表转储已移除，请重新提交 SQL 任务", finished_at=timezone.now())
    cutoff = timezone.now() - timedelta(seconds=settings.DATABASE_TRANSFER_TASK_TIMEOUT_SECONDS)
    stale = DatabaseTransferTask.objects.filter(status="running", started_at__lt=cutoff)
    for task in stale:
        update(task, status="failed", stage="timeout", error="任务超过执行超时时间", finished_at=timezone.now())
    with transaction.atomic():
        from django.db.models import Q
        task = DatabaseTransferTask.objects.filter(Q(status="queued") | Q(status="inspecting", stage="inspection_queued")).order_by("created_at").first()
        if not task: return None
        inspection = task.status == "inspecting"
        changed = DatabaseTransferTask.objects.filter(pk=task.pk, status=task.status, stage=task.stage).update(status="running", stage="inspection_running" if inspection else "starting", started_at=timezone.now())
        if not changed: return None
        task.refresh_from_db(); emit(task)
        return task


def execute_claimed(task):
    try:
        run_task(task)
    except InterruptedError as exc:
        update(task, status="cancelled", stage="cancelled", error=str(exc), finished_at=timezone.now())
        audit_task(task)
    except Exception as exc:
        # Driver messages may contain SQL values; only expose known safe application errors.
        from .mysql_dump import DumpError
        summary = str(exc) if isinstance(exc, (DumpError, PermissionError)) else "数据库传输失败，请检查目标兼容性、键冲突、权限及连接状态"
        update(task, status="failed", stage="failed", error=summary[:2000], finished_at=timezone.now())
        audit_task(task)


def cleanup_expired():
    now = timezone.now()
    for task in DatabaseTransferTask.objects.filter(expires_at__lte=now).exclude(status__in={"expired", "running", "queued"}):
        for value in (task.input_path, task.output_path):
            if value: Path(value).unlink(missing_ok=True)
        update(task, status="expired", stage="expired", input_path="", output_path="")
    for part in storage_dir().glob("*.chunk.*"):
        if time.time() - part.stat().st_mtime > settings.DATABASE_TRANSFER_TASK_TIMEOUT_SECONDS: part.unlink(missing_ok=True)
