"""Small, request-scoped adapters for databases managed by the UI."""

import importlib
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

from .services import decrypt_password


TYPE_INFO = {
    "mysql": ("MySQL", 3306, "pymysql"),
    "mariadb": ("MariaDB", 3306, "pymysql"),
    "postgresql": ("PostgreSQL", 5432, "psycopg"),
    "kingbase": ("Kingbase", 54321, "psycopg"),
    "sqlserver": ("SQL Server", 1433, "pymssql"),
    "sqlite": ("SQLite", 0, "sqlite3"),
    "redis": ("Redis", 6379, "redis"),
    "clickhouse": ("ClickHouse", 8123, "clickhouse_connect"),
    "oracle": ("Oracle", 1521, "oracledb"),
    "dameng": ("Dameng", 5236, "dmPython"),
}
IDENTIFIER = re.compile(r"^[\w$][\w$-]*$", re.UNICODE)


def type_metadata():
    return [{"key": key, "label": label, "defaultPort": port,
             "fields": (["file"] if key == "sqlite" else
                        ["db", "ssl"] if key == "redis" else
                        ["service", "sid"] if key == "oracle" else
                        ["https"] if key == "clickhouse" else
                        ["instance"] if key == "sqlserver" else
                        ["schema", "ssl"] if key in {"postgresql", "kingbase"} else
                        ["ssl"] if key in {"mysql", "mariadb"} else []),
             "capabilities": (["keys", "commands", "json", "csv"] if key == "redis" else
                              ["tree", "data", "sql", "rows", "transaction", "csv", "sql_export"])}
            for key, (label, port, _) in TYPE_INFO.items()]


def sqlite_path(filename):
    root = Path(settings.DATABASE_ASSET_SQLITE_ROOT).resolve()
    if not filename or Path(filename).is_absolute() or Path(filename).name != filename:
        raise ValueError("请选择 SQLite 目录中的文件名")
    path = (root / filename).resolve()
    if path.parent != root or path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("SQLite 文件必须位于限定目录且使用 .db/.sqlite/.sqlite3 后缀")
    app_database = Path(settings.DATABASES["default"]["NAME"]).resolve()
    if path == app_database or (path.exists() and app_database.exists() and path.samefile(app_database)):
        raise ValueError("不能连接应用自身数据库")
    return path


def quote(name, db_type):
    name = str(name or "")
    if not IDENTIFIER.fullmatch(name):
        raise ValueError("数据库对象名称不合法")
    if db_type in {"mysql", "mariadb", "clickhouse"}:
        return "`" + name.replace("`", "``") + "`"
    if db_type == "sqlserver":
        return "[" + name.replace("]", "]]" ) + "]"
    return '"' + name.replace('"', '""') + '"'


def marker(db_type, index=1):
    return "?" if db_type in {"sqlite", "dameng"} else f":{index}" if db_type == "oracle" else "%s"


def connection_error(exc):
    if isinstance(exc, ValueError):
        return str(exc)
    return "数据库操作失败，请检查连接配置、对象名称及账号权限"


def module_for(db_type):
    try:
        return importlib.import_module(TYPE_INFO[db_type][2])
    except ImportError as exc:
        raise ValueError(f"{TYPE_INFO[db_type][0]} 驱动未安装") from exc


def connect(asset, database=None):
    kind = asset.db_type
    if kind not in TYPE_INFO:
        raise ValueError("不支持的数据库类型")
    options = asset.options or {}
    password = decrypt_password(asset.password_encrypted)
    if kind == "sqlite":
        path = sqlite_path(options.get("file"))
        if not path.is_file():
            raise ValueError("SQLite 文件不存在")
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=rw", uri=True, timeout=10)
        conn.set_authorizer(lambda action, *_args: sqlite3.SQLITE_DENY if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH} else sqlite3.SQLITE_OK)
        return conn
    module = module_for(kind)
    common = {"host": asset.host, "port": asset.port, "user": asset.username, "password": password}
    if kind in {"mysql", "mariadb"}:
        if options.get("ssl"):
            common["ssl"] = {}
        return module.connect(**common, database=database or asset.database or None,
                              charset="utf8mb4", connect_timeout=5, read_timeout=20,
                              cursorclass=module.cursors.DictCursor)
    if kind in {"postgresql", "kingbase"}:
        return module.connect(**common, dbname=database or asset.database or "postgres",
                              connect_timeout=5, row_factory=module.rows.dict_row,
                              sslmode="require" if options.get("ssl") else "prefer",
                              options="-c statement_timeout=20000")
    if kind == "sqlserver":
        server = asset.host + ("\\" + str(options["instance"]) if options.get("instance") else "")
        return module.connect(server=server, port=asset.port, user=asset.username,
                              password=password, database=database or asset.database or "master", login_timeout=5, timeout=20)
    if kind == "redis":
        return module.Redis(**common, db=int(options.get("db", 0)), socket_connect_timeout=5,
                            socket_timeout=20, decode_responses=True, ssl=bool(options.get("ssl")))
    if kind == "clickhouse":
        return module.get_client(**common, database=database or asset.database or "default",
                                 secure=bool(options.get("https")), connect_timeout=5, send_receive_timeout=20,
                                 settings={"max_execution_time": 20, "max_result_rows": 501,
                                           "result_overflow_mode": "throw"})
    if kind == "oracle":
        service = options.get("service") or options.get("sid") or asset.database
        if not service:
            raise ValueError("Oracle 需要 Service Name 或 SID")
        dsn = module.makedsn(asset.host, asset.port, service_name=service) if options.get("service") or not options.get("sid") else module.makedsn(asset.host, asset.port, sid=service)
        return module.connect(user=asset.username, password=password, dsn=dsn, tcp_connect_timeout=5)
    return module.connect(user=asset.username, password=password, server=asset.host,
                          port=asset.port, database=database or asset.database)


