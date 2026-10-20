from rest_framework import serializers
from .models import ApplicationKey, AssetDirectory, DatabaseAsset
from accounts.permissions import has_feature_permission
from .services import encrypt_password
from .connection_config import validate_options, merge_secrets, encode_secrets, secret_status, validate_materials

class DatabaseAssetSerializer(serializers.ModelSerializer):
    applicationKeyId = serializers.PrimaryKeyRelatedField(source="application_key", queryset=ApplicationKey.objects.all(), required=False, allow_null=True)
    applicationKeyName = serializers.SerializerMethodField()
    directoryId = serializers.PrimaryKeyRelatedField(source="directory", queryset=AssetDirectory.objects.all(), required=False, allow_null=True)
    dbType = serializers.ChoiceField(source="db_type", choices=DatabaseAsset.DB_TYPES, required=False)
    databaseName = serializers.CharField(source="database", max_length=120, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False, max_length=4096)
    connectionSecrets = serializers.JSONField(write_only=True, required=False)
    connectionSecretStatus = serializers.SerializerMethodField()
    port = serializers.IntegerField(min_value=0, max_value=65535, required=False)
    host = serializers.CharField(required=False, allow_blank=True, max_length=255)
    username = serializers.CharField(required=False, allow_blank=True, max_length=120)
    class Meta:
        model = DatabaseAsset
        fields = ["id", "name", "directoryId", "dbType", "host", "port", "username", "password", "applicationKeyId", "applicationKeyName", "connectionSecrets", "connectionSecretStatus", "databaseName", "remark", "options", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
    def validate_host(self, value):
        if any(char.isspace() for char in value) or any(char in value for char in "/\\@\x00"):
            raise serializers.ValidationError("请输入主机名或 IP 地址，不要包含协议或路径")
        return value
    def get_connectionSecretStatus(self, instance):
        return secret_status(instance)
    def get_applicationKeyName(self, instance):
        return instance.application_key.name if instance.application_key_id else ""
    def to_representation(self, instance):
        result = super().to_representation(instance)
        if instance.application_key_id and (instance.options or {}).get("authMethod") == "applicationKey":
            result["username"] = instance.application_key.username
        return result
    def validate(self, attrs):
        db_type = attrs.get("db_type", getattr(self.instance, "db_type", "mysql"))
        options = attrs.get("options", getattr(self.instance, "options", {})) or {}
        try:
            validate_options(options, db_type)
        except ValueError as exc:
            raise serializers.ValidationError({"options": str(exc)}) from exc
        key_mode = options.get("authMethod") == "applicationKey"
        if key_mode:
            key = attrs.get("application_key", getattr(self.instance, "application_key", None))
            if not key and not self.context.get("connection_import"):
                raise serializers.ValidationError({"applicationKeyId": "请选择应用密钥"})
            if key:
                previous_id = getattr(self.instance, "application_key_id", None)
                previous_mode = (getattr(self.instance, "options", None) or {}).get("authMethod")
                if key.pk != previous_id or previous_mode != "applicationKey":
                    request = self.context.get("request")
                    if not request or not has_feature_permission(request.user, "applicationKeys", "use"):
                        raise serializers.ValidationError({"applicationKeyId": "没有使用应用密钥的权限"})
                if db_type != "redis" and not key.username.strip():
                    raise serializers.ValidationError({"applicationKeyId": "所选应用密钥缺少用户名"})
            attrs["application_key"] = key
            attrs["username"] = ""
            attrs.pop("password", None)
            attrs["password_encrypted"] = ""
        else:
            attrs["application_key"] = None
        try:
            materials = merge_secrets(self.instance, attrs.pop("connectionSecrets", {}))
            if db_type == "mysql" and not self.context.get("connection_import"):
                validate_materials(options, materials)
            attrs["connection_secrets_encrypted"] = encode_secrets(materials)
        except ValueError as exc:
            raise serializers.ValidationError({"options": str(exc)}) from exc
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
        password = validated_data.pop("password", "")
        if validated_data.get("options", {}).get("authMethod") == "none": password = ""
        validated_data["password_encrypted"] = "" if validated_data.get("application_key") else encrypt_password(password)
        return super().create(validated_data)
    def update(self, instance, validated_data):
        if validated_data.get("options", instance.options).get("authMethod") == "none":
            validated_data.pop("password", None)
            validated_data["password_encrypted"] = encrypt_password("")
        if "password" in validated_data:
            password = validated_data.pop("password")
            if password:
                validated_data["password_encrypted"] = encrypt_password(password)
        return super().update(instance, validated_data)
