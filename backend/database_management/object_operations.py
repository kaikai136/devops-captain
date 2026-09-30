import re
import sqlparse

from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import require_feature_permission
from operations.responses import bad_request, get_object_or_error
from system_management.services import record_operation_log

from . import adapters
from .models import DatabaseAsset


OBJECT_TYPES = {"table", "view", "function", "procedure"}
IDENTIFIER = re.compile(r"^[\w$][\w$-]*$", re.UNICODE)


def qualified(database, schema, name, kind):
    parts = [value for value in (schema, name) if value]
    if database and kind in {"clickhouse"}:
        parts.insert(0, database)
    return ".".join(adapters.quote(value, kind) for value in parts)


def checked(request, asset_id):
    denied = require_feature_permission(request, "databaseManagement", "manage_schema")
    if denied:
        return None, denied
    return get_object_or_error(DatabaseAsset, pk=asset_id, error_message="数据库资产不存在")


def validate_name(value, label="对象名称"):
    value = str(value or "").strip()
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label}不合法")
    return value


def single_statement(definition, allow_routine_body=False):
    """Reject stacked SQL while allowing semicolons inside routine bodies."""
    text = definition.strip()
    if len(sqlparse.split(text)) != 1:
        raise ValueError("对象定义只能包含一条 SQL 语句")
    return text.rstrip(";")


def checked_definition(definition, object_type, name, schema):
    text = single_statement(definition, object_type in {"function", "procedure"})
    identifier = r'(?:"[\w$-]+"|`[\w$-]+`|\[[\w$-]+\]|[\w$-]+)'
    options = r'(?:ALGORITHM\s*=\s*(?:UNDEFINED|MERGE|TEMPTABLE)\s+)?(?:DEFINER\s*=\s*(?:`[^`]+`@`[^`]+`|CURRENT_USER(?:\(\))?)\s+)?(?:SQL\s+SECURITY\s+(?:DEFINER|INVOKER)\s+)?'
    match = re.match(rf'^CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?{options}{object_type}\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<target>{identifier}(?:\s*\.\s*{identifier})?)\s*(?=\(|@|AS\b|RETURNS?\b|IS\b)', text, re.I)
    if not match:
        raise ValueError("对象定义类型或名称不匹配")
    parts = [part.strip().strip('`"[]') for part in match.group('target').split('.')]
    if parts[-1] != name or len(parts) > 1 and parts[0] != (schema or ""):
        raise ValueError("对象定义必须与目标名称和 Schema 一致")
    return text