@contextmanager
def connection(asset, database=None):
    conn = connect(asset, database)
    try:
        yield conn
    finally:
        conn.close()


def test(asset):
    with connection(asset) as conn:
        if asset.db_type == "redis":
            conn.ping()
        elif asset.db_type == "clickhouse":
            conn.ping()
        else:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT 1")
            finally:
                cursor.close()


def run(conn, sql, params=(), *, db_type=None, max_rows=500):
    if db_type == "clickhouse":
        if re.match(r"^\s*(SELECT|WITH|SHOW|DESCRIBE|EXPLAIN)\b", sql, re.I):
            if isinstance(params, (tuple, list)):
                values = {f"p{index}": str(value) for index, value in enumerate(params, 1)}
                param_index = 0
                def bind_clickhouse(_match):
                    nonlocal param_index
                    param_index += 1
                    return "{" + f"p{param_index}:String" + "}"
                sql = re.sub(r"%s", bind_clickhouse, sql)
                params = values
            result = conn.query(sql, parameters=params)
            if len(result.result_rows) > max_rows:
                raise ValueError(f"单次查询最多返回 {max_rows} 行")
            rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
            if len(json.dumps(rows, default=str)) > 2_000_000:
                raise ValueError("单次查询结果不得超过 2MB")
            return rows, len(rows)
        conn.command(sql, parameters=params)
        return [], 0
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        if not cursor.description:
            return [], max(cursor.rowcount, 0)
        columns = [item[0] for item in cursor.description]
        rows = cursor.fetchmany(max_rows + 1)
        if len(rows) > max_rows:
            raise ValueError(f"单次查询最多返回 {max_rows} 行")
        result = [dict(row) if isinstance(row, dict) else dict(zip(columns, row)) for row in rows]
        if len(json.dumps(result, default=str)) > 2_000_000:
            raise ValueError("单次查询结果不得超过 2MB")
        return result, len(rows)
    finally:
        cursor.close()


def metadata_rows(rows):
    return [{str(key).lower(): value for key, value in row.items()} for row in rows]


def schema_names(asset):
    kind = asset.db_type
    if kind == "redis":
        return [str((asset.options or {}).get("db", 0))]
    if kind == "sqlite":
        return ["main"]
    if kind == "oracle":
        return [asset.username.upper()]
    if kind == "dameng":
        return [asset.username.upper()]
    with connection(asset) as conn:
        sql = ("SHOW DATABASES" if kind in {"mysql", "mariadb", "clickhouse"} else
               "SELECT datname FROM pg_database WHERE datallowconn ORDER BY datname" if kind in {"postgresql", "kingbase"} else
               "SELECT name FROM sys.databases ORDER BY name")
        rows, _ = run(conn, sql, db_type=kind)
        return [str(next(iter(row.values()))) for row in rows]


def schemas(asset, database):
    kind = asset.db_type
    if kind in {"postgresql", "kingbase"}:
        sql = "SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT LIKE 'pg_%' AND schema_name <> 'information_schema' ORDER BY schema_name"
    elif kind == "sqlserver":
        sql = "SELECT name FROM sys.schemas ORDER BY name"
    elif kind in {"oracle", "dameng"}:
        return [asset.username.upper()]
    else:
        return []
    with connection(asset, database) as conn:
        rows, _ = run(conn, sql, db_type=kind)
    return [str(next(iter(row.values()))) for row in rows]


