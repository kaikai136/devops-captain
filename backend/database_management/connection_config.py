"""Validated MySQL settings, encrypted materials and per-operation policy."""
import json
import re
import ssl
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlparse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .services import decrypt_password, encrypt_password

COLORS = {"#ff4d4f", "#fa8c16", "#fadb14", "#52c41a", "#36cfc9", "#1890ff", "#9254de", "#8c8c8c"}
SECRET_KEYS = {"sshPassword", "sshPrivateKey", "sshKeyPassword", "sslCa", "sslCert", "sslKey", "sslKeyPassword"}
FILE_KEYS = {"sshPrivateKey", "sslCa", "sslCert", "sslKey"}
COMMON_KEYS = {"color", "environment", "readOnly", "connectTimeout", "authMethod"}
MYSQL_KEYS = COMMON_KEYS | {"expiresAt", "charset", "parameters", "ssh", "tls"}
LEGACY_KEYS = {"ssl", "https", "instance", "service", "sid", "file", "db", "schema"}
SQL_MODES = set("ALLOW_INVALID_DATES ANSI ANSI_QUOTES ERROR_FOR_DIVISION_BY_ZERO HIGH_NOT_PRECEDENCE IGNORE_SPACE NO_AUTO_VALUE_ON_ZERO NO_BACKSLASH_ESCAPES NO_DIR_IN_CREATE NO_ENGINE_SUBSTITUTION NO_UNSIGNED_SUBTRACTION NO_ZERO_DATE NO_ZERO_IN_DATE ONLY_FULL_GROUP_BY PAD_CHAR_TO_FULL_LENGTH PIPES_AS_CONCAT REAL_AS_FLOAT STRICT_ALL_TABLES STRICT_TRANS_TABLES TRADITIONAL TIME_TRUNCATE_FRACTIONAL NO_AUTO_CREATE_USER".split())


class ConnectionPolicyError(ValueError, PermissionError):
    """Policy failures must stop transfers even when continue-on-error is enabled."""


def integer(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{label}必须为 {low} 至 {high} 的整数")


def hostname(value):
    if not isinstance(value, str) or not value or len(value) > 255 or re.search(r"[\s/\\@\x00]", value):
        raise ValueError("请输入合法的主机名或 IP 地址")


def validate_options(options, kind):
    if not isinstance(options, dict) or set(options) - LEGACY_KEYS - {"authMethod"} - (MYSQL_KEYS if kind == "mysql" else COMMON_KEYS):
        raise ValueError("包含不支持的连接选项")
    if options.get("authMethod", "password") not in {"password", "none", "applicationKey"}:
        raise ValueError("验证方式无效")
    if kind == "sqlite" and options.get("authMethod") == "applicationKey":
        raise ValueError("SQLite 不支持应用密钥认证")
    if kind != "mysql":
        return options
    for key in ("ssl", "readOnly"):
        if key in options and not isinstance(options[key], bool):
            raise ValueError(f"{key} 必须为布尔值")
    if options.get("color", "") not in COLORS | {""}:
        raise ValueError("颜色标签无效")
    if options.get("environment", "") not in {"", "development", "test", "staging", "production"}:
        raise ValueError("环境无效")
    if options.get("charset", "auto") not in {"auto", "utf8mb4", "utf8", "latin1", "gbk", "gb18030"}:
        raise ValueError("编码无效")
    integer(options.get("connectTimeout", 5), 1, 120, "连接超时")
    if options.get("expiresAt"):
        try:
            value = parse_datetime(options["expiresAt"])
        except (TypeError, ValueError):
            value = None
        if value is None or timezone.is_naive(value):
            raise ValueError("到期时间必须包含时区")
    params = options.get("parameters", {})
    if not isinstance(params, dict) or set(params) - {"readTimeout", "writeTimeout", "autocommit", "sqlMode", "timeZone"}:
        raise ValueError("连接参数无效")
    for key in ("readTimeout", "writeTimeout"):
        integer(params.get(key, 20), 1, 600, key)
    if "autocommit" in params and not isinstance(params["autocommit"], bool):
        raise ValueError("自动提交必须为布尔值")
    if "sqlMode" in params:
        if not isinstance(params["sqlMode"], str) or any(mode.strip().upper() not in SQL_MODES for mode in params["sqlMode"].split(",") if mode.strip()):
            raise ValueError("SQL 模式无效")
    if params.get("timeZone"):
        value = params["timeZone"]
        if not isinstance(value, str): raise ValueError("会话时区无效")
        if value != "SYSTEM" and not re.fullmatch(r"[+-](?:0\d|1[0-3]):[0-5]\d|\+14:00", value):
            try: ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError): raise ValueError("会话时区无效")
    ssh = options.get("ssh", {})
    if not isinstance(ssh, dict) or set(ssh) - {"enabled", "host", "port", "username", "authMethod"}:
        raise ValueError("SSH 配置无效")
    if "enabled" in ssh and not isinstance(ssh["enabled"], bool): raise ValueError("SSH 开关无效")
    if ssh.get("enabled"):
        hostname(ssh.get("host"))
        integer(ssh.get("port", 22), 1, 65535, "SSH 端口")
        if not isinstance(ssh.get("username"), str) or not ssh["username"].strip() or len(ssh["username"]) > 120: raise ValueError("请输入 SSH 用户")
        if ssh.get("authMethod", "password") not in {"password", "privateKey"}: raise ValueError("SSH 验证方式无效")
    tls = options.get("tls", {})
    if not isinstance(tls, dict) or set(tls) - {"mode"} or tls.get("mode", "require") not in {"require", "verify_ca", "verify_identity"}:
        raise ValueError("SSL 模式无效")
    return options


