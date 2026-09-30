import re

from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import require_feature_permission
from operations.responses import bad_request, get_object_or_error
from system_management.services import record_operation_log

from . import adapters
from .models import DatabaseAsset


def guard(request): return require_feature_permission(request, "databaseManagement", "manage_accounts", "没有数据库账号管理权限")


def literal(value):
    text = str(value)
    if any(char in text for char in ('\\', '\x00', '\r', '\n')):
        raise ValueError("账号参数不能包含反斜线或控制字符")
    return "'" + text.replace("'", "''") + "'"


def password_identifier(value):
    text = str(value)
    if not text or any(char in text for char in ('"', '\x00', '\r', '\n')):
        raise ValueError("密码不能包含双引号或控制字符")
    return '"' + text + '"'


def builtin_account(kind, name):
    normalized = str(name or "").lower()
    fixed = {
        "mysql": {"root", "mysql.sys", "mysql.session", "mysql.infoschema"},
        "mariadb": {"root", "mariadb.sys", "mysql"},
        "postgresql": {"postgres"},
        "kingbase": {"kingbase", "system"},
        "sqlserver": {"sa", "dbo", "guest", "sys", "information_schema"},
        "oracle": {"sys", "system", "sysman", "dbsnmp"},
        "dameng": {"sys", "sysdba", "sysauditor", "syssso"},
        "clickhouse": {"default"},
    }
    return normalized in fixed.get(kind, set()) or kind in {"postgresql", "kingbase"} and normalized.startswith("pg_")


def account_capabilities(kind):
    grants = {
        'mysql': ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'EXECUTE'],
        'mariadb': ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'EXECUTE'],
        'postgresql': ['CONNECT', 'USAGE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'EXECUTE'],
        'kingbase': ['CONNECT', 'USAGE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'EXECUTE'],
        'sqlserver': ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'ALTER', 'EXECUTE'],
        'oracle': ['CONNECT'], 'dameng': ['CONNECT'],
        'clickhouse': ['SELECT', 'INSERT', 'ALTER UPDATE', 'ALTER DELETE', 'CREATE TABLE', 'ALTER TABLE', 'DROP TABLE'],
    }
    return {'passwordReset': True, 'delete': kind != 'sqlserver', 'grants': grants.get(kind, []), 'roles': True}


def available_roles(conn, kind):
    statements = {
        'mysql': 'SELECT DISTINCT FROM_USER AS name, FROM_HOST AS host FROM mysql.role_edges',
        'mariadb': "SELECT User AS name, Host AS host FROM mysql.user WHERE is_role='Y'",
        'postgresql': 'SELECT rolname AS name FROM pg_roles WHERE NOT rolcanlogin',
        'kingbase': 'SELECT rolname AS name FROM pg_roles WHERE NOT rolcanlogin',
        'sqlserver': "SELECT name FROM sys.database_principals WHERE type='R' AND name<>'public'",
        'clickhouse': 'SELECT name FROM system.roles',
        'oracle': 'SELECT ROLE AS name FROM DBA_ROLES',
        'dameng': 'SELECT ROLE AS name FROM DBA_ROLES',
    }
    rows, _ = adapters.run(conn, statements[kind], db_type=kind)
    return [{'name': str(row.get('name') or row.get('NAME') or ''), 'host': str(row.get('host') or '')} for row in rows]


def role_sql(asset, action, name, role, host='%', role_host=''):
    kind = asset.db_type
    if name.casefold() == asset.username.casefold() or builtin_account(kind, name):
        raise ValueError('不能修改当前连接账号或数据库内置账号的角色')
    role_name, user = adapters.quote(role, kind), adapters.quote(name, kind)
    if kind in {'mysql', 'mariadb'}:
        role_name = literal(role) + ('@' + literal(role_host or '%') if kind == 'mysql' else '')
        user = f'{literal(name)}@{literal(host or "%")}'
    if kind == 'sqlserver':
        return f'ALTER ROLE {role_name} {"ADD" if action == "grant_role" else "DROP"} MEMBER {user}'
    return f'{"GRANT" if action == "grant_role" else "REVOKE"} {role_name} {"TO" if action == "grant_role" else "FROM"} {user}'


