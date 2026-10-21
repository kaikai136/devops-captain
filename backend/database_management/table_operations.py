import hashlib
import re
from contextlib import ExitStack
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import has_feature_permission
from operations.responses import bad_request
from system_management.services import record_operation_log
from . import adapters
from .connection_config import enforce_policy
from .models import DatabaseAsset, DatabaseTransferTask
from .mysql_dump import DumpError, quote, resource_guard


def require_permissions(user, mode):
    permissions = {"view_data", "manage_schema" if mode == "structure" else "modify_data"}
    if mode == "copy": permissions.add("import_export")
    if not all(has_feature_permission(user, "databaseManagement", permission) for permission in permissions):
        raise PermissionError("没有执行此表操作的权限")


def resolve_reference(data, write=False):
    if not isinstance(data, dict): raise DumpError("表范围无效")
    try: asset = DatabaseAsset.objects.get(pk=data.get("assetId"))
    except (DatabaseAsset.DoesNotExist, ValueError, TypeError): raise DumpError("数据库资产不存在")
    if asset.db_type not in {"mysql", "mariadb"}: raise DumpError("表复制和同步目前仅支持 MySQL/MariaDB")
    enforce_policy(asset, write=write)
    database = str(data.get("database") or asset.database)
    table = str(data.get("table") or "")
    schema = str(data.get("schema") or "")
    quote(database); quote(table)
    if schema and schema != database: raise DumpError("MySQL Schema 必须与目标数据库一致")
    return asset, {"assetId": asset.pk, "database": database, "schema": schema, "table": table}


def ddl_parts(ddl):
    start = ddl.index("(")
    depth, delimiter, index, begin, parts = 1, None, start + 1, start + 1, []
    while index < len(ddl):
        char = ddl[index]
        if delimiter:
            if char == "\\" and delimiter != "`": index += 2; continue
            if char == delimiter:
                if index + 1 < len(ddl) and ddl[index + 1] == delimiter: index += 2; continue
                delimiter = None
        elif char in "'\"`": delimiter = char
        elif char == "(": depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                parts.append(ddl[begin:index].strip())
                return parts
        elif char == "," and depth == 1:
            parts.append(ddl[begin:index].strip()); begin = index + 1
        index += 1
    raise DumpError("表 DDL 不完整")


def definitions(ddl):
    fields, indexes, unsupported = {}, {}, []
    for part in ddl_parts(ddl):
        column = re.match(r"^`((?:``|[^`])+)`\s", part)
        index = re.match(r"^(?:(?:UNIQUE|FULLTEXT|SPATIAL)\s+)?KEY\s+`((?:``|[^`])+)`", part, re.I)
        if column: fields[column[1].replace("``", "`")] = part
        elif part.upper().startswith("PRIMARY KEY"): indexes["PRIMARY"] = part
        elif index: indexes[index[1].replace("``", "`")] = part
        else: unsupported.append(part)
    return fields, indexes, unsupported


def metadata(asset, ref):
    ddl = adapters.table_ddl(asset, ref["database"], ref["table"])
    fields, indexes, unsupported = definitions(ddl)
    columns = adapters.columns(asset, ref["database"], ref["table"])
    with adapters.connection(asset, ref["database"]) as conn:
        rows, _ = adapters.run(conn, f"SELECT COUNT(*) AS total FROM {quote(ref['table'])}", db_type=asset.db_type)
    return {"ddl": ddl, "fields": fields, "indexes": indexes, "unsupported": unsupported, "columns": columns,
            "primaryKey": [column["name"] for column in columns if column["column_key"] == "PRI"],
            "rows": int(rows[0]["total"]), "fingerprint": hashlib.sha256(re.sub(r"\bAUTO_INCREMENT=\d+", "", ddl).encode()).hexdigest()}


def writable_fields(source, target):
    return [name for name, definition in source["fields"].items() if name in target["fields"] and not re.search(r"\bAS\s*\(", definition, re.I) and not re.search(r"\bAS\s*\(", target["fields"][name], re.I)]


