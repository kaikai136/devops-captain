from django.conf import settings
from django.db import models

import uuid


class AssetDirectory(models.Model):
    name = models.CharField(max_length=160)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

class DatabaseAsset(models.Model):
    DB_TYPES = [(key, label) for key, label in (
        ("mysql", "MySQL"), ("mariadb", "MariaDB"), ("postgresql", "PostgreSQL"),
        ("kingbase", "Kingbase"), ("sqlserver", "SQL Server"), ("sqlite", "SQLite"),
        ("redis", "Redis"), ("clickhouse", "ClickHouse"), ("oracle", "Oracle"),
        ("dameng", "Dameng"),
    )]
    name = models.CharField(max_length=160)
    db_type = models.CharField(max_length=20, choices=DB_TYPES, default="mysql")
    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=3306)
    username = models.CharField(max_length=120)
    password_encrypted = models.TextField(blank=True)
    database = models.CharField(max_length=120, blank=True)
    remark = models.TextField(blank=True)
    options = models.JSONField(default=dict, blank=True)
    directory = models.ForeignKey(AssetDirectory, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="database_assets")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-updated_at", "id"]
    def __str__(self):
        return self.name


class SavedDatabaseQuery(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_database_queries")
    asset = models.ForeignKey(DatabaseAsset, on_delete=models.CASCADE, related_name="saved_queries")
    database = models.CharField(max_length=160, blank=True)
    schema = models.CharField(max_length=160, blank=True)
    name = models.CharField(max_length=160)
    sql = models.TextField(blank=True)
    pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pinned", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "asset", "database", "schema", "name"], name="unique_saved_database_query"),
        ]

    def __str__(self):
        return self.name


class DatabaseTransferTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    DIRECTIONS = [(value, value) for value in ("import", "export")]
    STATUSES = [(value, value) for value in (
        "uploading", "inspecting", "awaiting_confirmation", "queued", "running",
        "cancel_requested", "cancelled", "succeeded", "failed", "expired",
    )]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="database_transfer_tasks")
    asset = models.ForeignKey(DatabaseAsset, null=True, blank=True, on_delete=models.SET_NULL, related_name="transfer_tasks")
    direction = models.CharField(max_length=8, choices=DIRECTIONS)
    scope = models.CharField(max_length=32)
    format = models.CharField(max_length=16, blank=True)
    database = models.CharField(max_length=160, blank=True)
    schema = models.CharField(max_length=160, blank=True)
    object_name = models.CharField(max_length=256, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    conflict_policy = models.CharField(max_length=24, blank=True)
    status = models.CharField(max_length=32, choices=STATUSES, default="queued", db_index=True)
    stage = models.CharField(max_length=64, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    processed_rows = models.BigIntegerField(default=0)
    processed_bytes = models.BigIntegerField(default=0)
    total_rows = models.BigIntegerField(null=True, blank=True)
    total_bytes = models.BigIntegerField(null=True, blank=True)
    preview = models.JSONField(default=dict, blank=True)
    checkpoints = models.JSONField(default=dict, blank=True)
    source_name = models.CharField(max_length=255, blank=True)
    input_path = models.CharField(max_length=1024, blank=True)
    output_path = models.CharField(max_length=1024, blank=True)
    error = models.TextField(blank=True)
    retry_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="retries")
    cancel_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