def account_metadata(conn, asset, name, host, database, schema):
    kind = asset.db_type
    roles, permissions = [], []
    if kind in {'mysql', 'mariadb'}:
        rows, _ = adapters.run(conn, f"SHOW GRANTS FOR {literal(name)}@{literal(host or '%')}", db_type=kind)
        for row in rows:
            grant = str(next(iter(row.values()), ''))
            match = re.match(r'^GRANT\s+(.+?)\s+ON\s+(`[^`]+`|\*)\.\*\s+TO\s+', grant, re.I)
            if match and match[2].strip('`') in {'*', database or asset.database}:
                values = [value.strip().upper() for value in match[1].split(',')]
                permissions.extend(account_capabilities(kind)['grants'] if 'ALL PRIVILEGES' in values else values)
            elif re.match(r'^GRANT\s+.+\s+TO\s+', grant, re.I) and ' ON ' not in grant.upper():
                roles.append(re.split(r'\s+TO\s+', grant[6:], flags=re.I)[0])
    elif kind in {'postgresql', 'kingbase'}:
        rows, _ = adapters.run(conn, "SELECT parent.rolname AS role FROM pg_auth_members m JOIN pg_roles parent ON parent.oid=m.roleid JOIN pg_roles member ON member.oid=m.member WHERE member.rolname=%s", (name,), db_type=kind)
        roles = [str(row['role']) for row in rows if row.get('role')]
        rows, _ = adapters.run(conn, "SELECT DISTINCT privilege_type AS permission FROM information_schema.table_privileges WHERE grantee=%s AND table_schema=%s", (name, schema or 'public'), db_type=kind)
        permissions = [str(row['permission']) for row in rows if row.get('permission')]
        rows, _ = adapters.run(conn, "SELECT has_database_privilege(%s,%s,'CONNECT') AS connect, has_schema_privilege(%s,%s,'USAGE') AS usage, has_schema_privilege(%s,%s,'CREATE') AS create_schema", (name, database or asset.database, name, schema or 'public', name, schema or 'public'), db_type=kind)
        if rows:
            permissions.extend(label for key, label in [('connect', 'CONNECT'), ('usage', 'USAGE'), ('create_schema', 'CREATE')] if rows[0].get(key))
    elif kind == 'sqlserver':
        rows, _ = adapters.run(conn, "SELECT parent.name AS role FROM sys.database_role_members m JOIN sys.database_principals parent ON parent.principal_id=m.role_principal_id JOIN sys.database_principals member ON member.principal_id=m.member_principal_id WHERE member.name=%s", (name,), db_type=kind)
        roles = [str(row['role']) for row in rows if row.get('role')]
        rows, _ = adapters.run(conn, "SELECT DISTINCT permission_name AS permission FROM sys.database_permissions WHERE grantee_principal_id=USER_ID(%s) AND class=3 AND major_id=SCHEMA_ID(%s) AND state IN ('G','W')", (name, schema or 'dbo'), db_type=kind)
        permissions = [str(row['permission']) for row in rows if row.get('permission')]
    elif kind == 'clickhouse':
        rows, _ = adapters.run(conn, "SELECT granted_role_name AS role FROM system.role_grants WHERE user_name={user:String}", {'user': name}, db_type=kind)
        roles = [str(row['role']) for row in rows if row.get('role')]
        rows, _ = adapters.run(conn, "SELECT access_type AS permission FROM system.grants WHERE user_name={user:String} AND (database={database:String} OR database IS NULL) AND table IS NULL", {'user': name, 'database': database or asset.database or 'default'}, db_type=kind)
        permissions = [str(row['permission']) for row in rows if row.get('permission')]
    else:
        rows, _ = adapters.run(conn, f"SELECT GRANTED_ROLE AS role FROM DBA_ROLE_PRIVS WHERE GRANTEE={adapters.marker(kind)}", (name,), db_type=kind)
        roles = [str(row['role']) for row in adapters.metadata_rows(rows) if row.get('role')]
        rows, _ = adapters.run(conn, f"SELECT PRIVILEGE AS permission FROM DBA_SYS_PRIVS WHERE GRANTEE={adapters.marker(kind)}", (name,), db_type=kind)
        permissions = ['CONNECT' for row in adapters.metadata_rows(rows) if row.get('permission') == 'CREATE SESSION']
    return sorted(set(roles)), sorted(set(permissions))


