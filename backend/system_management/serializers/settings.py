from rest_framework import serializers

from ..models import SystemSetting
from .constants import (
    AUTH_SESSION_SETTING_KEY,
    DASHBOARD_HERO_SETTING_KEY,
    LAYOUT_FOOTER_SETTING_KEY,
    LOG_RETENTION_SETTING_KEY,
    LOGIN_CONTENT_SETTING_KEY,
    SECURITY_SCAN_SETTING_KEY,
    SITE_IDENTITY_SETTING_KEY,
    TERMINAL_SETTINGS_SETTING_KEY,
    UI_THEME_SETTING_KEY,
    WATERMARK_SETTING_KEY,
)
from .settings_validators import (
    validate_auth_session_value,
    validate_dashboard_hero_value,
    validate_layout_footer_value,
    validate_log_retention_value,
    validate_login_content_value,
    validate_security_scan_value,
    validate_site_identity_value,
    validate_terminal_settings_value,
    validate_ui_theme_value,
    validate_watermark_value,
)


class SystemSettingSerializer(serializers.ModelSerializer):
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = SystemSetting
        fields = ["id", "key", "label", "description", "value", "updatedAt"]

    def validate_key(self, value):
        key = value.strip()
        if not key:
            raise serializers.ValidationError("请输入设置键名")
        return key

    def validate(self, attrs):
        key = attrs.get("key", getattr(self.instance, "key", ""))
        value = attrs.get("value", getattr(self.instance, "value", {}))
        if key == SITE_IDENTITY_SETTING_KEY:
            attrs["value"] = validate_site_identity_value(value)
        elif key == DASHBOARD_HERO_SETTING_KEY:
            attrs["value"] = validate_dashboard_hero_value(value)
        elif key == LAYOUT_FOOTER_SETTING_KEY:
            attrs["value"] = validate_layout_footer_value(value)
        elif key == LOGIN_CONTENT_SETTING_KEY:
            attrs["value"] = validate_login_content_value(value)
        elif key == UI_THEME_SETTING_KEY:
            attrs["value"] = validate_ui_theme_value(value)
        elif key == WATERMARK_SETTING_KEY:
            attrs["value"] = validate_watermark_value(value)
        elif key == SECURITY_SCAN_SETTING_KEY:
            attrs["value"] = validate_security_scan_value(value)
        elif key == LOG_RETENTION_SETTING_KEY:
            attrs["value"] = validate_log_retention_value(value)
        elif key == TERMINAL_SETTINGS_SETTING_KEY:
            attrs["value"] = validate_terminal_settings_value(value)
        elif key == AUTH_SESSION_SETTING_KEY:
            attrs["value"] = validate_auth_session_value(value)
        return attrs
