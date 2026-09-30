from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.contrib.sessions.models import Session
from django.db.models import Count
from django.http import HttpRequest
from django.utils import timezone

from .models import LoginLog, OperationLog, SystemSetting
from .settings_defaults import AUTH_SESSION_FIELD_LIMITS, DEFAULT_AUTH_SESSION, DEFAULT_LOG_RETENTION, DEFAULT_TERMINAL_SETTINGS, TERMINAL_SETTINGS_FIELD_LIMITS

FEATURE_PERMISSIONS_CACHE_KEY = "system.feature_permissions_ready.v1"
FEATURE_PERMISSION_CACHE_SECONDS = getattr(settings, "FEATURE_PERMISSION_CACHE_SECONDS", 300)

BUILTIN_ADMIN_USERNAME = "admin"
BUILTIN_ADMIN_EMAIL = "admin@ops.local"
BUILTIN_ADMIN_FIRST_NAME = "System Administrator"
BUILTIN_ADMIN_PASSWORD_ENV = "OPS_TOOL_ADMIN_PASSWORD"
BUILTIN_ADMIN_DEFAULT_PASSWORD = "Admin@123456"
BUILTIN_ADMIN_ROLE_NAME = "\u7ba1\u7406\u5458"

FEATURE_PERMISSION_DEFINITIONS = [
    ("dashboard", "仪表盘", "dashboard", "仪表盘"),
    ("network", "网络工具", "ip", "IP 探活"),
    ("network", "网络工具", "ports", "机器探测"),
    ("network", "网络工具", "subnet", "IPv4 子网划分"),
    ("host", "主机管理", "hosts", "主机管理"),
    ("host", "主机管理", "bulkExecution", "批量执行"),
    ("host", "主机管理", "applicationMarket", "应用市场"),
    ("host", "主机管理", "databaseManagement", "应用管理"),
    ("host", "主机管理", "accounts", "账号管理"),
    ("company", "设备管理", "companyDevices", "设备资产"),
    ("security", "安全工具", "auth", "双因子认证"),
    ("security", "安全工具", "password", "密码生成器"),
    ("security", "安全工具", "securityScan", "安全扫描"),
    ("system", "系统管理", "loginLogs", "登录日志"),
    ("system", "系统管理", "operationLogs", "操作日志"),
    ("system", "系统管理", "users", "用户管理"),
    ("system", "系统管理", "roles", "角色管理"),
    ("system", "系统管理", "profile", "个人中心"),
    ("system", "系统管理", "systemSettings", "系统设置"),
]

