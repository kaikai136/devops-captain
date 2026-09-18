import re
from urllib.parse import urlparse

from rest_framework import serializers

from .constants import (
    AUTH_SESSION_FIELD_LIMITS,
    DASHBOARD_HERO_FONT_CHOICES,
    DEFAULT_AUTH_SESSION,
    DEFAULT_DASHBOARD_HERO,
    DEFAULT_LAYOUT_FOOTER,
    DEFAULT_LOG_RETENTION,
    DEFAULT_LOGIN_CONTENT,
    DEFAULT_SITE_IDENTITY,
    DEFAULT_TERMINAL_SETTINGS,
    DEFAULT_UI_THEME,
    DEFAULT_WATERMARK_TEXT,
    FONT_WEIGHT_CHOICES,
    HEX_COLOR_RE,
    TERMINAL_SETTINGS_FIELD_LIMITS,
    UI_THEME_PRESET_CHOICES,
    WATERMARK_ALLOWED_PAGES,
)


def _require_setting_object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise serializers.ValidationError({"value": f"{label}配置格式无效"})
    return value


def _clean_text(value, fallback: str, max_length: int = 160) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        return fallback
    return text[:max_length]


def _clean_optional_text(value, max_length: int = 160) -> str:
    return str(value if value is not None else "").strip()[:max_length]


def _clean_url(value, fallback: str = "", *, allow_blank: bool = False) -> str:
    url = str(value if value is not None else "").strip()
    if not url:
        if allow_blank:
            return ""
        return fallback
    if url.startswith("/") and not url.startswith("//"):
        return url[:500]
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return url[:500]
    raise serializers.ValidationError({"value": "URL 仅支持相对路径或 http/https 地址"})


def _clean_color(value, fallback: str) -> str:
    color = str(value if value is not None else "").strip()
    if not color:
        return fallback
    if not HEX_COLOR_RE.fullmatch(color):
        raise serializers.ValidationError({"value": "颜色值必须是 #RRGGBB 格式"})
    return color.upper()


def _clean_dashboard_font(value, fallback: str) -> str:
    font = _clean_text(value, fallback, 80)
    if font not in DASHBOARD_HERO_FONT_CHOICES:
        raise serializers.ValidationError({"value": "字体仅支持 Noto Sans SC / Noto Serif SC / Noto Sans TC / Noto Serif TC"})
    return font


def _clean_svg_color(value, fallback: str, *, allow_alpha: bool = False) -> str:
    color = str(value if value is not None else "").strip()
    if not color:
        return fallback
    pattern = r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$" if allow_alpha else r"^#[0-9A-Fa-f]{6}$"
    if not re.fullmatch(pattern, color):
        raise serializers.ValidationError({"value": "SVG 颜色值必须是 #RRGGBB 或 #RRGGBBAA 格式"})
    return color.upper()


def _clean_letter_spacing(value, fallback: str) -> str:
    spacing = str(value if value is not None else "").strip() or fallback
    if not re.fullmatch(r"[A-Za-z0-9 ._%+-]{1,40}", spacing):
        raise serializers.ValidationError({"value": "字间距格式无效"})
    return spacing


def _clean_int(value, fallback: int, *, minimum: int, maximum: int, field_label: str) -> int:
    if value is None or value == "":
        return fallback
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise serializers.ValidationError({"value": f"{field_label}必须是数字"})
    if number < minimum or number > maximum:
        raise serializers.ValidationError({"value": f"{field_label}必须在 {minimum}-{maximum} 之间"})
    return number


def _clean_strict_int(value, fallback: int, *, minimum: int, maximum: int, field_label: str) -> int:
    if value is None or value == "":
        return fallback
    if isinstance(value, bool):
        raise serializers.ValidationError({"value": f"{field_label}必须是整数"})
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        number = int(value.strip())
    else:
        raise serializers.ValidationError({"value": f"{field_label}必须是整数"})
    if number < minimum or number > maximum:
        raise serializers.ValidationError({"value": f"{field_label}必须在 {minimum}-{maximum} 之间"})
    return number


def _clean_font_weight(value, fallback: int) -> int:
    weight = _clean_int(value, fallback, minimum=400, maximum=900, field_label="字重")
    if weight not in FONT_WEIGHT_CHOICES:
        raise serializers.ValidationError({"value": "字重仅支持 400/500/600/700/800/900"})
    return weight