def data_preview(source_asset, source_ref, target_asset, target_ref, source, target):
    primary = source["primaryKey"]
    fields = writable_fields(source, target)
    if not primary or primary != target["primaryKey"] or not set(primary) <= set(fields): return None
    names = ", ".join(quote(name) for name in fields)
    result = {"sampledRows": 0, "insertRows": 0, "updateRows": 0, "unchangedRows": 0, "keyConflicts": 0, "exact": source["rows"] <= 1000}
    with adapters.connection(source_asset, source_ref["database"]) as source_conn, adapters.connection(target_asset, target_ref["database"]) as target_conn:
        rows, _ = adapters.run(source_conn, f"SELECT {names} FROM {quote(source_ref['table'])} ORDER BY " + ", ".join(quote(name) for name in primary) + " LIMIT %s", (1000,), db_type=source_asset.db_type, max_rows=1000, json_safe=False)
        for row in rows:
            existing, _ = adapters.run(target_conn, f"SELECT {names} FROM {quote(target_ref['table'])} WHERE " + " AND ".join(f"{quote(name)}=%s" for name in primary), tuple(row[name] for name in primary), db_type=target_asset.db_type, json_safe=False)
            result["sampledRows"] += 1
            if not existing: result["insertRows"] += 1
            else:
                result["keyConflicts"] += 1
                result["updateRows" if any(existing[0][name] != row[name] for name in fields if name not in primary) else "unchangedRows"] += 1
    return result


def differences(source, target):
    return [{"name": name, "change": "add" if name not in target else "modify", "source": definition, "target": target.get(name, "")}
            for name, definition in source.items() if target.get(name) != definition] + [
                {"name": name, "change": "target-only", "source": "", "target": definition}
                for name, definition in target.items() if name not in source]


def structure_sql(source, target, table, delete_extras=False):
    clauses = []
    for name, definition in target["indexes"].items():
        if (name in source["indexes"] and source["indexes"][name] != definition) or (delete_extras and name not in source["indexes"]):
            clauses.append("DROP PRIMARY KEY" if name == "PRIMARY" else f"DROP INDEX {quote(name)}")
    for name, definition in source["fields"].items():
        if target["fields"].get(name) != definition:
            clauses.append(("MODIFY COLUMN " if name in target["fields"] else "ADD COLUMN ") + definition)
    if delete_extras:
        clauses.extend(f"DROP COLUMN {quote(name)}" for name in target["fields"] if name not in source["fields"])
    for name, definition in source["indexes"].items():
        if target["indexes"].get(name) != definition: clauses.append("ADD " + definition)
    return [f"ALTER TABLE {quote(table)} " + ",\n  ".join(clauses)] if clauses else []


def build_preview(source, target, mode):
    fields = differences(source["fields"], target["fields"])
    indexes = differences(source["indexes"], target["indexes"])
    matching_primary_key = bool(source["primaryKey"]) and source["primaryKey"] == target["primaryKey"] and set(source["primaryKey"]) <= set(writable_fields(source, target))
    warnings, conflicts = [], []
    if source["unsupported"] != target["unsupported"]:
        warnings.append("外键或 CHECK 约束存在差异；结构同步保留这些约束，请另行核对")
    if mode == "structure":
        warnings.append("MySQL 结构变更会隐式提交，执行后不能通过回滚恢复")
    else:
        if not re.search(r"\bENGINE\s*=\s*InnoDB\b", target["ddl"], re.I): conflicts.append("目标必须为 InnoDB 表，才能保证失败时回滚")
        if mode == "data" and not matching_primary_key:
            conflicts.append("数据同步要求来源和目标具有相同且可写的非空主键")
        missing = set(source["fields"]) - set(target["fields"])
        if missing: conflicts.append("目标缺少字段：" + "、".join(sorted(missing)))
        for column in target["columns"]:
            if column["name"] not in source["fields"] and column["nullable"] == "NO" and column.get("default") is None and "AUTO_INCREMENT" not in target["fields"][column["name"]].upper() and "GENERATED" not in target["fields"][column["name"]].upper():
                conflicts.append("目标必填字段没有来源：" + column["name"])
        warnings.append("目标独有数据保留；键冲突在执行时按所选策略处理。请先核对字段类型兼容性")
    return {"fields": fields, "indexes": indexes, "primaryKey": source["primaryKey"], "matchingPrimaryKey": matching_primary_key,
            "sourceRows": source["rows"], "targetRows": target["rows"], "estimatedRows": source["rows"],
            "warnings": warnings, "conflicts": conflicts, "canExecute": not conflicts,
            "sql": structure_sql(source, target, "__target__") if mode == "structure" else [],
            "requiresExplicitConfirmation": True}