PAGE_ACTION_PERMISSION_DEFINITIONS = [
    ("ip", "scan", "扫描 IP"),
    ("ip", "select_host", "选择主机"),
    ("ports", "ping", "Ping 探测"),
    ("ports", "port_scan", "端口扫描"),
    ("ports", "export_ping", "导出 Ping 结果"),
    ("subnet", "calculate", "计算子网"),
    ("subnet", "split", "划分子网"),
    ("subnet", "clear", "清空结果"),
    ("hosts", "create", "新建主机"),
    ("hosts", "edit", "编辑主机"),
    ("hosts", "delete", "删除主机"),
    ("hosts", "verify", "验证主机"),
    ("hosts", "move", "移动主机"),
    ("hosts", "filter", "筛选主机"),
    ("hosts", "group", "管理分组"),
    ("hosts", "import", "导入恢复"),
    ("hosts", "export", "导出备份"),
    ("hosts", "terminal", "Web 终端"),
    ("hosts", "quick_commands", "快捷命令"),
    ("hosts", "session_audit", "会话审计"),
    ("bulkExecution", "execute", "执行命令"),
    ("bulkExecution", "cancel", "取消任务"),
    ("bulkExecution", "delete", "删除任务"),
    ("bulkExecution", "refresh", "刷新任务"),
    ("applicationMarket", "view", "查看应用市场"),
    ("applicationMarket", "refresh", "刷新应用市场"),
    ("applicationMarket", "install", "安装应用"),
    ("applicationMarket", "update", "更新应用"),
    ("applicationMarket", "uninstall", "卸载应用"),
    ("applicationMarket", "start", "启动应用"),
    ("applicationMarket", "stop", "停止应用"),
    ("applicationMarket", "restart", "重启应用"),
    ("applicationMarket", "view_tasks", "查看应用任务"),
    ("applicationMarket", "manage_sources", "管理应用源"),
    ("databaseManagement", "view", "查看应用管理"),
    ("databaseManagement", "create", "新增数据库资产"),
    ("databaseManagement", "edit", "编辑数据库资产"),
    ("databaseManagement", "delete", "删除数据库资产"),
    ("databaseManagement", "test_connection", "测试数据库连接"),
    ("databaseManagement", "view_data", "查看数据库数据"),
    ("databaseManagement", "execute_sql", "执行数据库 SQL"),
    ("databaseManagement", "modify_data", "修改数据库数据"),
    ("databaseManagement", "manage_schema", "管理数据库结构"),
    ("databaseManagement", "import_export", "导入导出数据库数据"),
    ("databaseManagement", "redis_command", "执行 Redis 命令"),
    ("databaseManagement", "database_admin", "管理数据库级对象"),
    ("databaseManagement", "manage_accounts", "管理数据库账号与授权"),
    ("accounts", "create", "新增账号"),
    ("accounts", "edit", "编辑账号"),
    ("accounts", "delete", "删除账号"),
    ("companyDevices", "create", "添加设备"),
    ("companyDevices", "edit", "编辑设备"),
    ("companyDevices", "delete", "删除设备"),
    ("companyDevices", "export", "导出 Excel"),
    ("companyDevices", "filter", "查询筛选"),
    ("auth", "scan", "扫码导入"),
    ("auth", "import", "导入条目"),
    ("auth", "create", "新增条目"),
    ("auth", "edit", "编辑条目"),
    ("auth", "delete", "删除条目"),
    ("auth", "export", "导出保存"),
    ("auth", "clear", "清空条目"),
    ("password", "generate", "生成密码"),
    ("password", "copy", "复制密码"),
    ("password", "delete", "删除记录"),
    ("password", "clear", "清空记录"),
    ("password", "import", "导入历史"),
    ("password", "export", "导出历史"),
    ("securityScan", "scan", "开始扫描"),
    ("securityScan", "export", "导出报告"),
    ("securityScan", "delete", "删除任务"),
    ("securityScan", "refresh", "刷新任务"),
    ("loginLogs", "refresh", "刷新日志"),
    ("loginLogs", "filter", "筛选日志"),
    ("loginLogs", "columns", "列设置"),
    ("operationLogs", "refresh", "刷新日志"),
    ("operationLogs", "filter", "筛选日志"),
    ("operationLogs", "columns", "列设置"),
    ("users", "create", "新建用户"),
    ("users", "edit", "编辑用户"),
    ("users", "toggle_status", "启用禁用"),
    ("users", "reset_password", "重置密码"),
    ("users", "2fa_enable", "开启 2FA"),
    ("users", "2fa_disable", "关闭 2FA"),
    ("users", "2fa_reset", "重置 2FA"),
    ("users", "session_audit", "会话审计"),
    ("users", "delete", "删除用户"),
    ("roles", "create", "新增角色"),
    ("roles", "edit", "编辑角色"),
    ("roles", "permissions", "权限管理"),
    ("roles", "delete", "删除角色"),
    ("profile", "edit", "保存资料"),
    ("profile", "avatar", "上传头像"),
    ("profile", "password", "修改密码"),
    ("profile", "2fa_enable", "启用 2FA"),
    ("profile", "2fa_disable", "关闭 2FA"),
    ("systemSettings", "save", "保存设置"),
    ("systemSettings", "reset", "还原设置"),
    ("systemSettings", "refresh", "刷新设置"),
]

FEATURE_PERMISSION_CODE_BY_KEY = {key: f"access_{key}" for _, _, key, _ in FEATURE_PERMISSION_DEFINITIONS}
PAGE_LABEL_BY_KEY = {key: label for _, _, key, label in FEATURE_PERMISSION_DEFINITIONS}
PAGE_ACTION_PERMISSION_CODE_BY_KEY = {
    (feature_key, action_key): f"action_{feature_key}_{action_key}"
    for feature_key, action_key, _action_label in PAGE_ACTION_PERMISSION_DEFINITIONS
}
PAGE_ACTION_PERMISSION_META_BY_CODE = {
    code: {
        "feature_key": feature_key,
        "action_key": action_key,
        "action_label": action_label,
        "feature_label": PAGE_LABEL_BY_KEY.get(feature_key, feature_key),
    }
    for (feature_key, action_key), code in PAGE_ACTION_PERMISSION_CODE_BY_KEY.items()
    for _source_feature_key, _source_action_key, action_label in PAGE_ACTION_PERMISSION_DEFINITIONS
    if _source_feature_key == feature_key and _source_action_key == action_key
}
FEATURE_PERMISSION_CODES = set(FEATURE_PERMISSION_CODE_BY_KEY.values())
PAGE_ACTION_PERMISSION_CODES = set(PAGE_ACTION_PERMISSION_CODE_BY_KEY.values())
UI_PERMISSION_CODES = FEATURE_PERMISSION_CODES | PAGE_ACTION_PERMISSION_CODES
_feature_permissions_ready = False