def statement(asset, payload):
    kind = asset.db_type
    action = str(payload.get("action", ""))
    object_type = str(payload.get("objectType", "table"))
    if object_type not in OBJECT_TYPES:
        raise ValueError("不支持的对象类型")
    capabilities = next((item['capabilities'] for item in adapters.type_metadata() if item['key'] == kind), [])
    if object_type in {"function", "procedure"} and "routines" not in capabilities:
        raise ValueError("该数据库不支持例程操作")
    if action in {"truncate", "delete_rows", "optimize"} and object_type != "table":
        raise ValueError("此操作只支持表")
    name = validate_name(payload.get("name"))
    schema = payload.get("schema")
    target = qualified(payload.get("database"), schema, name, kind)
    new_name = validate_name(payload.get("newName"), "新名称") if payload.get("newName") else ""
    definition = str(payload.get("definition", "")).strip()
    if len(definition) > 100000:
        raise ValueError("对象定义最多 100000 字符")
    if action == "create":
        if object_type == "table":
            if not definition: raise ValueError("建表需要提供定义")
            if not re.match(r"^CREATE\s+TABLE\b", definition, re.I): raise ValueError("建表定义必须以 CREATE TABLE 开头")
            return checked_definition(definition, object_type, name, payload.get('database') if kind == 'clickhouse' else schema)
        if object_type == "view":
            if not definition: raise ValueError("视图需要提供 SELECT 定义")
            if not re.match(r"^(?:WITH\b|SELECT\b)", definition, re.I): raise ValueError("视图定义必须是 SELECT 查询")
            return f"CREATE VIEW {target} AS {single_statement(definition)}"
        if kind in {"sqlite", "clickhouse"}:
            raise ValueError(f"{kind} 不支持创建{object_type}")
        if not definition: raise ValueError("例程需要提供定义")
        prefix = "FUNCTION" if object_type == "function" else "PROCEDURE"
        return checked_definition(definition, object_type, name, schema)
    if action == "replace":
        if object_type not in {"view", "function", "procedure"}: raise ValueError("只有视图和例程支持覆盖定义")
        if not definition: raise ValueError("对象定义不能为空")
        text = checked_definition(definition, object_type, name, payload.get('database') if kind == 'clickhouse' else schema)
        if kind in {"postgresql", "kingbase", "oracle", "dameng"}:
            return re.sub(r'^CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?', 'CREATE OR REPLACE ', text, count=1, flags=re.I)
        if kind == "sqlserver":
            return re.sub(r'^CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?', 'CREATE OR ALTER ', text, count=1, flags=re.I)
        if kind in {"mysql", "mariadb"} and object_type == "view":
            return re.sub(r'^CREATE\s+(?:OR\s+REPLACE\s+)?', 'CREATE OR REPLACE ', text, count=1, flags=re.I)
        if kind == 'clickhouse' and object_type == 'view':
            return re.sub(r'^CREATE\s+(?:OR\s+REPLACE\s+)?', 'CREATE OR REPLACE ', text, count=1, flags=re.I)
        if kind == 'sqlite' and object_type == 'view':
            return [f'DROP VIEW {target}', text]
        raise ValueError("该数据库不支持安全覆盖此对象定义")
    if action == "rename":
        renamed = adapters.quote(new_name, kind)
        if not new_name: raise ValueError("新名称不能为空")
        if object_type == "table":
            if kind == "sqlserver": return f"EXEC sp_rename N'{target}', N'{new_name}'"
            if kind in {"oracle", "dameng"}: return f"ALTER TABLE {target} RENAME TO {renamed}"
            if kind == "clickhouse": return f"RENAME TABLE {target} TO {qualified(payload.get('database'), schema, new_name, kind)}"
            return f"ALTER TABLE {target} RENAME TO {renamed}"
        if object_type in {'function', 'procedure'} and kind in {'postgresql', 'kingbase'}:
            signature = str(payload.get('signature') or '')
            if not re.fullmatch(r'[\w\s.,\[\]"]*', signature): raise ValueError('例程签名不合法')
            return f'ALTER {object_type.upper()} {target}({signature}) RENAME TO {renamed}'
        if object_type != "view": raise ValueError("该数据库不支持安全重命名此对象")
        if kind in {"postgresql", "kingbase"}: return f"ALTER VIEW {target} RENAME TO {renamed}"
        if kind in {"mysql", "mariadb"}: return f"RENAME TABLE {target} TO {qualified(payload.get('database'), schema, new_name, kind)}"
        if kind == "sqlserver": return f"EXEC sp_rename N'{target}', N'{new_name}'"
        if kind in {"oracle", "dameng"}: raise ValueError("该数据库不支持跨 Schema 安全重命名视图")
        raise ValueError(f"{kind} 不支持重命名视图")
    if action in {"drop", "delete"}:
        if object_type in {"function", "procedure"} and kind in {"postgresql", "kingbase"}:
            signature = str(payload.get('signature') or '')
            if not re.fullmatch(r'[\w\s.,\[\]"]*', signature): raise ValueError("例程签名不合法")
            target += f"({signature})"
        if object_type == "table": prefix = "TABLE"
        elif object_type == "view": prefix = "VIEW"
        elif object_type == "function": prefix = "FUNCTION"
        else: prefix = "PROCEDURE"
        return f"DROP {prefix} {target}"
    if action == "truncate":
        if "truncate" not in capabilities: raise ValueError("该数据库不支持 TRUNCATE")
        return f"TRUNCATE TABLE {target}"
    if action == "delete_rows": return f"DELETE FROM {target}"
    if action == "optimize":
        if kind in {"mysql", "mariadb"}: return f"OPTIMIZE TABLE {target}"
        if kind == "postgresql": return f"VACUUM ANALYZE {target}"
        raise ValueError(f"{kind} 不支持优化表")
    raise ValueError("不支持的对象操作")


@api_view(["POST"])
def object_action(request, asset_id):
    asset, denied = checked(request, asset_id)
    if denied: return denied
    try:
        sql = statement(asset, request.data)
        with adapters.connection(asset, request.data.get("database")) as conn:
            try:
                if request.data.get('action') == 'optimize' and asset.db_type == 'postgresql': conn.autocommit = True
                if isinstance(sql, list) and asset.db_type == 'sqlite': adapters.run(conn, 'BEGIN', db_type=asset.db_type)
                for command in sql if isinstance(sql, list) else [sql]: adapters.run(conn, command, db_type=asset.db_type)
                if hasattr(conn, "commit"): conn.commit()
            except Exception:
                if hasattr(conn, "rollback"): conn.rollback()
                raise
        record_operation_log(request, "应用管理", "数据库对象操作", asset.name,
                             f"动作={request.data.get('action')}; 类型={request.data.get('objectType', 'table')}; 名称={request.data.get('name')}")
        return Response({"ok": True})
    except Exception as exc:
        return bad_request(adapters.connection_error(exc))
