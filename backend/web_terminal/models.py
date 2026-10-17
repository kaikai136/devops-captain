import uuid

from django.conf import settings
from django.db import models

from host_management.models import ManagedHost


class TerminalQuickCommand(models.Model):
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=80)
    command = models.TextField()
    description = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "sort_order", "id"]
        indexes = [
            models.Index(fields=["category", "sort_order"], name="web_termina_categor_f4c5d1_idx"),
            models.Index(fields=["enabled"], name="web_termina_enabled_bf4f2f_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.category} / {self.name}"


class TerminalSession(models.Model):
    PROTOCOL_SSH = "ssh"
    PROTOCOL_RDP = "rdp"
    PROTOCOL_CHOICES = [
        (PROTOCOL_SSH, "SSH"),
        (PROTOCOL_RDP, "RDP"),
    ]

    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    host = models.ForeignKey(ManagedHost, related_name="terminal_sessions", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="terminal_sessions",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    username = models.CharField(max_length=150, blank=True)
    protocol = models.CharField(max_length=20, choices=PROTOCOL_CHOICES, default=PROTOCOL_SSH)
    entrypoint = models.CharField(max_length=40, blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    remote_username = models.CharField(max_length=120, blank=True)
    direct_mode = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="connected")
    transcript = models.TextField(blank=True)
    recording = models.TextField(blank=True)
    recording_file = models.CharField(max_length=500, blank=True)
    recording_enabled = models.BooleanField(default=False)
    recording_started_at = models.DateTimeField(null=True, blank=True)
    recording_last_event_at = models.DateTimeField(null=True, blank=True)
    recording_cols = models.PositiveSmallIntegerField(default=120)
    recording_rows = models.PositiveSmallIntegerField(default=36)
    recording_has_input = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_command_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.host.name} · {self.session_id}"


class TerminalFileAudit(models.Model):
    OPERATION_LIST = "list"
    OPERATION_READ = "read"
    OPERATION_WRITE = "write"
    OPERATION_MKDIR = "mkdir"
    OPERATION_REMOVE = "remove"
    OPERATION_RENAME = "rename"
    OPERATION_COPY = "copy"
    OPERATION_MOVE = "move"
    OPERATION_STAT = "stat"
    OPERATION_CHOICES = [
        (OPERATION_LIST, "List"),
        (OPERATION_READ, "Read"),
        (OPERATION_WRITE, "Write"),
        (OPERATION_MKDIR, "Mkdir"),
        (OPERATION_REMOVE, "Remove"),
        (OPERATION_RENAME, "Rename"),
        (OPERATION_COPY, "Copy"),
        (OPERATION_MOVE, "Move"),
        (OPERATION_STAT, "Stat"),
    ]
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    session = models.ForeignKey(
        TerminalSession,
        related_name="file_audits",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    host = models.ForeignKey(ManagedHost, related_name="terminal_file_audits", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="terminal_file_audits",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    username = models.CharField(max_length=150)
    protocol = models.CharField(max_length=20, default="sftp")
    operation = models.CharField(max_length=20, choices=OPERATION_CHOICES)
    path = models.TextField()
    target_path = models.TextField(blank=True)
    size = models.BigIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["-created_at", "-id"], name="web_termina_created_96fbd0_idx"),
            models.Index(fields=["host", "-created_at"], name="web_termina_host_id_c2932d_idx"),
            models.Index(fields=["username", "-created_at"], name="web_termina_usernam_9ea6bf_idx"),
            models.Index(fields=["operation", "-created_at"], name="web_termina_operati_16cfdc_idx"),
            models.Index(fields=["protocol", "-created_at"], name="web_termina_protoco_5f49d2_idx"),
            models.Index(fields=["status", "-created_at"], name="web_termina_status_6f082a_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.username} {self.protocol} {self.operation} {self.path[:80]}"


class TerminalCommandAudit(models.Model):
    RISK_ACCEPT = "accept"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CHOICES = [
        (RISK_ACCEPT, "接受"),
        (RISK_MEDIUM, "中风险"),
        (RISK_HIGH, "高风险"),
    ]

    session = models.ForeignKey(TerminalSession, related_name="command_audits", on_delete=models.CASCADE)
    host = models.ForeignKey(ManagedHost, related_name="terminal_command_audits", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="terminal_command_audits",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    username = models.CharField(max_length=150)
    command = models.TextField()
    output = models.TextField(blank=True)
    risk_level = models.CharField(max_length=20, choices=RISK_CHOICES, default=RISK_ACCEPT)
    asset_name = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    executed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-executed_at", "-id"]
        indexes = [
            models.Index(fields=["-executed_at", "-id"], name="web_termina_execute_21b4ee_idx"),
            models.Index(fields=["risk_level", "-executed_at"], name="web_termina_risk_le_c7d90c_idx"),
            models.Index(fields=["host", "-executed_at"], name="web_termina_host_id_0d2ee9_idx"),
            models.Index(fields=["session", "-executed_at"], name="web_termina_session_54a138_idx"),
            models.Index(fields=["username"], name="web_termina_usernam_7a859e_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.username} {self.command[:60]} {self.executed_at:%Y-%m-%d %H:%M:%S}"