def secrets_for(asset):
    raw = getattr(asset, "connection_secrets_encrypted", "")
    return json.loads(decrypt_password(raw)) if raw else {}


def merge_secrets(asset, updates):
    values = dict(secrets_for(asset)) if asset else {}
    if not isinstance(updates, dict) or set(updates) - SECRET_KEYS: raise ValueError("连接凭据无效")
    for key, value in updates.items():
        if value is None:
            values.pop(key, None)
        elif key in FILE_KEYS:
            if not isinstance(value, dict) or set(value) != {"name", "content"} or not all(isinstance(v, str) for v in value.values()):
                raise ValueError("文件材料无效")
            if not value["name"] or len(value["name"]) > 180 or re.search(r"[/\\\x00]", value["name"]): raise ValueError("文件名无效")
            if len(value["content"].encode()) > 256 * 1024: raise ValueError("每个文件最多 256KB")
            values[key] = value
        else:
            if not isinstance(value, str) or len(value) > 4096: raise ValueError("凭据长度无效")
            values[key] = value
    return values


def encode_secrets(values):
    return encrypt_password(json.dumps(values, ensure_ascii=False)) if values else ""


def secret_status(asset):
    return {key: {"configured": True, **({"name": value["name"]} if key in FILE_KEYS else {})}
            for key, value in secrets_for(asset).items() if value}


def load_ssh_key(content, password=None):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_ssh_private_key
    data = content.encode()
    loader = load_ssh_private_key if b"BEGIN OPENSSH" in data else load_pem_private_key
    return loader(data, password=password.encode() if password else None)


def ssl_context(options, secrets):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    mode = options.get("tls", {}).get("mode", "require")
    context.check_hostname = mode == "verify_identity"
    context.verify_mode = ssl.CERT_NONE if mode == "require" else ssl.CERT_REQUIRED
    ca = secrets.get("sslCa")
    if mode != "require" and not ca: raise ValueError("验证证书时必须选择 CA 证书")
    if ca: context.load_verify_locations(cadata=ca["content"])
    cert, key = secrets.get("sslCert"), secrets.get("sslKey")
    if bool(cert) != bool(key): raise ValueError("客户端证书与私钥必须成对提供")
    if cert:
        with tempfile.TemporaryDirectory(prefix="captain-mysql-tls-") as directory:
            cert_path, key_path = Path(directory) / "client.pem", Path(directory) / "key.pem"
            cert_path.write_text(cert["content"], encoding="utf-8")
            key_path.write_text(key["content"], encoding="utf-8")
            key_path.chmod(0o600)
            context.load_cert_chain(cert_path, key_path, secrets.get("sslKeyPassword") or None)
    return context


