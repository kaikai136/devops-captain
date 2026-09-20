from django.conf import settings
from django.db import models


class BulkExecutionTask(models.Model):
    EXECUTION_SHELL = "shell"
    EXECUTION_FILE_UPLOAD = "file_upload"
    EXECUTION_CHOICES = [
        (EXECUTION_SHELL, "Shell"),
        (EXECUTION_FILE_UPLOAD, "File upload"),
    ]

    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELED, "Canceled"),
    ]

    name = models.CharField(max_length=180)
    command = models.TextField()
    execution_type = models.CharField(max_length=20, choices=EXECUTION_CHOICES, default=EXECUTION_SHELL)
    remote_directory = models.CharField(max_length=500, blank=True)
    upload_file = models.FileField(upload_to="bulk_execution_uploads/", blank=True)
    upload_filename = models.CharField(max_length=255, blank=True)
    upload_size = models.PositiveBigIntegerField(default=0)
    upload_overwrite = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="bulk_execution_tasks", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    cancel_requested = models.BooleanField(default=False)
    target_count = models.PositiveIntegerField(default=0)
    completed_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="bulk_task_status_idx"),
            models.Index(fields=["-created_at"], name="bulk_task_created_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class BulkExecutionUploadFile(models.Model):
    task = models.ForeignKey(BulkExecutionTask, related_name="upload_files", on_delete=models.CASCADE)
    file = models.FileField(upload_to="bulk_execution_uploads/", blank=True)
    filename = models.CharField(max_length=255)
    remote_path = models.CharField(max_length=700)
    size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["task"], name="bulk_upload_task_idx"),
        ]

    def __str__(self) -> str:
        return self.filename


class BulkExecutionResult(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    task = models.ForeignKey(BulkExecutionTask, related_name="results", on_delete=models.CASCADE)
    host = models.ForeignKey("host_management.ManagedHost", related_name="bulk_execution_results", null=True, blank=True, on_delete=models.SET_NULL)
    inventory_name = models.CharField(max_length=80)
    host_name = models.CharField(max_length=160)
    host_ip = models.GenericIPAddressField(protocol="IPv4")
    host_port = models.PositiveIntegerField(default=22)
    login_user = models.CharField(max_length=120, blank=True)
    os = models.CharField(max_length=40, blank=True)
    system_type = models.CharField(max_length=120, blank=True)
    system_arch = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    stdout = models.TextField(blank=True)
    stderr = models.TextField(blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    output_truncated = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["task", "status"], name="bulk_result_status_idx"),
            models.Index(fields=["host"], name="bulk_result_host_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.task_id}:{self.host_name}"


class BulkExecutionTransferItem(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    task = models.ForeignKey(BulkExecutionTask, related_name="transfer_items", on_delete=models.CASCADE)
    result = models.ForeignKey(BulkExecutionResult, related_name="transfers", on_delete=models.CASCADE)
    upload_file = models.ForeignKey(BulkExecutionUploadFile, related_name="transfers", on_delete=models.CASCADE)
    remote_path = models.CharField(max_length=700)
    size = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    stdout = models.TextField(blank=True)
    stderr = models.TextField(blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["task", "status"], name="bulk_transfer_status_idx"),
            models.Index(fields=["result"], name="bulk_transfer_result_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.result_id}:{self.remote_path}"
