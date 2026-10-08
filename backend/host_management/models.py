from django.conf import settings
from django.db import models


class HostGroup(models.Model):
    name = models.CharField(max_length=120)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.CASCADE)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="unique_host_group_name_per_parent"),
        ]

    def __str__(self) -> str:
        return self.name


class ManagedHost(models.Model):
    OS_CHOICES = [
        ("ubuntu", "Ubuntu"),
        ("centos", "CentOS"),
        ("debian", "Debian"),
        ("windows", "Windows"),
    ]
    VERIFY_STATUS_CHOICES = [
        ("unverified", "未验证"),
        ("verified", "已验证"),
        ("failed", "验证失败"),
    ]

    name = models.CharField(max_length=160)
    group = models.ForeignKey(HostGroup, related_name="hosts", on_delete=models.PROTECT)
    public_ip = models.GenericIPAddressField(protocol="IPv4", null=True, blank=True)
    private_ip = models.GenericIPAddressField(protocol="IPv4")
    port = models.PositiveIntegerField(default=22)
    login_user = models.CharField(max_length=120, blank=True)
    login_password = models.CharField(max_length=256, blank=True)
    private_key_name = models.CharField(max_length=180, blank=True)
    private_key = models.TextField(blank=True)
    remark = models.TextField(blank=True)
    machine_name = models.CharField(max_length=160, blank=True)
    system_arch = models.CharField(max_length=80, blank=True)
    system_type = models.CharField(max_length=80, blank=True)
    cpu = models.PositiveSmallIntegerField(default=2)
    memory = models.PositiveSmallIntegerField(default=4)
    disk = models.CharField(max_length=260, blank=True, default="")
    os = models.CharField(max_length=20, choices=OS_CHOICES, default="centos")
    verified = models.BooleanField(default=False)
    verify_status = models.CharField(max_length=20, choices=VERIFY_STATUS_CHOICES, default="unverified")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="managed_hosts", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class HostCredential(models.Model):
    TYPE_HOST = "host"
    TYPE_APPLICATION = "application"
    TYPE_CHOICES = [
        (TYPE_HOST, "主机密钥"),
        (TYPE_APPLICATION, "应用密钥"),
    ]
    name = models.CharField(max_length=120)
    credential_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_HOST)
    username = models.CharField(max_length=120, blank=True)
    password = models.CharField(max_length=256, blank=True)
    port = models.PositiveIntegerField(default=22)
    private_key_name = models.CharField(max_length=180, blank=True)
    private_key = models.TextField(blank=True)
    remark = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["name"], name="unique_host_credential_name"),
        ]

    def __str__(self) -> str:
        return self.name