def get_log_retention_setting() -> dict:
    try:
        setting = SystemSetting.objects.get(key="log_retention")
    except SystemSetting.DoesNotExist:
        return DEFAULT_LOG_RETENTION.copy()
    value = setting.value if isinstance(setting.value, dict) else {}
    return {**DEFAULT_LOG_RETENTION, **value}


def get_terminal_settings() -> dict:
    value = get_database_setting_value("terminal_settings")
    if value is None:
        return DEFAULT_TERMINAL_SETTINGS.copy()
    normalized = DEFAULT_TERMINAL_SETTINGS.copy()
    for field, fallback in DEFAULT_TERMINAL_SETTINGS.items():
        minimum, maximum = TERMINAL_SETTINGS_FIELD_LIMITS[field]
        raw_value = value.get(field, fallback)
        if isinstance(raw_value, bool):
            number = fallback
        else:
            try:
                number = int(raw_value)
            except (TypeError, ValueError):
                number = fallback
        normalized[field] = max(minimum, min(maximum, number))
    return normalized


def get_auth_session_settings() -> dict:
    value = get_database_setting_value("auth_session")
    if value is None:
        return DEFAULT_AUTH_SESSION.copy()
    minimum, maximum = AUTH_SESSION_FIELD_LIMITS["loginExpiryMinutes"]
    raw_value = value.get("loginExpiryMinutes", DEFAULT_AUTH_SESSION["loginExpiryMinutes"])
    if isinstance(raw_value, bool):
        number = DEFAULT_AUTH_SESSION["loginExpiryMinutes"]
    else:
        try:
            number = int(raw_value)
        except (TypeError, ValueError):
            number = DEFAULT_AUTH_SESSION["loginExpiryMinutes"]
    return {"loginExpiryMinutes": max(minimum, min(maximum, number))}


def refresh_existing_auth_sessions() -> int:
    expiry = get_auth_session_settings()["loginExpiryMinutes"]
    now = timezone.now().timestamp()
    updated = 0
    for session in Session.objects.all().iterator():
        data = session.get_decoded()
        if data.get("_auth_user_id") is None:
            continue
        data["ops_auth_started_at"] = now
        data["ops_auth_expires_at"] = now + (expiry * 60)
        session.session_data = Session.objects.encode(data)
        session.expire_date = timezone.now() + timezone.timedelta(seconds=expiry * 60)
        session.save(update_fields=["session_data", "expire_date"])
        updated += 1
    return updated


def get_database_setting_value(key: str) -> dict | None:
    try:
        setting = SystemSetting.objects.get(key=key)
    except SystemSetting.DoesNotExist:
        return None
    except Exception as exc:
        if exc.__class__.__name__ == "DatabaseOperationForbidden":
            return None
        raise
    return setting.value if isinstance(setting.value, dict) else {}


def get_rdp_recording_enabled_setting() -> bool:
    log_retention = get_database_setting_value("log_retention")
    if log_retention is not None:
        return bool({**DEFAULT_LOG_RETENTION, **log_retention}.get("rdpRecordingEnabled", DEFAULT_LOG_RETENTION["rdpRecordingEnabled"]))
    value = get_database_setting_value("rdp_recording")
    if value is None:
        return bool(getattr(settings, "RDP_RECORDING_DEFAULT_ENABLED", False))
    if "enabled" in value:
        return bool(value["enabled"])
    return bool(getattr(settings, "RDP_RECORDING_DEFAULT_ENABLED", False))


def get_rdp_recording_retention_days() -> int:
    log_retention = get_database_setting_value("log_retention")
    if log_retention is not None:
        return int({**DEFAULT_LOG_RETENTION, **log_retention}.get("rdpRecordingDays", DEFAULT_LOG_RETENTION["rdpRecordingDays"]))
    return int(getattr(settings, "RDP_RECORDING_RETENTION_DAYS", DEFAULT_LOG_RETENTION["rdpRecordingDays"]))