def object_list(asset, database, schema=None, object_type=None):
    kind = asset.db_type
    if kind == "redis":
        return []
    if object_type in {"procedure", "function"}:
        if kind == "sqlite" or kind == "clickhouse":
            return []
        routine_type = "PROCEDURE" if object_type == "procedure" else "FUNCTION"
        if kind in {"mysql", "mariadb"}:
            sql = "SELECT ROUTINE_NAME AS name, ROUTINE_TYPE AS type FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_TYPE=%s ORDER BY ROUTINE_NAME"
            params = (database or asset.database, routine_type)
        elif kind in {"postgresql", "kingbase"}:
            sql = "SELECT routine_name AS name, routine_type AS type FROM information_schema.routines WHERE routine_schema=%s AND routine_type=%s ORDER BY routine_name"
            params = (schema or "public", routine_type)
        elif kind == "sqlserver":
            codes = "'P'" if object_type == "procedure" else "'FN','IF','TF'"
            sql = f"SELECT name, type_desc AS type FROM sys.objects WHERE type IN ({codes}) ORDER BY name"
            params = ()
        else:
            sql = f"SELECT OBJECT_NAME AS name, OBJECT_TYPE AS type FROM ALL_OBJECTS WHERE OWNER={marker(kind)} AND OBJECT_TYPE={marker(kind, 2)} ORDER BY OBJECT_NAME"
            params = (schema or asset.username.upper(), routine_type)
        with connection(asset, database if kind not in {"oracle", "dameng"} else None) as conn:
            rows, _ = run(conn, sql, params, db_type=kind)
        rows = metadata_rows(rows)
        return [{"name": row["name"], "type": row["type"], "rows_count": None, "comment": ""} for row in rows]
    if kind in {"postgresql", "kingbase"}:
        sql = "SELECT table_name AS name, table_type AS type FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name"
        params = (schema or "public",)
    elif kind == "sqlite":
        sql = "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
        params = ()
    elif kind in {"mysql", "mariadb"}:
        sql = ("SELECT table_name AS name, table_type AS type, table_rows AS rows_count, "
               "engine, update_time FROM information_schema.tables WHERE table_schema=" +
               marker(kind) + " ORDER BY table_name")
        params = (database or asset.database,)
    elif kind == "clickhouse":
        sql = ("SELECT name, if(engine IN ('View', 'MaterializedView', 'LiveView'), 'VIEW', 'TABLE') AS type, "
               "total_rows AS rows_count, engine, metadata_modification_time AS update_time "
               "FROM system.tables WHERE database={db:String} ORDER BY name")
        params = {"db": database or asset.database or "default"}
    elif kind == "sqlserver":
        sql = "SELECT TABLE_NAME AS name, TABLE_TYPE AS type FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME"
        params = (schema or "dbo",)
    else:
        sql = (f"SELECT TABLE_NAME AS name, 'TABLE' AS type FROM ALL_TABLES WHERE OWNER={marker(kind)} "
               f"UNION ALL SELECT VIEW_NAME AS name, 'VIEW' AS type FROM ALL_VIEWS WHERE OWNER={marker(kind)} ORDER BY name")
        params = (schema or asset.username.upper(),) * (2 if kind == "dameng" else 1)
    with connection(asset, database if kind not in {"oracle", "dameng", "sqlite"} else None) as conn:
        rows, _ = run(conn, sql, params, db_type=kind)
    rows = metadata_rows(rows)
    if object_type in {"table", "view"}:
        rows = [row for row in rows if ("VIEW" in str(row["type"]).upper()) == (object_type == "view")]
    return [{"name": row["name"], "type": row["type"], "rows_count": row.get("rows_count"),
             "engine": row.get("engine"), "update_time": row.get("update_time"), "comment": ""}
            for row in rows]


