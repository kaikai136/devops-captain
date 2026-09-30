from django.conf import settings
from django.db import models

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