def retention_cutoff(days: int, now=None):
    if days <= 0:
        return None
    return (now or timezone.now()) - timezone.timedelta(days=days)


def cleanup_queryset(queryset, *, dry_run: bool) -> int:
    count = queryset.count()
    if not dry_run:
        queryset.delete()
    return count


def cleanup_expired_logs(*, now=None, dry_run: bool = False, rdp_root=None) -> dict[str, int]:
    from web_terminal.models import TerminalCommandAudit, TerminalFileAudit, TerminalSession
    from web_terminal.services.rdp import cleanup_expired_rdp_recordings

    now = now or timezone.now()
    retention = get_log_retention_setting()
    result = {
        "loginLogs": 0,
        "operationLogs": 0,
        "terminalCommandAudits": 0,
        "terminalFileAudits": 0,
        "terminalSessions": 0,
        "rdpRecordings": 0,
    }

    cutoff = retention_cutoff(int(retention["loginLogsDays"]), now)
    if cutoff:
        result["loginLogs"] = cleanup_queryset(LoginLog.objects.filter(created_at__lt=cutoff), dry_run=dry_run)

    cutoff = retention_cutoff(int(retention["operationLogsDays"]), now)
    if cutoff:
        result["operationLogs"] = cleanup_queryset(OperationLog.objects.filter(created_at__lt=cutoff), dry_run=dry_run)

    cutoff = retention_cutoff(int(retention["terminalSessionDays"]), now)
    if cutoff:
        sessions = (
            TerminalSession.objects.filter(created_at__lt=cutoff, recording_file="")
            .annotate(command_count=Count("command_audits"), file_count=Count("file_audits"))
            .filter(command_count=0, file_count=0)
        )
        result["terminalSessions"] = cleanup_queryset(sessions, dry_run=dry_run)

    cutoff = retention_cutoff(int(retention["terminalCommandAuditDays"]), now)
    if cutoff:
        result["terminalCommandAudits"] = cleanup_queryset(TerminalCommandAudit.objects.filter(executed_at__lt=cutoff), dry_run=dry_run)

    cutoff = retention_cutoff(int(retention["terminalFileAuditDays"]), now)
    if cutoff:
        result["terminalFileAudits"] = cleanup_queryset(TerminalFileAudit.objects.filter(created_at__lt=cutoff), dry_run=dry_run)

    rdp_result = cleanup_expired_rdp_recordings(root=rdp_root, now=now, dry_run=dry_run)
    result["rdpRecordings"] = rdp_result["deleted"]
    return result


def is_builtin_admin_user(user) -> bool:
    return bool(user and getattr(user, "username", "") == BUILTIN_ADMIN_USERNAME)


def ensure_builtin_admin():
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=BUILTIN_ADMIN_USERNAME,
        defaults={
            "email": BUILTIN_ADMIN_EMAIL,
            "first_name": BUILTIN_ADMIN_FIRST_NAME,
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
        },
    )
    if created:
        admin_password = os.environ.get(BUILTIN_ADMIN_PASSWORD_ENV, "").strip() or BUILTIN_ADMIN_DEFAULT_PASSWORD
        user.set_password(admin_password)
        user.save(update_fields=["password"])

    update_fields: list[str] = []
    fixed_fields = {
        "email": BUILTIN_ADMIN_EMAIL,
        "first_name": BUILTIN_ADMIN_FIRST_NAME,
        "is_active": True,
        "is_staff": True,
        "is_superuser": True,
    }
    for field, value in fixed_fields.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            update_fields.append(field)

    if update_fields:
        user.save(update_fields=list(dict.fromkeys(update_fields)))
    ensure_builtin_admin_role(user)
    return user