@api_view(["POST"])
def preview(request):
    try:
        mode = request.data.get("mode") or request.data.get("operation")
        if mode not in {"structure", "data", "copy"}: raise DumpError("表操作类型无效")
        require_permissions(request.user, mode)
        source_asset, source_ref = resolve_reference(request.data.get("source"))
        target_asset, target_ref = resolve_reference(request.data.get("target"), write=True)
        if (source_asset.host, source_asset.port, source_ref["database"], source_ref["table"]) == (target_asset.host, target_asset.port, target_ref["database"], target_ref["table"]):
            raise DumpError("来源和目标不能是同一张表")
        source = metadata(source_asset, source_ref); target = metadata(target_asset, target_ref)
        result = build_preview(source, target, mode)
        fields = writable_fields(source, target)
        result["sql"] = structure_sql(source, target, target_ref["table"]) if mode == "structure" else [
            f"INSERT INTO {quote(target_ref['table'])} ({', '.join(quote(name) for name in fields)}) VALUES ({', '.join(['%s'] * len(fields))})"]
        result["sqlDeleteExtras"] = structure_sql(source, target, target_ref["table"], True) if mode == "structure" else []
        if mode != "structure" and result["canExecute"]:
            result["dataDifference"] = data_preview(source_asset, source_ref, target_asset, target_ref, source, target)
            result["warnings"].append("数据差异最多预览前 1000 行，执行时重新读取并处理全部数据；其他唯一键冲突由数据库约束校验")
        from .transfers import create_task
        task = create_task(request.user, asset=target_asset, direction="import", scope="table-operation", format="internal",
                           database=target_ref["database"], schema=target_ref["schema"], object_name=target_ref["table"],
                           source_name={"structure": "结构同步", "data": "数据同步", "copy": "复制数据"}[mode],
                           status="awaiting_confirmation", stage="awaiting_confirmation", preview=result,
                           parameters={"mode": mode, "source": source_ref, "target": target_ref, "sourceFingerprint": source["fingerprint"], "targetFingerprint": target["fingerprint"]})
        record_operation_log(request, "应用管理", "表操作预览", target_asset.name, f"操作={mode}; 表={target_ref['table']}")
        return Response({**result, "previewId": str(task.pk)})
    except PermissionError as exc: return Response({"error": str(exc)}, status=403)
    except (ValueError, TypeError, ValidationError) as exc: return bad_request(str(exc))
    except Exception as exc: return bad_request(adapters.connection_error(exc))


@api_view(["POST"])
def execute(request):
    try:
        with transaction.atomic():
            task = DatabaseTransferTask.objects.select_for_update().get(pk=request.data.get("previewId"), owner=request.user, scope="table-operation")
            if task.status != "awaiting_confirmation" or task.created_at < timezone.now() - timedelta(minutes=15): raise DumpError("预览已执行或已过期，请重新预览")
            require_permissions(request.user, task.parameters["mode"])
            resolve_reference(task.parameters["source"]); resolve_reference(task.parameters["target"], write=True)
            if request.data.get("confirmed") is not True: raise DumpError("请明确确认执行")
            if not task.preview.get("canExecute"): raise DumpError("请先解决预览中的冲突")
            policy = request.data.get("conflictPolicy", "update" if task.parameters["mode"] == "data" else "append")
            if policy not in {"append", "skip", "update"}: raise DumpError("冲突策略无效")
            if policy == "update" and not task.preview.get("matchingPrimaryKey"): raise DumpError("来源表和目标表需要具有相同且可写的主键，才能按主键更新")
            delete_extras = request.data.get("deleteTargetExtras", False)
            if not isinstance(delete_extras, bool): raise DumpError("删除目标独有结构选项无效")
            from .transfers import update, serialize
            update(task, parameters={**task.parameters, "deleteTargetExtras": delete_extras}, conflict_policy=policy, status="queued", stage="queued")
        record_operation_log(request, "应用管理", "确认表操作", task.asset.name, f"任务={task.pk}; 表={task.object_name}; 操作={task.parameters['mode']}")
        return Response(serialize(task), status=202)
    except DatabaseTransferTask.DoesNotExist: return bad_request("预览不存在")
    except PermissionError as exc: return Response({"error": str(exc)}, status=403)
    except (ValueError, TypeError, ValidationError) as exc: return bad_request(str(exc))