def columns(asset, database, table, schema=None):
    kind = asset.db_type
    if kind == "sqlite":
        sql, params = f"PRAGMA table_info({quote(table, kind)})", ()
    elif kind in {"mysql", "mariadb"}:
        sql, params = f"SELECT COLUMN_NAME AS name, COLUMN_TYPE AS type, IS_NULLABLE AS nullable, COLUMN_KEY AS column_key, COLUMN_DEFAULT AS default_value FROM information_schema.COLUMNS WHERE TABLE_SCHEMA={marker(kind, 1)} AND TABLE_NAME={marker(kind, 2)} ORDER BY ORDINAL_POSITION", (database or asset.database, table)
    elif kind == "clickhouse":
        sql = "SELECT name, type, if(startsWith(type, 'Nullable('), 'YES', 'NO') AS nullable, if(is_in_primary_key, 'PRI', '') AS column_key, default_expression AS default_value FROM system.columns WHERE database={db:String} AND table={table:String} ORDER BY position"
        params = {"db": database or asset.database or "default", "table": table}
    elif kind in {"postgresql", "kingbase", "sqlserver"}:
        owner = schema or ("dbo" if kind == "sqlserver" else "public")
        if kind == "sqlserver":
            sql = "SELECT c.COLUMN_NAME AS name, c.DATA_TYPE AS type, c.IS_NULLABLE AS nullable, CASE WHEN k.COLUMN_NAME IS NULL THEN '' ELSE 'PRI' END AS column_key, c.COLUMN_DEFAULT AS default_value FROM INFORMATION_SCHEMA.COLUMNS c LEFT JOIN (SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku ON ku.CONSTRAINT_NAME=tc.CONSTRAINT_NAME AND ku.TABLE_SCHEMA=tc.TABLE_SCHEMA AND ku.TABLE_NAME=tc.TABLE_NAME WHERE tc.CONSTRAINT_TYPE='PRIMARY KEY') k ON k.TABLE_SCHEMA=c.TABLE_SCHEMA AND k.TABLE_NAME=c.TABLE_NAME AND k.COLUMN_NAME=c.COLUMN_NAME WHERE c.TABLE_SCHEMA=%s AND c.TABLE_NAME=%s ORDER BY c.ORDINAL_POSITION"
        else:
            sql = "SELECT c.column_name AS name, c.data_type AS type, c.is_nullable AS nullable, CASE WHEN k.column_name IS NULL THEN '' ELSE 'PRI' END AS column_key, c.column_default AS default_value FROM information_schema.columns c LEFT JOIN (SELECT ku.table_schema, ku.table_name, ku.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage ku ON ku.constraint_name=tc.constraint_name AND ku.table_schema=tc.table_schema AND ku.table_name=tc.table_name WHERE tc.constraint_type='PRIMARY KEY') k ON k.table_schema=c.table_schema AND k.table_name=c.table_name AND k.column_name=c.column_name WHERE c.table_schema=%s AND c.table_name=%s ORDER BY c.ordinal_position"
        params = (owner, table)
    else:
        sql = f"SELECT c.COLUMN_NAME AS name, c.DATA_TYPE AS type, c.NULLABLE AS nullable, CASE WHEN k.COLUMN_NAME IS NULL THEN '' ELSE 'PRI' END AS column_key, c.DATA_DEFAULT AS default_value FROM ALL_TAB_COLUMNS c LEFT JOIN (SELECT cc.OWNER, cc.TABLE_NAME, cc.COLUMN_NAME FROM ALL_CONSTRAINTS co JOIN ALL_CONS_COLUMNS cc ON cc.OWNER=co.OWNER AND cc.CONSTRAINT_NAME=co.CONSTRAINT_NAME WHERE co.CONSTRAINT_TYPE='P') k ON k.OWNER=c.OWNER AND k.TABLE_NAME=c.TABLE_NAME AND k.COLUMN_NAME=c.COLUMN_NAME WHERE c.OWNER={marker(kind, 1)} AND c.TABLE_NAME={marker(kind, 2)} ORDER BY c.COLUMN_ID"
        params = (schema or asset.username.upper(), table.upper())
    with connection(asset, database) as conn:
        rows, _ = run(conn, sql, params, db_type=kind)
    rows = metadata_rows(rows)
    return [{"name": row.get("name"), "type": row.get("type"),
             "nullable": row.get("nullable", "") if kind != "sqlite" else ("NO" if row.get("notnull") else "YES"),
             "column_key": row.get("column_key") or ("PRI" if row.get("pk") else ""),
             "comment": "", "default": row.get("default_value", row.get("dflt_value"))}
            for row in rows]