def validate_site_identity_value(value):
    raw = _require_setting_object(value, "品牌变量")
    defaults = DEFAULT_SITE_IDENTITY
    return {
        "appName": _clean_text(raw.get("appName"), defaults["appName"], 80),
        "appShortName": _clean_text(raw.get("appShortName"), defaults["appShortName"], 32),
        "appSubtitle": _clean_text(raw.get("appSubtitle"), defaults["appSubtitle"], 80),
        "browserTitle": _clean_text(raw.get("browserTitle"), defaults["browserTitle"], 80),
        "logoText": _clean_text(raw.get("logoText"), defaults["logoText"], 32),
        "logoImageUrl": _clean_url(raw.get("logoImageUrl"), defaults["logoImageUrl"]),
        "iconUrl": _clean_url(raw.get("iconUrl"), defaults["iconUrl"]),
        "totpIssuer": _clean_text(raw.get("totpIssuer"), defaults["totpIssuer"], 80),
    }


def validate_dashboard_hero_value(value):
    raw = _require_setting_object(value, "仪表盘动态文字")
    defaults = DEFAULT_DASHBOARD_HERO
    return {
        "badgeTemplate": _clean_text(raw.get("badgeTemplate"), defaults["badgeTemplate"], 160),
        "line1Template": _clean_text(raw.get("line1Template"), defaults["line1Template"], 160),
        "line2Template": _clean_text(raw.get("line2Template"), defaults["line2Template"], 160),
        "descriptionTemplate": _clean_text(raw.get("descriptionTemplate"), defaults["descriptionTemplate"], 260),
        "font": _clean_dashboard_font(raw.get("font"), defaults["font"]),
        "fontSize": _clean_int(raw.get("fontSize"), defaults["fontSize"], minimum=16, maximum=36, field_label="动态文字字号"),
        "fontWeight": _clean_font_weight(raw.get("fontWeight"), defaults["fontWeight"]),
        "letterSpacing": _clean_letter_spacing(raw.get("letterSpacing"), defaults["letterSpacing"]),
        "durationMs": _clean_int(raw.get("durationMs"), defaults["durationMs"], minimum=100, maximum=30000, field_label="每行持续时间"),
        "pauseMs": _clean_int(raw.get("pauseMs"), defaults["pauseMs"], minimum=0, maximum=10000, field_label="停顿时间"),
        "color": _clean_svg_color(raw.get("color"), defaults["color"]),
        "backgroundColor": _clean_svg_color(raw.get("backgroundColor"), defaults["backgroundColor"], allow_alpha=True),
        "centered": bool(raw.get("centered", defaults["centered"])),
        "verticalCentered": bool(raw.get("verticalCentered", defaults["verticalCentered"])),
        "multiline": bool(raw.get("multiline", defaults["multiline"])),
        "repeat": bool(raw.get("repeat", defaults["repeat"])),
        "random": bool(raw.get("random", defaults["random"])),
        "width": _clean_int(raw.get("width"), defaults["width"], minimum=160, maximum=1600, field_label="SVG 宽度"),
        "height": _clean_int(raw.get("height"), defaults["height"], minimum=30, maximum=420, field_label="SVG 高度"),
    }


def validate_layout_footer_value(value):
    raw = _require_setting_object(value, "页脚")
    defaults = DEFAULT_LAYOUT_FOOTER
    return {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "textTemplate": _clean_text(raw.get("textTemplate"), defaults["textTemplate"], 220),
        "linkText": _clean_optional_text(raw.get("linkText"), 80),
        "linkUrl": _clean_url(raw.get("linkUrl"), "", allow_blank=True),
        "fontSize": _clean_int(raw.get("fontSize"), defaults["fontSize"], minimum=10, maximum=18, field_label="页脚字号"),
        "color": _clean_color(raw.get("color"), defaults["color"]),
    }


def validate_login_content_value(value):
    raw = _require_setting_object(value, "登录页文案")
    defaults = DEFAULT_LOGIN_CONTENT
    return {
        "badgeTemplate": _clean_text(raw.get("badgeTemplate"), defaults["badgeTemplate"], 160),
        "title": _clean_text(raw.get("title"), defaults["title"], 80),
        "description": _clean_text(raw.get("description"), defaults["description"], 260),
        "copyrightTemplate": _clean_text(raw.get("copyrightTemplate"), defaults["copyrightTemplate"], 160),
    }


def validate_ui_theme_value(value):
    raw = _require_setting_object(value, "界面主题")
    preset = str(raw.get("preset", DEFAULT_UI_THEME["preset"])).strip().lower()
    if preset not in UI_THEME_PRESET_CHOICES:
        raise serializers.ValidationError({"value": "主题预设无效"})
    return {
        "preset": preset,
        "customPrimary": _clean_color(raw.get("customPrimary"), DEFAULT_UI_THEME["customPrimary"]),
    }