def ensure_feature_permissions():
    global _feature_permissions_ready
    content_type = ContentType.objects.get_for_model(SystemSetting)
    if _feature_permissions_ready:
        cached_permissions = list(Permission.objects.filter(content_type=content_type, codename__in=UI_PERMISSION_CODES))
        if len(cached_permissions) == len(UI_PERMISSION_CODES):
            return cached_permissions

    permissions = []
    page_permissions_by_key = {}
    for _group_key, _group_label, feature_key, feature_label in FEATURE_PERMISSION_DEFINITIONS:
        permission, _created = Permission.objects.get_or_create(
            content_type=content_type,
            codename=FEATURE_PERMISSION_CODE_BY_KEY[feature_key],
            defaults={"name": f"访问{feature_label}"},
        )
        expected_name = f"访问{feature_label}"
        if permission.name != expected_name:
            permission.name = expected_name
            permission.save(update_fields=["name"])
        permissions.append(permission)
        page_permissions_by_key[feature_key] = permission

    created_action_permissions_by_feature: dict[str, list[Permission]] = {}
    for feature_key, action_key, action_label in PAGE_ACTION_PERMISSION_DEFINITIONS:
        feature_label = PAGE_LABEL_BY_KEY.get(feature_key, feature_key)
        permission, created = Permission.objects.get_or_create(
            content_type=content_type,
            codename=PAGE_ACTION_PERMISSION_CODE_BY_KEY[(feature_key, action_key)],
            defaults={"name": f"{feature_label}：{action_label}"},
        )
        expected_name = f"{feature_label}：{action_label}"
        if permission.name != expected_name:
            permission.name = expected_name
            permission.save(update_fields=["name"])
        permissions.append(permission)
        if created:
            created_action_permissions_by_feature.setdefault(feature_key, []).append(permission)

    inherit_created_action_permissions(page_permissions_by_key, created_action_permissions_by_feature)
    _feature_permissions_ready = True
    cache.set(FEATURE_PERMISSIONS_CACHE_KEY, True, FEATURE_PERMISSION_CACHE_SECONDS)
    return permissions


def ensure_feature_permissions_ready() -> None:
    """权限校验热路径专用的轻量守卫。

    命中缓存(默认 5 分钟)即直接返回,跳过 ``ensure_feature_permissions`` 里的
    ContentType/Permission 查询;缓存未命中才触发一次完整的懒创建。
    ``has_feature_permission`` 每个受控请求都会调用,故此快路径显著减少 DB 往返。
    """
    if cache.get(FEATURE_PERMISSIONS_CACHE_KEY):
        return
    ensure_feature_permissions()


def ensure_builtin_admin_role(user=None):
    if user is None:
        user = ensure_builtin_admin()

    permissions = ensure_feature_permissions()
    role, _created = Group.objects.get_or_create(name=BUILTIN_ADMIN_ROLE_NAME)
    role.permissions.set(permissions)
    if not user.groups.filter(id=role.id).exists():
        user.groups.add(role)
    return role


def inherit_created_action_permissions(page_permissions_by_key: dict[str, Permission], created_action_permissions_by_feature: dict[str, list[Permission]]):
    for feature_key, action_permissions in created_action_permissions_by_feature.items():
        page_permission = page_permissions_by_key.get(feature_key)
        if not page_permission or not action_permissions:
            continue
        for role in Group.objects.filter(permissions=page_permission).prefetch_related("permissions"):
            role.permissions.add(*action_permissions)
        for user in get_user_model().objects.filter(user_permissions=page_permission):
            user.user_permissions.add(*action_permissions)


def user_feature_permission_codes(user) -> list[str]:
    if not user or not getattr(user, "is_authenticated", False):
        return []
    if getattr(user, "is_superuser", False):
        return sorted(UI_PERMISSION_CODES)

    ensure_feature_permissions()
    codes = user.get_all_permissions()
    return sorted(code.split(".", 1)[1] for code in codes if code.split(".", 1)[-1] in UI_PERMISSION_CODES)


def get_client_ip(request: HttpRequest) -> str | None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def record_login_log(request: HttpRequest, username: str, status: str, message: str = "", user=None) -> LoginLog:
    return LoginLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        username=username,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        status=status,
        message=message,
    )


def record_operation_log(
    request: HttpRequest,
    module: str,
    action: str,
    target: str = "",
    detail: str = "",
    user=None,
) -> OperationLog:
    operator = user or getattr(request, "user", None)
    username = getattr(operator, "username", "") if getattr(operator, "is_authenticated", False) else ""
    log = OperationLog.objects.create(
        user=operator if getattr(operator, "is_authenticated", False) else None,
        username=username,
        module=str(module)[:80],
        action=str(action)[:80],
        target=str(target)[:255],
        detail=str(detail),
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
    setattr(request, "_operation_log_recorded", True)
    raw_request = getattr(request, "_request", None)
    if raw_request is not None:
        setattr(raw_request, "_operation_log_recorded", True)
    return log