def validate_materials(options, secrets):
    from cryptography import x509
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    try:
        for key in ("sslCa", "sslCert"):
            if secrets.get(key): x509.load_pem_x509_certificate(secrets[key]["content"].encode())
        if secrets.get("sslKey"):
            load_pem_private_key(secrets["sslKey"]["content"].encode(), password=secrets.get("sslKeyPassword", "").encode() or None)
        if options.get("ssl"): ssl_context(options, secrets)
    except (TypeError, ValueError, ssl.SSLError, UnsupportedAlgorithm) as exc:
        raise ValueError("SSL 证书材料无效，请检查 PEM 格式、证书配对和私钥口令") from exc
    try:
        if secrets.get("sshPrivateKey"):
            load_ssh_key(secrets["sshPrivateKey"]["content"], secrets.get("sshKeyPassword"))
        ssh = options.get("ssh", {})
        if ssh.get("enabled"):
            required = "sshPrivateKey" if ssh.get("authMethod") == "privateKey" else "sshPassword"
            if not secrets.get(required): raise ValueError("请补全 SSH 认证材料")
    except (TypeError, ValueError, UnsupportedAlgorithm) as exc:
        raise ValueError("SSH 认证材料无效，请检查私钥格式和口令，或补全 SSH 密码") from exc


def current_options(asset):
    options = asset.options or {}
    # Long-running transfers recheck the current persisted policy at each SQL batch.
    from .models import DatabaseAsset
    if isinstance(asset, DatabaseAsset) and asset.pk:
        row = DatabaseAsset.objects.filter(pk=asset.pk).values("options").first()
        if row is None: raise ConnectionPolicyError("连接资产已删除")
        options = row["options"] or {}
    return options


def enforce_policy(asset, *, write=False):
    if asset.db_type != "mysql": return
    options = current_options(asset)
    if options.get("expiresAt") and parse_datetime(options["expiresAt"]) <= timezone.now():
        raise ConnectionPolicyError("连接已到期，操作已停止；已提交的批次保留，请编辑连接到期时间")
    if write and options.get("readOnly"):
        raise ConnectionPolicyError("连接为只读模式，禁止写入、导入及管理操作；已提交的批次保留")
    return options


def enforce_sql(asset, sql):
    options = enforce_policy(asset)
    if asset.db_type != "mysql" or not options.get("readOnly"): return
    if not isinstance(sql, str): raise ValueError("只读连接仅允许读取语句")
    statements = [s for s in sqlparse.parse(sql) if str(s).strip()]
    clean = sqlparse.format(sql, strip_comments=True).strip()
    if len(statements) != 1 or "/*!" in sql or not re.match(r"^(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b", clean, re.I):
        raise ValueError("只读连接仅允许单条读取语句")
    if re.match(r"^(SHOW|DESCRIBE|DESC)\b", clean, re.I): return
    # Inspect tokens rather than matching string literals that may contain SQL words.
    tokens = [t for t in statements[0].flatten() if t.ttype not in sqlparse.tokens.Literal.String and t.ttype not in sqlparse.tokens.Comment]
    text = " ".join(str(t) for t in tokens).upper()
    if re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|TRUNCATE|CALL|SET|INTO|FOR\s+UPDATE|LOCK|LOAD_FILE|GET_LOCK|RELEASE_LOCK|SLEEP|BENCHMARK)\b|:=", text):
        raise ValueError("只读连接不允许写入或修改会话状态")