def validate_watermark_value(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError({"value": "水印配置格式无效"})

    enabled = bool(value.get("enabled", False))
    text = str(value.get("text", DEFAULT_WATERMARK_TEXT)).strip() or DEFAULT_WATERMARK_TEXT
    raw_pages = value.get("pages", [])
    if not isinstance(raw_pages, list):
        raise serializers.ValidationError({"value": "水印应用页面格式无效"})

    pages = []
    invalid_pages = []
    for page in raw_pages:
        page_key = str(page).strip()
        if not page_key:
            continue
        if page_key not in WATERMARK_ALLOWED_PAGES:
            invalid_pages.append(page_key)
            continue
        if page_key not in pages:
            pages.append(page_key)

    if invalid_pages:
        raise serializers.ValidationError({"value": f"水印应用页面无效：{invalid_pages[0]}"})
    if enabled and not text:
        raise serializers.ValidationError({"value": "开启水印时请输入水印文本"})

    return {"enabled": enabled, "text": text, "pages": pages}


def validate_security_scan_value(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError({"value": "安全扫描配置格式无效"})
    return {"onlineCveEnabled": bool(value.get("onlineCveEnabled", False))}


def validate_log_retention_value(value):
    raw = _require_setting_object(value, "日志保留")
    defaults = DEFAULT_LOG_RETENTION
    day_labels = {
        "loginLogsDays": "登录日志保留天数",
        "operationLogsDays": "操作日志保留天数",
        "terminalCommandAuditDays": "终端命令审计保留天数",
        "terminalFileAuditDays": "终端文件审计保留天数",
        "terminalSessionDays": "终端会话元数据保留天数",
        "rdpRecordingDays": "RDP 录像保留天数",
    }
    enabled = raw.get("rdpRecordingEnabled", defaults["rdpRecordingEnabled"])
    if not isinstance(enabled, bool):
        raise serializers.ValidationError({"value": "RDP 录像开关必须是布尔值"})
    cleaned = {
        field: _clean_strict_int(raw.get(field), defaults[field], minimum=0, maximum=3650, field_label=label)
        for field, label in day_labels.items()
    }
    return {
        "loginLogsDays": cleaned["loginLogsDays"],
        "operationLogsDays": cleaned["operationLogsDays"],
        "terminalCommandAuditDays": cleaned["terminalCommandAuditDays"],
        "terminalFileAuditDays": cleaned["terminalFileAuditDays"],
        "terminalSessionDays": cleaned["terminalSessionDays"],
        "rdpRecordingEnabled": enabled,
        "rdpRecordingDays": cleaned["rdpRecordingDays"],
    }


def validate_terminal_settings_value(value):
    raw = _require_setting_object(value, "终端设置")
    cleaned = {}
    labels = {
        "sshConnectTimeoutSeconds": "SSH 连接超时秒数",
        "sshBannerTimeoutSeconds": "SSH Banner 超时秒数",
        "sshAuthTimeoutSeconds": "SSH 认证超时秒数",
        "sshConnectAttempts": "SSH 连接重试次数",
        "sshRetryDelayMs": "SSH 重试基础间隔毫秒",
        "sshKeepaliveSeconds": "SSH Keepalive 间隔秒数",
        "webSocketHeartbeatSeconds": "WebSocket 心跳间隔秒数",
        "idleDisconnectMinutes": "闲置断开分钟数",
        "initialReadTimeoutSeconds": "初始读取超时秒数",
        "initialReadIdleTimeoutMs": "初始读取空闲毫秒",
        "commandReadTimeoutSeconds": "命令读取超时秒数",
        "commandReadIdleTimeoutMs": "命令读取空闲毫秒",
        "readerPollIntervalMs": "输出轮询间隔毫秒",
        "cwdHookSuppressEchoMs": "CWD Hook 回显抑制毫秒",
        "cwdHookDrainTimeoutMs": "CWD Hook 排空超时毫秒",
        "cwdHookDrainIdleTimeoutMs": "CWD Hook 排空空闲毫秒",
        "defaultCols": "默认列数",
        "defaultRows": "默认行数",
        "defaultFontSize": "默认字号",
        "scrollbackLines": "滚屏行数",
        "bulkExecutionMaxTargets": "批量执行最大主机数",
    }
    for field, fallback in DEFAULT_TERMINAL_SETTINGS.items():
        minimum, maximum = TERMINAL_SETTINGS_FIELD_LIMITS[field]
        cleaned[field] = _clean_strict_int(
            raw.get(field),
            fallback,
            minimum=minimum,
            maximum=maximum,
            field_label=labels[field],
        )
    return cleaned


def validate_auth_session_value(value):
    raw = _require_setting_object(value, "登录会话")
    minimum, maximum = AUTH_SESSION_FIELD_LIMITS["loginExpiryMinutes"]
    return {
        "loginExpiryMinutes": _clean_strict_int(
            raw.get("loginExpiryMinutes"),
            DEFAULT_AUTH_SESSION["loginExpiryMinutes"],
            minimum=minimum,
            maximum=maximum,
            field_label="系统登录过期时间",
        )
    }
