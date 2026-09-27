from rest_framework import serializers
from .models import AssetDirectory, DatabaseAsset
from .services import encrypt_password

class DatabaseAssetSerializer(serializers.ModelSerializer):
    directoryId = serializers.PrimaryKeyRelatedField(source="directory", queryset=AssetDirectory.objects.all(), required=False, allow_null=True)
    dbType = serializers.ChoiceField(source="db_type", choices=DatabaseAsset.DB_TYPES, required=False)
    databaseName = serializers.CharField(source="database", max_length=120, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False, max_length=4096)
    port = serializers.IntegerField(min_value=0, max_value=65535, required=False)
    host = serializers.CharField(required=False, allow_blank=True, max_length=255)
    username = serializers.CharField(required=False, allow_blank=True, max_length=120)
    class Meta:
        model = DatabaseAsset
        fields = ["id", "name", "directoryId", "dbType", "host", "port", "username", "password", "databaseName", "remark", "options", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
    def validate_host(self, value):
        if any(char.isspace() for char in value) or any(char in value for char in "/\\@\x00"):
            raise serializers.ValidationError("请输入主机名或 IP 地址，不要包含协议或路径")
        return value
    def validate_options(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("连接选项必须为对象")
        allowed = {"ssl", "https", "instance", "service", "sid", "file", "db", "schema"}
        if set(value) - allowed:
            raise serializers.ValidationError("包含不支持的连接选项")
        return value
    def validate(self, attrs):
        db_type = attrs.get("db_type", getattr(self.instance, "db_type", "mysql"))
        options = attrs.get("options", getattr(self.instance, "options", {})) or {}
        if db_type == "sqlite":
            from .adapters import sqlite_path
            try:
                sqlite_path(options.get("file", ""))
            except ValueError as exc:
                raise serializers.ValidationError({"options": str(exc)}) from exc
        elif not attrs.get("host", getattr(self.instance, "host", "")):
            raise serializers.ValidationError({"host": "请输入数据库地址"})
        elif not attrs.get("port", getattr(self.instance, "port", 0)):
            raise serializers.ValidationError({"port": "请输入数据库端口"})
        if db_type == "redis":
            try:
                db = int(options.get("db", 0))
            except (TypeError, ValueError):
                raise serializers.ValidationError({"options": "Redis DB 编号必须是 0 至 255 的整数"})
            if not 0 <= db <= 255:
                raise serializers.ValidationError({"options": "Redis DB 编号必须是 0 至 255 的整数"})
        if db_type == "oracle" and not (options.get("service") or options.get("sid") or attrs.get("database", getattr(self.instance, "database", ""))):
            raise serializers.ValidationError({"options": "Oracle 需要 Service Name 或 SID"})
        return attrs
    def create(self, validated_data):
        validated_data["password_encrypted"] = encrypt_password(validated_data.pop("password", ""))
        return super().create(validated_data)
    def update(self, instance, validated_data):
        if "password" in validated_data:
            password = validated_data.pop("password")
            if password:
                validated_data["password_encrypted"] = encrypt_password(password)
        return super().update(instance, validated_data)