def execute_task(task, report):
    mode = task.parameters["mode"]
    require_permissions(task.owner, mode)
    source_asset, source_ref = resolve_reference(task.parameters["source"])
    target_asset, target_ref = resolve_reference(task.parameters["target"], write=True)
    source = metadata(source_asset, source_ref); target = metadata(target_asset, target_ref)
    if source["fingerprint"] != task.parameters["sourceFingerprint"] or target["fingerprint"] != task.parameters["targetFingerprint"]:
        raise DumpError("表结构已变化，请重新预览")
    result = build_preview(source, target, mode)
    if not result["canExecute"]: raise DumpError("表结构不兼容，请重新预览")
    if mode != "structure" and task.conflict_policy == "update" and not result["matchingPrimaryKey"]:
        raise DumpError("来源表和目标表需要具有相同且可写的主键，才能按主键更新")
    if mode == "structure":
        sql = structure_sql(source, target, target_ref["table"], task.parameters.get("deleteTargetExtras", False))
        if sql:
            from .transfers import update
            update(task, checkpoints={"ddlMayBeCommitted": True, "currentTable": target_ref["table"]})
            report(task, stage="syncing_structure")
            adapters.execute(target_asset, target_ref["database"], sql[0], commit=True)
        return
    fields = writable_fields(source, target)
    if not fields: raise DumpError("没有可写入字段")
    primary = source["primaryKey"] if source["primaryKey"] == target["primaryKey"] else []
    names = ", ".join(quote(name) for name in fields)
    insert = f"INSERT INTO {quote(target_ref['table'])} ({names}) VALUES ({', '.join(['%s'] * len(fields))})"
    with ExitStack() as stack:
        source_conn = stack.enter_context(adapters.connection(source_asset, source_ref["database"]))
        target_conn = stack.enter_context(adapters.connection(target_asset, target_ref["database"]))
        try:
            adapters.run(source_conn, "START TRANSACTION WITH CONSISTENT SNAPSHOT", db_type=source_asset.db_type)
            adapters.run(target_conn, "START TRANSACTION", db_type=target_asset.db_type)
            rows_done, offset = 0, 0
            from django.conf import settings
            while True:
                require_permissions(task.owner, mode); enforce_policy(source_asset); enforce_policy(target_asset, write=True)
                resource_guard(task)
                report(task, stage="syncing_data", rows=rows_done, total=source["rows"])
                rows, _ = adapters.run(source_conn, f"SELECT {names} FROM {quote(source_ref['table'])}" + (" ORDER BY " + ", ".join(quote(name) for name in primary) if primary else "") + " LIMIT %s OFFSET %s", (500, offset), db_type=source_asset.db_type, json_safe=False)
                if not rows: break
                for row in rows:
                    existing = []
                    where = " AND ".join(f"{quote(name)}=%s" for name in primary)
                    keys = tuple(row[name] for name in primary)
                    if primary and task.conflict_policy == "update":
                        existing, _ = adapters.run(target_conn, f"SELECT {names} FROM {quote(target_ref['table'])} WHERE {where}", keys, db_type=target_asset.db_type, json_safe=False)
                    if existing:
                        changed = [name for name in fields if name not in primary and existing[0][name] != row[name]]
                        if changed: adapters.run(target_conn, f"UPDATE {quote(target_ref['table'])} SET " + ", ".join(f"{quote(name)}=%s" for name in changed) + f" WHERE {where}", tuple(row[name] for name in changed) + keys, db_type=target_asset.db_type)
                    else:
                        try: adapters.run(target_conn, insert, tuple(row[name] for name in fields), db_type=target_asset.db_type)
                        except Exception as exc:
                            if task.conflict_policy != "skip" or not exc.args or exc.args[0] != 1062: raise
                    rows_done += 1
                    if settings.DATABASE_TRANSFER_MAX_ROWS and rows_done > settings.DATABASE_TRANSFER_MAX_ROWS: raise DumpError("行数超过系统配置上限")
                offset += len(rows)
            report(task, stage="committing", rows=rows_done)
            target_conn.commit()
        except BaseException:
            target_conn.rollback()
            raise
