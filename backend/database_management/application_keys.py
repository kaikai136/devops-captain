from django.db import IntegrityError, transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import require_feature_permission
from operations.responses import bad_request, get_object_or_error
from system_management.services import record_operation_log
from .models import ApplicationKey
from .services import encrypt_password


class ApplicationKeySerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False, max_length=4096)
    hasPassword = serializers.SerializerMethodField()
    connectionCount = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationKey
        fields = ["id", "name", "username", "password", "hasPassword", "connectionCount", "remark", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_hasPassword(self, instance):
        return bool(instance.password_encrypted)

    def get_connectionCount(self, instance):
        return getattr(instance, "connection_count", None) if hasattr(instance, "connection_count") else instance.connections.count()

    def validate(self, attrs):
        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "请输入密码"})
        if self.instance and not attrs.get("username", self.instance.username).strip() and self.instance.connections.exclude(db_type="redis").exists():
            raise serializers.ValidationError({"username": "该密钥已关联需要用户名的数据库，不能清空用户"})
        return attrs

    def create(self, validated_data):
        validated_data["password_encrypted"] = encrypt_password(validated_data.pop("password"))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "")
        if password:
            validated_data["password_encrypted"] = encrypt_password(password)
        return super().update(instance, validated_data)


@api_view(["GET", "POST"])
def collection(request):
    selecting = request.method == "GET" and request.query_params.get("select") == "1"
    error = require_feature_permission(request, "applicationKeys", "use" if selecting else "view" if request.method == "GET" else "create")
    if error:
        return error
    if request.method == "GET":
        keys = ApplicationKey.objects.annotate(connection_count=Count("connections"))
        if selecting:
            return Response(list(keys.values("id", "name", "username")))
        return Response(ApplicationKeySerializer(keys, many=True).data)
    serializer = ApplicationKeySerializer(data=request.data)
    if not serializer.is_valid():
        return bad_request(str(serializer.errors))
    try:
        key = serializer.save()
    except IntegrityError:
        return bad_request("应用密钥名称已存在")
    record_operation_log(request, "应用密钥", "新增密钥", key.name, f"ID={key.pk}")
    return Response(ApplicationKeySerializer(key).data, status=status.HTTP_201_CREATED)


@api_view(["PUT", "DELETE"])
def detail(request, key_id):
    error = require_feature_permission(request, "applicationKeys", "edit" if request.method == "PUT" else "delete")
    if error:
        return error
    try:
        with transaction.atomic():
            key, error = get_object_or_error(ApplicationKey, queryset=ApplicationKey.objects.select_for_update(), pk=key_id, error_message="应用密钥不存在")
            if error:
                return error
            if request.method == "DELETE":
                count = key.connections.count()
                if count:
                    return bad_request(f"该应用密钥关联 {count} 个连接，请先解除关联再删除")
                name = key.name
                key.delete()
                record_operation_log(request, "应用密钥", "删除密钥", name, f"ID={key_id}")
                return Response({"deleted": True})
            serializer = ApplicationKeySerializer(key, data=request.data, partial=True)
            if not serializer.is_valid():
                return bad_request(str(serializer.errors))
            key = serializer.save()
    except ProtectedError:
        return bad_request("该应用密钥已有关联连接，请先解除关联再删除")
    except IntegrityError:
        return bad_request("应用密钥名称已存在")
    record_operation_log(request, "应用密钥", "编辑密钥", key.name, f"ID={key.pk}")
    return Response(ApplicationKeySerializer(key).data)
