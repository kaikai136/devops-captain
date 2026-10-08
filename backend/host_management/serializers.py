from rest_framework import serializers

from .models import HostCredential, HostGroup, ManagedHost


class ManagedHostSerializer(serializers.ModelSerializer):
    group = serializers.IntegerField(source="group_id")
    publicIp = serializers.IPAddressField(source="public_ip", required=False, allow_null=True)
    privateIp = serializers.IPAddressField(source="private_ip")
    port = serializers.IntegerField(required=False)
    loginUser = serializers.CharField(source="login_user", required=False, allow_blank=True)
    loginPassword = serializers.CharField(source="login_password", required=False, allow_blank=True)
    privateKeyName = serializers.CharField(source="private_key_name", required=False, allow_blank=True)
    privateKey = serializers.CharField(source="private_key", required=False, allow_blank=True)
    machineName = serializers.CharField(source="machine_name", read_only=True)
    systemArch = serializers.CharField(source="system_arch", read_only=True)
    systemType = serializers.CharField(source="system_type", read_only=True)
    verifyStatus = serializers.CharField(source="verify_status", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    creator = serializers.SerializerMethodField()
    platformType = serializers.SerializerMethodField()
    remark = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = ManagedHost
        fields = [
            "id",
            "name",
            "group",
            "publicIp",
            "privateIp",
            "port",
            "loginUser",
            "loginPassword",
            "privateKeyName",
            "privateKey",
            "machineName",
            "systemArch",
            "systemType",
            "remark",
            "cpu",
            "memory",
            "disk",
            "os",
            "verified",
            "verifyStatus",
            "createdAt",
            "updatedAt",
            "creator",
            "platformType",
        ]

    def get_creator(self, host: ManagedHost) -> str:
        return host.created_by.username if host.created_by_id and host.created_by else "system"

    def get_platformType(self, host: ManagedHost) -> str:
        return "windows" if (host.os or "").lower() == "windows" else "linux"


class HostCredentialSerializer(serializers.ModelSerializer):
    credentialType = serializers.ChoiceField(source="credential_type", choices=HostCredential.TYPE_CHOICES, required=False)
    privateKeyName = serializers.CharField(source="private_key_name", required=False, allow_blank=True)
    privateKey = serializers.CharField(source="private_key", required=False, allow_blank=True)

    class Meta:
        model = HostCredential
        fields = ["id", "name", "credentialType", "username", "password", "port", "privateKeyName", "privateKey", "remark"]


class HostGroupSerializer(serializers.ModelSerializer):
    key = serializers.IntegerField(source="id")
    label = serializers.CharField(source="name")
    count = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = HostGroup
        fields = ["key", "label", "count", "children"]

    def get_count(self, group: HostGroup) -> int:
        counts = self.context.get("counts", {})
        return counts.get(group.id, 0)

    def get_children(self, group: HostGroup) -> list[dict]:
        children = list(getattr(group, "_prefetched_children", []))
        return HostGroupSerializer(children, many=True, context=self.context).data
