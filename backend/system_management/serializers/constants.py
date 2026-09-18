import re

from ..settings_defaults import (
    AUTH_SESSION_FIELD_LIMITS,
    DEFAULT_AUTH_SESSION,
    DEFAULT_LOG_RETENTION,
    DEFAULT_TERMINAL_SETTINGS,
    LOG_RETENTION_DAY_FIELDS,
    TERMINAL_SETTINGS_FIELD_LIMITS,
)

SITE_IDENTITY_SETTING_KEY = "site_identity"
DASHBOARD_HERO_SETTING_KEY = "dashboard_hero"
LAYOUT_FOOTER_SETTING_KEY = "layout_footer"
LOGIN_CONTENT_SETTING_KEY = "login_content"
UI_THEME_SETTING_KEY = "ui_theme"
WATERMARK_SETTING_KEY = "watermark"
SECURITY_SCAN_SETTING_KEY = "security_scan"
LOG_RETENTION_SETTING_KEY = "log_retention"
TERMINAL_SETTINGS_SETTING_KEY = "terminal_settings"
AUTH_SESSION_SETTING_KEY = "auth_session"
DISPLAY_SETTING_KEYS = {
    SITE_IDENTITY_SETTING_KEY,
    DASHBOARD_HERO_SETTING_KEY,
    LAYOUT_FOOTER_SETTING_KEY,
    LOGIN_CONTENT_SETTING_KEY,
    UI_THEME_SETTING_KEY,
    WATERMARK_SETTING_KEY,
    SECURITY_SCAN_SETTING_KEY,
    TERMINAL_SETTINGS_SETTING_KEY,
    AUTH_SESSION_SETTING_KEY,
}
PUBLIC_DISPLAY_SETTING_KEYS = {
    SITE_IDENTITY_SETTING_KEY,
    LOGIN_CONTENT_SETTING_KEY,
    UI_THEME_SETTING_KEY,
}
DEFAULT_SITE_IDENTITY = {
    "appName": "运维船长",
    "appShortName": "CAPTAIN",
    "appSubtitle": "Secure Console",
    "browserTitle": "运维船长",
    "logoText": "CAPTAIN",
    "logoImageUrl": "/captain-banner.png",
    "iconUrl": "/ops-captain-icon.png",
    "totpIssuer": "运维船长",
}
DEFAULT_DASHBOARD_HERO = {
    "badgeTemplate": "{appShortName} OPS",
    "line1Template": "{greeting}，{displayName}",
    "line2Template": "一路向前，莫问前程！！！",
    "descriptionTemplate": "这里汇总系统账号、资产与网络出口状态，帮助你快速判断今天的运维态势。",
    "font": "Noto Sans SC",
    "fontSize": 24,
    "fontWeight": 900,
    "letterSpacing": "normal",
    "durationMs": 5000,
    "pauseMs": 1000,
    "color": "#9B5CFF",
    "backgroundColor": "#00000000",
    "centered": False,
    "verticalCentered": True,
    "multiline": False,
    "repeat": True,
    "random": False,
    "width": 620,
    "height": 64,
}
DEFAULT_LAYOUT_FOOTER = {
    "enabled": True,
    "textTemplate": "© Copyright {year} {appName} All rights reserved.",
    "linkText": "",
    "linkUrl": "",
    "fontSize": 12,
    "color": "#0B5CFF",
}
DEFAULT_LOGIN_CONTENT = {
    "badgeTemplate": "{appName} · {appSubtitle}",
    "title": "欢迎回来",
    "description": "登录管理平台，继续处理网络、主机和系统管理任务。",
    "copyrightTemplate": "© {year} {appName} Team",
}
DEFAULT_UI_THEME = {
    "preset": "blue",
    "customPrimary": "#2563EB",
}
UI_THEME_PRESET_CHOICES = {"neutral", "slate", "blue", "cyan", "teal", "emerald", "custom"}
DEFAULT_WATERMARK_TEXT = "{username}"
DASHBOARD_HERO_FONT_CHOICES = {"Noto Sans SC", "Noto Serif SC", "Noto Sans TC", "Noto Serif TC"}
FONT_WEIGHT_CHOICES = {400, 500, 600, 700, 800, 900}
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
WATERMARK_ALLOWED_PAGES = {
    "dashboard",
    "ip",
    "ports",
    "subnet",
    "hosts",
    "sessionAudits",
    "bulkExecution",
    "applicationMarket",
    "accounts",
    "companyDevices",
    "auth",
    "password",
    "securityScan",
    "loginLogs",
    "operationLogs",
    "users",
    "roles",
    "profile",
    "systemSettings",
    "webTerminal",
}
