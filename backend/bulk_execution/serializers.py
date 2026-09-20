from rest_framework import serializers

from .models import BulkExecutionResult, BulkExecutionTask, BulkExecutionTransferItem, BulkExecutionUploadFile


class BulkExecutionTaskSerializer(serializers.ModelSerializer):
    executionType = serializers.CharField(source="execution_type", read_only=True)
    remoteDirectory = serializers.CharField(source="remote_directory", read_only=True)
    uploadFilename = serializers.CharField(source="upload_filename", read_only=True)
    uploadSize = serializers.IntegerField(source="upload_size", read_only=True)
    cancelRequested = serializers.BooleanField(source="cancel_requested", read_only=True)
    targetCount = serializers.IntegerField(source="target_count", read_only=True)
    completedCount = serializers.IntegerField(source="completed_count", read_only=True)
    successCount = serializers.IntegerField(source="success_count", read_only=True)
    failedCount = serializers.IntegerField(source="failed_count", read_only=True)
    skippedCount = serializers.IntegerField(source="skipped_count", read_only=True)
    createdBy = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    startedAt = serializers.DateTimeField(source="started_at", read_only=True)
    finishedAt = serializers.DateTimeField(source="finished_at", read_only=True)

    class Meta:
        model = BulkExecutionTask
        fields = [
            "id",
            "name",
            "command",
            "executionType",
            "remoteDirectory",
            "uploadFilename",
            "uploadSize",
            "status",
            "cancelRequested",
            "targetCount",
            "completedCount",
            "successCount",
            "failedCount",
            "skippedCount",
            "error",
            "createdBy",
            "createdAt",
            "startedAt",
            "finishedAt",
        ]

    def get_createdBy(self, task: BulkExecutionTask) -> str:
        return task.created_by.username if task.created_by_id and task.created_by else "system"


class BulkExecutionResultSerializer(serializers.ModelSerializer):
    hostName = serializers.CharField(source="host_name", read_only=True)
    hostIp = serializers.IPAddressField(source="host_ip", read_only=True)
    hostPort = serializers.IntegerField(source="host_port", read_only=True)
    loginUser = serializers.CharField(source="login_user", read_only=True)
    systemType = serializers.CharField(source="system_type", read_only=True)
    systemArch = serializers.CharField(source="system_arch", read_only=True)
    exitCode = serializers.IntegerField(source="exit_code", read_only=True)
    outputTruncated = serializers.BooleanField(source="output_truncated", read_only=True)
    startedAt = serializers.DateTimeField(source="started_at", read_only=True)
    finishedAt = serializers.DateTimeField(source="finished_at", read_only=True)
    transfers = serializers.SerializerMethodField()

    class Meta:
        model = BulkExecutionResult
        fields = [
            "id",
            "host",
            "hostName",
            "hostIp",
            "hostPort",
            "loginUser",
            "os",
            "systemType",
            "systemArch",
            "status",
            "stdout",
            "stderr",
            "exitCode",
            "error",
            "outputTruncated",
            "startedAt",
            "finishedAt",
            "transfers",
        ]

    def get_transfers(self, result: BulkExecutionResult):
        return BulkExecutionTransferItemSerializer(result.transfers.all(), many=True).data


class BulkExecutionUploadFileSerializer(serializers.ModelSerializer):
    remotePath = serializers.CharField(source="remote_path", read_only=True)

    class Meta:
        model = BulkExecutionUploadFile
        fields = [
            "id",
            "filename",
            "remotePath",
            "size",
        ]


class BulkExecutionTransferItemSerializer(serializers.ModelSerializer):
    uploadFile = serializers.IntegerField(source="upload_file_id", read_only=True)
    remotePath = serializers.CharField(source="remote_path", read_only=True)
    startedAt = serializers.DateTimeField(source="started_at", read_only=True)
    finishedAt = serializers.DateTimeField(source="finished_at", read_only=True)

    class Meta:
        model = BulkExecutionTransferItem
        fields = [
            "id",
            "uploadFile",
            "remotePath",
            "size",
            "status",
            "stdout",
            "stderr",
            "error",
            "startedAt",
            "finishedAt",
        ]


class BulkExecutionTaskDetailSerializer(BulkExecutionTaskSerializer):
    results = serializers.SerializerMethodField()
    uploadFiles = serializers.SerializerMethodField()

    class Meta(BulkExecutionTaskSerializer.Meta):
        fields = BulkExecutionTaskSerializer.Meta.fields + ["uploadFiles", "results"]

    def get_results(self, task: BulkExecutionTask):
        return BulkExecutionResultSerializer(task.results.all(), many=True).data

    def get_uploadFiles(self, task: BulkExecutionTask):
        return BulkExecutionUploadFileSerializer(task.upload_files.all(), many=True).data