def indexes(asset, database, table, schema=None):
    kind = asset.db_type
    if kind == "redis":
        return []
    if kind == "sqlite":
        sql, params = f"PRAGMA index_list({quote(table, kind)})", ()
    elif kind in {"mysql", "mariadb"}:
        sql = "SELECT INDEX_NAME AS name, COLUMN_NAME AS column_name, NON_UNIQUE AS non_unique FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY INDEX_NAME, SEQ_IN_INDEX"
        params = (database or asset.database, table)
    elif kind in {"postgresql", "kingbase"}:
        sql = "SELECT indexname AS name, indexdef AS definition FROM pg_indexes WHERE schemaname=%s AND tablename=%s ORDER BY indexname"
        params = (schema or "public", table)
    elif kind == "sqlserver":
        sql = "SELECT i.name AS name, c.name AS column_name, i.is_unique AS is_unique FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id JOIN sys.tables t ON t.object_id=i.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name=%s AND t.name=%s AND i.name IS NOT NULL ORDER BY i.name, ic.key_ordinal"
        params = (schema or "dbo", table)
    elif kind == "clickhouse":
        sql = "SELECT name, expression AS definition FROM system.data_skipping_indices WHERE database={db:String} AND table={table:String} ORDER BY name"
        params = {"db": database or asset.database or "default", "table": table}
    else:
        sql = f"SELECT c.INDEX_NAME AS name, c.COLUMN_NAME AS column_name, i.UNIQUENESS AS uniqueness FROM ALL_IND_COLUMNS c JOIN ALL_INDEXES i ON i.OWNER=c.INDEX_OWNER AND i.INDEX_NAME=c.INDEX_NAME WHERE c.TABLE_OWNER={marker(kind)} AND c.TABLE_NAME={marker(kind, 2)} ORDER BY c.INDEX_NAME, c.COLUMN_POSITION"
        params = (schema or asset.username.upper(), table.upper())
    with connection(asset, database) as conn:
        rows, _ = run(conn, sql, params, db_type=kind)
        rows = metadata_rows(rows)
        if kind == "sqlite":
            for row in rows:
                details, _ = run(conn, f"PRAGMA index_info({quote(row['name'], kind)})", db_type=kind)
                row["columns"] = [item["name"] for item in metadata_rows(details)]
    grouped = {}
    for row in rows:
        name = row["name"]
        entry = grouped.setdefault(name, {"name": name, "columns": [], "unique": False, "definition": ""})
        if row.get("column_name"):
            entry["columns"].append(row["column_name"])
        elif row.get("columns"):
            entry["columns"] = row["columns"]
        entry["definition"] = row.get("definition") or entry["definition"]
        if kind == "sqlite":
            entry["unique"] = bool(row.get("unique"))
        elif kind in {"mysql", "mariadb"}:
            entry["unique"] = not bool(row.get("non_unique"))
        elif kind == "sqlserver":
            entry["unique"] = bool(row.get("is_unique"))
        elif kind in {"postgresql", "kingbase"}:
            entry["unique"] = "CREATE UNIQUE INDEX" in entry["definition"].upper()
        elif row.get("uniqueness"):
            entry["unique"] = row["uniqueness"] == "UNIQUE"
    return list(grouped.values())


def table_data(asset, database, table, schema=None, page=1, page_size=25, sort=None,
               direction="asc", fields=None, where_field=None, where_value=None,
               max_rows=500):
    kind = asset.db_type
    qualified = ".".join(quote(item, kind) for item in (schema, table) if item) if schema else quote(table, kind)
    selected = ", ".join(quote(field, kind) for field in fields) if fields else "*"
    where = f" WHERE {quote(where_field, kind)}={marker(kind)}" if where_field and where_value is not None else ""
    params = (where_value,) if where else ()
    order = f" ORDER BY {quote(sort, kind)} {'DESC' if direction == 'desc' else 'ASC'}" if sort else ""
    offset = (page - 1) * page_size
    if kind in {"sqlserver", "oracle", "dameng"}:
        sql = f"SELECT {selected} FROM {qualified}{where}{order or ' ORDER BY 1'} OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY"
    else:
        sql = f"SELECT {selected} FROM {qualified}{where}{order} LIMIT {page_size} OFFSET {offset}"
    with connection(asset, database) as conn:
        rows, _ = run(conn, sql, params, db_type=kind, max_rows=max_rows)
        count, _ = run(conn, f"SELECT COUNT(*) AS total FROM {qualified}{where}", params, db_type=kind)
    total = int(next(iter(count[0].values()))) if count else 0
    return {"rows": rows, "total": total, "page": page, "pageSize": page_size,
            "hasNext": offset + page_size < total}


def execute(asset, database, sql, *, commit=False):
    if not sql or len(sql) > 100000:
        raise ValueError("SQL 不能为空且长度不得超过 100000 字符")
    with connection(asset, database) as conn:
        try:
            rows, affected = run(conn, sql, db_type=asset.db_type)
            if commit and hasattr(conn, "commit"):
                conn.commit()
            return {"rows": rows, "affected": affected, "columns": list(rows[0]) if rows else []}
        except Exception:
            if hasattr(conn, "rollback"):
                conn.rollback()
            raise