def account_sql(asset, action, name, password="", database="", schema="", grants=None, host="%"):
    kind = asset.db_type
    if kind in {"sqlite", "redis"}: raise ValueError("该数据库类型不支持账号管理")
    user = adapters.quote(name, kind)
    account = f"{literal(name)}@{literal(host or '%')}" if kind in {"mysql", "mariadb"} else user
    if action == 'revoke':
        if name.casefold() == asset.username.casefold() or builtin_account(kind, name):
            raise ValueError('不能撤销当前连接账号或数据库内置账号的权限')
        commands = account_sql(asset, 'grant', name, database=database, schema=schema, grants=grants, host=host)
        def revoke(command):
            prefix, _, target = command.rpartition(' TO ')
            return 'REVOKE ' + prefix[len('GRANT '):] + ' FROM ' + target
        return [revoke(command) for command in commands] if isinstance(commands, list) else revoke(commands)
    if action == "create":
        if not password: raise ValueError("新建账号必须设置密码")
        if kind in {"mysql", "mariadb"}: sql = f"CREATE USER {account} IDENTIFIED BY {literal(password)}"
        elif kind in {"postgresql", "kingbase"}: sql = f"CREATE USER {user} PASSWORD {literal(password)}"
        elif kind == "sqlserver": sql = f"CREATE LOGIN {user} WITH PASSWORD={literal(password)}"
        elif kind == "clickhouse": sql = f"CREATE USER {user} IDENTIFIED WITH sha256_password BY {literal(password)}"
        else: sql = f"CREATE USER {user} IDENTIFIED BY {password_identifier(password)}"
        return sql
    if action == "password":
        if not password: raise ValueError("密码不能为空")
        if kind in {"mysql", "mariadb"}: return f"ALTER USER {account} IDENTIFIED BY {literal(password)}"
        if kind in {"postgresql", "kingbase"}: return f"ALTER USER {user} PASSWORD {literal(password)}"
        if kind == "sqlserver": return f"ALTER LOGIN {user} WITH PASSWORD={literal(password)}"
        if kind == "clickhouse": return f"ALTER USER {user} IDENTIFIED WITH sha256_password BY {literal(password)}"
        return f"ALTER USER {user} IDENTIFIED BY {password_identifier(password)}"
    if action == "delete":
        if name.casefold() == asset.username.casefold(): raise ValueError("不能删除当前连接账号")
        if builtin_account(kind, name): raise ValueError("不能删除数据库内置账号")
        if kind == 'sqlserver': raise ValueError("SQL Server 登录账号删除需要先检查跨数据库映射，当前不支持")
        prefix = "LOGIN" if kind == "sqlserver" else "USER"
        return f"DROP {prefix} {account if kind in {'mysql', 'mariadb'} else user}"
    if action == "grant":
        privileges = grants or []
        if not privileges: raise ValueError("请选择要授权的权限")
        allowed = account_capabilities(kind)['grants']
        if any(value not in allowed for value in privileges): raise ValueError("权限类型不受支持")
        if kind in {"mysql", "mariadb"}:
            target = adapters.quote(database or asset.database, kind) + ".*"
            return f"GRANT {', '.join(privileges)} ON {target} TO {account}"
        if kind in {"postgresql", "kingbase"}:
            target = adapters.quote(schema or "public", kind)
            if any(value in {'ALTER', 'DROP'} for value in privileges): raise ValueError("PostgreSQL 不提供 Schema 级 ALTER/DROP 授权")
            statements = []
            if 'CONNECT' in privileges: statements.append(f"GRANT CONNECT ON DATABASE {adapters.quote(database or asset.database, kind)} TO {user}")
            schema_grants = [value for value in privileges if value in {'USAGE', 'CREATE'}]
            if schema_grants: statements.append(f"GRANT {', '.join(schema_grants)} ON SCHEMA {target} TO {user}")
            table_grants = [value for value in privileges if value in {'SELECT', 'INSERT', 'UPDATE', 'DELETE'}]
            if table_grants: statements.append(f"GRANT {', '.join(table_grants)} ON ALL TABLES IN SCHEMA {target} TO {user}")
            if 'EXECUTE' in privileges: statements.append(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {target} TO {user}")
            return statements
        if kind == "sqlserver":
            if any(value not in {'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'EXECUTE', 'ALTER'} for value in privileges): raise ValueError("此权限不支持 Schema 级授权")
            return f"GRANT {', '.join(privileges)} ON SCHEMA::{adapters.quote(schema or 'dbo', kind)} TO {user}"
        if kind == "clickhouse": return f"GRANT {', '.join(privileges)} ON {adapters.quote(database or asset.database or 'default', kind)}.* TO {user}"
        if privileges != ['CONNECT']: raise ValueError("此数据库不提供安全等价的 Schema 级对象授权")
        return f"GRANT CREATE SESSION TO {user}"
    raise ValueError("不支持的账号操作")


@api_view(["GET", "POST", "PUT", "DELETE"])
def asset_accounts(request, asset_id):
    denied = guard(request)
    if denied: return denied
    asset, error = get_object_or_error(DatabaseAsset, pk=asset_id, error_message="数据库资产不存在")
    if error: return error
    if asset.db_type in {"sqlite", "redis"}: return bad_request("该数据库类型不支持账号管理")
    try:
        if request.method == "GET":
            kind = asset.db_type
            sql = "SELECT User AS name, Host AS host FROM mysql.user" if kind in {"mysql", "mariadb"} else "SELECT rolname AS name FROM pg_roles" if kind in {"postgresql", "kingbase"} else "SELECT name FROM sys.database_principals WHERE type IN ('S','U','G')" if kind == "sqlserver" else "SELECT name FROM system.users" if kind == "clickhouse" else "SELECT USERNAME AS name FROM ALL_USERS"
            result = []
            with adapters.connection(asset, request.query_params.get("database")) as conn:
                rows, _ = adapters.run(conn, sql, db_type=kind)
                role_options = available_roles(conn, kind)
                for row in rows:
                    name = str(row.get("name") or row.get("NAME") or "")
                    roles, permissions = account_metadata(conn, asset, name, row.get('host', ''), request.query_params.get('database', ''), request.query_params.get('schema', ''))
                    result.append({"name": name, "host": row.get("host", ""), "roles": roles, "permissions": permissions,
                                   "current": name.casefold() == asset.username.casefold(), "builtIn": builtin_account(kind, name),
                                   "protected": name.casefold() == asset.username.casefold() or builtin_account(kind, name),
                                   "capabilities": account_capabilities(kind), "availableRoles": role_options})
            return Response(result)
        data = request.data; action = data.get("action", "create"); name = str(data.get("name", "")).strip()
        expected = {'POST': {'create'}, 'PUT': {'password', 'grant', 'revoke', 'grant_role', 'revoke_role'}, 'DELETE': {'delete'}}
        if action not in expected[request.method]: raise ValueError("请求方法与账号操作不匹配")
        if not name or name == asset.username and action in {"delete"}: raise ValueError("账号名称无效")
        with adapters.connection(asset, data.get("database")) as conn:
            try:
                if action in {'grant_role', 'revoke_role'}:
                    role, role_host = str(data.get('role', '')), str(data.get('roleHost', ''))
                    if not any(item['name'] == role and item['host'] == role_host for item in available_roles(conn, asset.db_type)):
                        raise ValueError('所选角色不存在或不可用')
                    sql = role_sql(asset, action, name, role, str(data.get('host', '%')), role_host)
                else:
                    sql_name = name
                    if action == 'password' and asset.db_type == 'sqlserver':
                        rows, _ = adapters.run(conn, "SELECT SUSER_SNAME(sid) AS login_name FROM sys.database_principals WHERE name=%s AND type='S'", (name,), db_type=asset.db_type)
                        if not rows or not rows[0].get('login_name'):
                            raise ValueError('该数据库用户没有可重置密码的 SQL 登录映射')
                        sql_name = str(rows[0]['login_name'])
                    sql = account_sql(asset, action, sql_name, str(data.get('password', '')), data.get('database', ''), data.get('schema', ''), data.get('grants'), str(data.get('host', '%')))
                for command in sql if isinstance(sql, list) else [sql]: adapters.run(conn, command, db_type=asset.db_type)
                if asset.db_type == 'sqlserver' and action == 'create': adapters.run(conn, f"CREATE USER {adapters.quote(name, asset.db_type)} FOR LOGIN {adapters.quote(name, asset.db_type)}", db_type=asset.db_type)
                if hasattr(conn, "commit"): conn.commit()
            except Exception:
                if hasattr(conn, "rollback"): conn.rollback()
                raise
        record_operation_log(request, "应用管理", "数据库账号操作", name, f"动作={action}; 资产={asset.name}")
        return Response({"ok": True})
    except Exception as exc: return bad_request(adapters.connection_error(exc))
