import base64
import hashlib
import os
import re
from contextlib import closing

import pymysql
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$-]*$")

def _key():
    return base64.urlsafe_b64encode(hashlib.sha256(("database-management:" + settings.SECRET_KEY).encode()).digest())

def encrypt_password(value: str) -> str:
    raw = value.encode()
    return Fernet(_key()).encrypt(raw).decode()

def decrypt_password(value: str) -> str:
    if not value: return ""
    try: return Fernet(_key()).decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, TypeError): raise ValueError("数据库凭据无法解密，请重新保存密码")

def validate_identifier(value: str, label="标识符") -> str:
    value = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(value): raise ValueError(f"{label}格式不正确")
    return value

def connect(asset, database=None):
    return pymysql.connect(host=asset.host, port=asset.port, user=asset.username, password=decrypt_password(asset.password_encrypted), database=database or asset.database or None, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, connect_timeout=5, read_timeout=15, write_timeout=15)

def databases(asset):
    with closing(connect(asset)) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            return [row["Database"] for row in cursor.fetchall()]

def tables(asset, database):
    database = validate_identifier(database, "数据库名")
    with closing(connect(asset, database)) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT TABLE_NAME AS name, TABLE_TYPE AS type, TABLE_ROWS AS rows_count, TABLE_COMMENT AS comment FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME", (database,))
            return list(cursor.fetchall())

def columns(asset, database, table):
    database, table = validate_identifier(database, "数据库名"), validate_identifier(table, "表名")
    with closing(connect(asset, database)) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COLUMN_NAME AS name, COLUMN_TYPE AS type, IS_NULLABLE AS nullable, COLUMN_KEY AS column_key, COLUMN_COMMENT AS comment FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION", (database, table))
            return list(cursor.fetchall())

def table_data(asset, database, table, fields=None, where_field=None, where_value=None, sort_field=None, sort_direction="asc", page=1, page_size=25):
    database, table = validate_identifier(database, "数据库名"), validate_identifier(table, "表名")
    selected = "*" if not fields else ", ".join(validate_identifier(item, "字段名") for item in fields)
    where = ""; args = []
    if where_field and where_value not in (None, ""):
        where = f" WHERE `{validate_identifier(where_field, '筛选字段')}` = %s"; args.append(where_value)
    order = ""
    if sort_field: order = f" ORDER BY `{validate_identifier(sort_field, '排序字段')}` {'DESC' if str(sort_direction).lower() == 'desc' else 'ASC'}"
    offset = max(page - 1, 0) * page_size
    with closing(connect(asset, database)) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM `{table}`{where}", args); total = int(cursor.fetchone()["total"])
            cursor.execute(f"SELECT {selected} FROM `{table}`{where}{order} LIMIT %s OFFSET %s", [*args, page_size, offset])
            rows = list(cursor.fetchall())
    return {"rows": rows, "total": total, "page": page, "pageSize": page_size, "hasNext": offset + page_size < total}


def connection_error(error):
    code = error.args[0] if getattr(error, "args", None) else None
    return {
        1045: "数据库认证失败，请检查用户名和密码",
        1044: "当前数据库账号没有访问权限",
        1049: "数据库不存在，请刷新数据库列表",
        1142: "当前数据库账号没有读取权限",
        1146: "数据表不存在，请刷新表列表",
        2003: "无法连接数据库，请检查地址、端口及网络",
        2013: "查询超时或连接中断，请缩小查询范围后重试",
        3024: "查询超时，请缩小查询范围后重试",
    }.get(code, "数据库操作失败，请检查连接配置和读取权限")

