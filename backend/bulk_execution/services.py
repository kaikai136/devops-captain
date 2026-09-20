from __future__ import annotations

import json
import os
import re
import shlex
import threading
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from types import SimpleNamespace

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import OperationalError, ProgrammingError, close_old_connections, transaction
from django.db.models import QuerySet
from django.utils import timezone

from host_management.models import ManagedHost
from web_terminal.services.commands import run_one_shot_ssh_command
from web_terminal.services.connections import open_ssh_client
from web_terminal.services.files import upload_remote_file_stream
from web_terminal.services.file_parsers import (
    join_remote_path,
    normalize_remote_file_name,
    normalize_remote_file_path,
    normalize_remote_relative_file_path,
    parent_remote_path,
)

from .models import BulkExecutionResult, BulkExecutionTask, BulkExecutionTransferItem, BulkExecutionUploadFile

MAX_COMMAND_LENGTH = 200000
OUTPUT_LIMIT = 200_000
DEFAULT_MAX_TARGETS = 500
DEFAULT_FORKS = 10
DEFAULT_TIMEOUT_SECONDS = 300

_interrupted_tasks_checked = False


def executable_targets_queryset() -> QuerySet[ManagedHost]:
    return (
        ManagedHost.objects.select_related("group", "created_by")
        .filter(verified=True, verify_status="verified")
        .exclude(os="windows")
        .exclude(login_user="")
    )


def has_ssh_credential(host: ManagedHost) -> bool:
    return bool(host.login_user and (host.login_password or host.private_key))


def list_executable_targets() -> list[ManagedHost]:
    return [host for host in executable_targets_queryset() if has_ssh_credential(host)]


def bulk_execution_settings() -> dict[str, int | bool]:
    max_targets = int(getattr(settings, "BULK_EXECUTION_MAX_TARGETS", DEFAULT_MAX_TARGETS))
    try:
        from system_management.services import get_database_setting_value
        from system_management.settings_defaults import TERMINAL_SETTINGS_FIELD_LIMITS

        terminal_settings = get_database_setting_value("terminal_settings")
        if isinstance(terminal_settings, dict) and "bulkExecutionMaxTargets" in terminal_settings:
            minimum, maximum = TERMINAL_SETTINGS_FIELD_LIMITS["bulkExecutionMaxTargets"]
            max_targets = max(minimum, min(maximum, int(terminal_settings["bulkExecutionMaxTargets"])))
    except (OperationalError, ProgrammingError, TypeError, ValueError):
        max_targets = int(getattr(settings, "BULK_EXECUTION_MAX_TARGETS", DEFAULT_MAX_TARGETS))
    return {
        "maxTargets": max(1, max_targets),
        "forks": int(getattr(settings, "BULK_EXECUTION_FORKS", DEFAULT_FORKS)),
        "timeoutSeconds": int(getattr(settings, "BULK_EXECUTION_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
        "runAsync": bool(getattr(settings, "BULK_EXECUTION_RUN_ASYNC", True)),
    }


def validate_max_targets(target_ids: list, max_targets: int) -> None:
    if len(target_ids) > max_targets:
        raise ValueError(f"每次最多选择 {max_targets} 台主机")


def create_bulk_execution_task(user, payload: dict) -> BulkExecutionTask:
    target_ids = payload.get("targetIds") or payload.get("target_ids") or payload.get("hostIds") or []
    if not isinstance(target_ids, list) or not target_ids:
        raise ValueError("Please select Linux SSH hosts")
    config = bulk_execution_settings()
    validate_max_targets(target_ids, int(config["maxTargets"]))
    try:
        target_ids = [int(item) for item in target_ids]
    except (TypeError, ValueError):
        raise ValueError("Invalid host selection")

    execution_type = str(payload.get("executionType") or payload.get("execution_type") or BulkExecutionTask.EXECUTION_SHELL).strip()
    if execution_type != BulkExecutionTask.EXECUTION_SHELL:
        raise ValueError("Unsupported execution type")

    task_name = require_task_name(payload)
    raw_command = str(payload.get("command", ""))
    if not raw_command.strip():
        raise ValueError("Please enter a command")
    if len(raw_command) > MAX_COMMAND_LENGTH:
        raise ValueError(f"Command cannot exceed {MAX_COMMAND_LENGTH} characters")
    command = raw_command.strip()

    hosts_by_id = {host.id: host for host in list_executable_targets() if host.id in set(target_ids)}
    hosts = [hosts_by_id[target_id] for target_id in target_ids if target_id in hosts_by_id]
    if not hosts:
        raise ValueError("No executable Linux SSH hosts selected")

    with transaction.atomic():
        task = BulkExecutionTask.objects.create(
            name=task_name,
            command=command,
            execution_type=execution_type,
            created_by=user if getattr(user, "is_authenticated", False) else None,
            target_count=len(hosts),
        )
        for index, host in enumerate(hosts, start=1):
            BulkExecutionResult.objects.create(
                task=task,
                host=host,
                inventory_name=f"host_{index}",
                host_name=host.name,
                host_ip=host.private_ip,
                host_port=host.port,
                login_user=host.login_user,
                os=host.os,
                system_type=host.system_type,
                system_arch=host.system_arch,
            )
    return task


def create_bulk_file_upload_task(user, payload: dict, uploaded_file) -> BulkExecutionTask:
    uploaded_files = normalize_uploaded_files(uploaded_file)
    if not uploaded_files:
        raise ValueError("Please select a file to upload")

    target_ids = parse_target_ids(payload.get("targetIds") or payload.get("target_ids") or payload.get("hostIds") or [])
    config = bulk_execution_settings()
    validate_max_targets(target_ids, int(config["maxTargets"]))

    remote_directory = normalize_remote_directory(str(payload.get("remoteDirectory") or payload.get("remote_directory") or "/tmp/"))
    hosts = executable_hosts_for_target_ids(target_ids)
    if not hosts:
        raise ValueError("No executable Linux SSH hosts selected")

    overwrite = parse_bool(payload.get("overwrite") or payload.get("uploadOverwrite") or payload.get("upload_overwrite"))
    task_name = require_task_name(payload)
    relative_paths = relative_paths_for_upload(payload, uploaded_files)
    uploaded_specs = []
    stored_names: list[str] = []
    try:
        for item, filename in zip(uploaded_files, relative_paths):
            if any(spec["filename"] == filename for spec in uploaded_specs):
                raise ValueError(f"Duplicate upload filename: {filename}")
            remote_path = join_remote_path(remote_directory, filename)
            if len(remote_path) > BulkExecutionUploadFile._meta.get_field("remote_path").max_length:
                raise ValueError("Upload remote path is too long")
            stored_name = default_storage.save(upload_storage_name(filename), item)
            stored_names.append(stored_name)
            uploaded_specs.append(
                {
                    "filename": filename,
                    "remote_path": remote_path,
                    "stored_name": stored_name,
                    "size": int(getattr(item, "size", 0) or default_storage.size(stored_name)),
                }
            )
        total_size = sum(spec["size"] for spec in uploaded_specs)
        summary_filename = uploaded_specs[0]["filename"] if len(uploaded_specs) == 1 else f"{len(uploaded_specs)} files"
        summary_file = uploaded_specs[0]["stored_name"] if len(uploaded_specs) == 1 else ""
        command_target = uploaded_specs[0]["remote_path"] if len(uploaded_specs) == 1 else remote_directory

        with transaction.atomic():
            task = BulkExecutionTask.objects.create(
                name=task_name,
                command=f"Upload {summary_filename} to {command_target}",
                execution_type=BulkExecutionTask.EXECUTION_FILE_UPLOAD,
                remote_directory=remote_directory,
                upload_file=summary_file,
                upload_filename=summary_filename,
                upload_size=total_size,
                upload_overwrite=overwrite,
                created_by=user if getattr(user, "is_authenticated", False) else None,
                target_count=len(hosts),
            )
            for spec in uploaded_specs:
                BulkExecutionUploadFile.objects.create(
                    task=task,
                    file=spec["stored_name"],
                    filename=spec["filename"],
                    remote_path=spec["remote_path"],
                    size=spec["size"],
                )
            create_results_for_hosts(task, hosts)
            create_transfer_items_for_uploads(task)
    except Exception:
        for stored_name in stored_names:
            if stored_name and default_storage.exists(stored_name):
                default_storage.delete(stored_name)
        raise
    return task


def require_task_name(payload: dict) -> str:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Please enter a task name")
    return name


def normalize_uploaded_files(uploaded_file) -> list:
    if uploaded_file is None:
        return []
    if isinstance(uploaded_file, (list, tuple)):
        return [item for item in uploaded_file if item is not None]
    return [uploaded_file]


def payload_list_value(payload: dict, *keys: str):
    for key in keys:
        if hasattr(payload, "getlist"):
            values = payload.getlist(key)
            if values:
                return values
        value = payload.get(key) if isinstance(payload, dict) or hasattr(payload, "get") else None
        if value not in (None, ""):
            return value
    return None


def relative_paths_for_upload(payload: dict, uploaded_files: list) -> list[str]:
    raw_paths = payload_list_value(payload, "relativePaths", "relative_paths")
    if raw_paths is None:
        raw_paths = [getattr(item, "name", "") for item in uploaded_files]
    elif isinstance(raw_paths, str):
        try:
            decoded = json.loads(raw_paths)
        except (TypeError, ValueError):
            decoded = [raw_paths]
        raw_paths = decoded
    if not isinstance(raw_paths, list) or len(raw_paths) != len(uploaded_files):
        raise ValueError("Uploaded file information is incomplete")
    return [normalize_upload_relative_path(str(value)) for value in raw_paths]


def normalize_upload_relative_path(value: str) -> str:
    raw_path = str(value or "").strip().replace("\\", "/")
    if not raw_path or raw_path.startswith("/") or "\x00" in raw_path or "\n" in raw_path or "\r" in raw_path:
        raise ValueError("Upload relative path is invalid")
    if re.match(r"^[A-Za-z]:", raw_path):
        raise ValueError("Upload relative path is invalid")
    raw_parts = raw_path.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("Upload relative path is invalid")
    normalized = normalize_remote_relative_file_path(raw_path)
    parts = [normalize_remote_file_name(part) for part in normalized.split("/")]
    relative_path = "/".join(parts)
    if len(relative_path) > BulkExecutionUploadFile._meta.get_field("filename").max_length:
        raise ValueError("Upload relative path is too long")
    return relative_path


def upload_storage_name(filename: str) -> str:
    basename = normalize_remote_file_name(filename)
    extension = os.path.splitext(basename)[1]
    prefix = "bulk_execution_uploads/"
    max_length = min(
        BulkExecutionUploadFile._meta.get_field("file").max_length,
        BulkExecutionTask._meta.get_field("upload_file").max_length,
    )
    extension_budget = max(0, max_length - len(prefix) - 32)
    return f"{prefix}{uuid.uuid4().hex}{extension[:extension_budget]}"


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_target_ids(value) -> list[int]:
    if isinstance(value, str):
        import json

        try:
            value = json.loads(value)
        except ValueError:
            value = [item for item in value.split(",") if item.strip()]
    if not isinstance(value, list) or not value:
        raise ValueError("Please select Linux SSH hosts")
    try:
        return [int(item) for item in value]
    except (TypeError, ValueError):
        raise ValueError("Invalid host selection")


def executable_hosts_for_target_ids(target_ids: list[int]) -> list[ManagedHost]:
    hosts_by_id = {host.id: host for host in list_executable_targets() if host.id in set(target_ids)}
    return [hosts_by_id[target_id] for target_id in target_ids if target_id in hosts_by_id]


def create_results_for_hosts(task: BulkExecutionTask, hosts: list[ManagedHost]) -> None:
    for index, host in enumerate(hosts, start=1):
        BulkExecutionResult.objects.create(
            task=task,
            host=host,
            inventory_name=f"host_{index}",
            host_name=host.name,
            host_ip=host.private_ip,
            host_port=host.port,
            login_user=host.login_user,
            os=host.os,
            system_type=host.system_type,
            system_arch=host.system_arch,
        )


def create_transfer_items_for_uploads(task: BulkExecutionTask) -> None:
    upload_files = list(task.upload_files.all())
    if not upload_files:
        return
    results = list(task.results.all())
    for result in results:
        for upload_file in upload_files:
            BulkExecutionTransferItem.objects.create(
                task=task,
                result=result,
                upload_file=upload_file,
                remote_path=upload_file.remote_path,
                size=upload_file.size,
            )


def normalize_remote_directory(value: str) -> str:
    directory = normalize_remote_file_path(value or "/tmp/")
    if directory != "/" and directory.endswith("/"):
        directory = directory.rstrip("/")
    return directory


def check_bulk_file_upload_targets(payload: dict) -> dict:
    target_ids = parse_target_ids(payload.get("targetIds") or payload.get("target_ids") or payload.get("hostIds") or [])
    config = bulk_execution_settings()
    validate_max_targets(target_ids, int(config["maxTargets"]))
    filenames_value = payload_list_value(payload, "filenames", "names") or []
    if isinstance(filenames_value, str):
        try:
            filenames_value = json.loads(filenames_value)
        except (TypeError, ValueError):
            filenames_value = [filenames_value]
    if not isinstance(filenames_value, list) or not filenames_value:
        raise ValueError("Please select files to upload")
    filenames = [normalize_upload_relative_path(str(name)) for name in filenames_value]
    remote_directory = normalize_remote_directory(str(payload.get("remoteDirectory") or payload.get("remote_directory") or "/tmp/"))
    hosts = executable_hosts_for_target_ids(target_ids)

    connected_targets = []
    unreachable_targets = []
    duplicate_files = []
    usable_target_ids = []
    for host in hosts:
        inspected = inspect_bulk_upload_target(host, remote_directory, filenames)
        if not inspected.get("connected"):
            unreachable_targets.append(target_payload(host, error=str(inspected.get("error") or "Connection failed")))
            continue
        connected_targets.append(target_payload(host))
        usable_target_ids.append(host.id)
        present_files = [str(item) for item in inspected.get("presentFiles", []) if str(item).strip()]
        if present_files:
            duplicate_files.append(
                {
                    "targetId": host.id,
                    "hostName": host.name,
                    "hostIp": str(host.private_ip),
                    "filenames": present_files,
                }
            )
    return {
        "connectedTargets": connected_targets,
        "unreachableTargets": unreachable_targets,
        "duplicateFiles": duplicate_files,
        "usableTargetIds": usable_target_ids,
    }


def target_payload(host: ManagedHost, *, error: str = "") -> dict:
    payload = {
        "id": host.id,
        "name": host.name,
        "group": host.group_id,
        "groupName": host.group.name if host.group_id and host.group else "",
        "privateIp": host.private_ip,
        "publicIp": host.public_ip,
        "port": host.port,
        "loginUser": host.login_user,
        "os": host.os,
        "systemType": host.system_type,
        "systemArch": host.system_arch,
        "verified": host.verified,
    }
    if error:
        payload["error"] = error
    return payload


def inspect_bulk_upload_target(host: ManagedHost, remote_directory: str, filenames: list[str]) -> dict:
    checks = []
    for filename in filenames:
        remote_path = join_remote_path(remote_directory, filename)
        checks.append(f"if test -e {shlex.quote(remote_path)}; then printf '%s\\n' {shlex.quote(filename)}; fi")
    command = "; ".join(checks) if checks else "true"
    try:
        output = run_one_shot_ssh_command(host, command)
    except Exception as error:
        return {"connected": False, "presentFiles": [], "error": str(error)}
    present = [line.strip() for line in output.splitlines() if line.strip()]
    return {"connected": True, "presentFiles": present, "error": ""}


def start_bulk_execution_task(task_id: int) -> None:
    if not bool(getattr(settings, "BULK_EXECUTION_RUN_ASYNC", True)):
        run_bulk_execution_task(task_id)
        return
    thread = threading.Thread(target=_run_task_safely, args=(task_id,), name=f"bulk-execution-{task_id}", daemon=True)
    thread.start()


def _run_task_safely(task_id: int) -> None:
    close_old_connections()
    try:
        run_bulk_execution_task(task_id)
    except Exception as error:
        BulkExecutionTask.objects.filter(id=task_id).update(status=BulkExecutionTask.STATUS_FAILED, error=str(error), finished_at=timezone.now())
    finally:
        close_old_connections()


def mark_interrupted_tasks() -> None:
    global _interrupted_tasks_checked
    if _interrupted_tasks_checked:
        return
    try:
        now = timezone.now()
        running_tasks = list(BulkExecutionTask.objects.filter(status=BulkExecutionTask.STATUS_RUNNING))
        BulkExecutionTask.objects.filter(id__in=[task.id for task in running_tasks]).update(
            status=BulkExecutionTask.STATUS_FAILED,
            error="Service restarted while the task was running",
            finished_at=now,
        )
        BulkExecutionResult.objects.filter(task_id__in=[task.id for task in running_tasks], status=BulkExecutionResult.STATUS_RUNNING).update(
            status=BulkExecutionResult.STATUS_FAILED,
            error="Service restarted while the task was running",
            finished_at=now,
        )
    except (OperationalError, ProgrammingError):
        return
    _interrupted_tasks_checked = True


def run_bulk_execution_task(task_id: int) -> None:
    task = BulkExecutionTask.objects.prefetch_related("results").get(id=task_id)
    task.status = BulkExecutionTask.STATUS_RUNNING
    task.started_at = task.started_at or timezone.now()
    task.finished_at = None
    task.error = ""
    task.save(update_fields=["status", "started_at", "finished_at", "error"])

    results = list(task.results.select_related("host").all())
    config = bulk_execution_settings()

    try:
        if not any(result.host_id for result in results):
            task.status = BulkExecutionTask.STATUS_FAILED
            task.error = "No available target host"
            mark_unfinished_results(task, BulkExecutionResult.STATUS_SKIPPED, task.error)
            return

        if task.execution_type == BulkExecutionTask.EXECUTION_FILE_UPLOAD:
            runner_result = run_file_upload(task, results, config)
        elif task.execution_type == BulkExecutionTask.EXECUTION_SHELL:
            runner_result = run_plain_shell_task(task, results, config)
        else:
            raise RuntimeError(f"Unsupported execution type: {task.execution_type}")

        task.refresh_from_db(fields=["cancel_requested"])
        canceled = bool(task.cancel_requested) or getattr(runner_result, "status", "") == "canceled"
        if canceled:
            mark_unfinished_transfers(task, BulkExecutionTransferItem.STATUS_SKIPPED, "Task canceled")
            mark_unfinished_results(task, BulkExecutionResult.STATUS_SKIPPED, "Task canceled")
            task.status = BulkExecutionTask.STATUS_CANCELED
        else:
            mark_unfinished_transfers(task, BulkExecutionTransferItem.STATUS_FAILED, "No result returned")
            mark_unfinished_results(task, BulkExecutionResult.STATUS_FAILED, "No result returned")
            task.status = final_task_status(task)
    except Exception as error:
        task.status = BulkExecutionTask.STATUS_FAILED
        task.error = str(error)
        mark_unfinished_transfers(task, BulkExecutionTransferItem.STATUS_FAILED, str(error))
        mark_unfinished_results(task, BulkExecutionResult.STATUS_FAILED, str(error))
    finally:
        task.finished_at = timezone.now()
        refresh_task_counts(task)
        task.save(update_fields=["status", "error", "finished_at", "completed_count", "success_count", "failed_count", "skipped_count"])
        cleanup_upload_file(task)


def run_plain_shell_task(task: BulkExecutionTask, results: list[BulkExecutionResult], config: dict[str, int | bool]):
    result_ids = [result.id for result in results if result.host_id]
    missing_results = [result for result in results if not result.host_id]
    for result in missing_results:
        mark_result(result, BulkExecutionResult.STATUS_SKIPPED, error="Host no longer exists")

    forks = max(1, min(len(result_ids) or 1, int(config["forks"])))
    timeout = int(config["timeoutSeconds"])
    if forks == 1:
        canceled = False
        for result_id in result_ids:
            if is_cancel_requested(task.id):
                canceled = True
                mark_plain_shell_result_skipped(task.id, result_id, "Task canceled")
                continue
            if run_plain_shell_result(task.id, result_id, task.command, timeout) == "canceled":
                canceled = True
        return SimpleNamespace(status="canceled" if canceled else "successful", rc=1 if canceled else 0)

    running = {}
    pending = list(result_ids)
    canceled = False

    with ThreadPoolExecutor(max_workers=forks, thread_name_prefix=f"bulk-shell-{task.id}") as executor:
        while pending or running:
            while pending and len(running) < forks:
                if is_cancel_requested(task.id):
                    canceled = True
                    mark_pending_plain_shell_results(pending)
                    pending = []
                    break
                result_id = pending.pop(0)
                future = executor.submit(run_plain_shell_result, task.id, result_id, task.command, timeout)
                running[future] = result_id

            if not running:
                break

            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                result_id = running.pop(future)
                try:
                    if future.result() == "canceled":
                        canceled = True
                except Exception as error:
                    mark_plain_shell_result_failed(task.id, result_id, str(error))
                if is_cancel_requested(task.id):
                    canceled = True

    return SimpleNamespace(status="canceled" if canceled else "successful", rc=1 if canceled else 0)


def mark_pending_plain_shell_results(result_ids: list[int]) -> None:
    now = timezone.now()
    BulkExecutionResult.objects.filter(id__in=result_ids, status=BulkExecutionResult.STATUS_PENDING).update(
        status=BulkExecutionResult.STATUS_SKIPPED,
        error="Task canceled",
        started_at=now,
        finished_at=now,
    )


def run_plain_shell_result(task_id: int, result_id: int, command: str, timeout: int) -> str:
    close_old_connections()
    try:
        if is_cancel_requested(task_id):
            mark_plain_shell_result_skipped(task_id, result_id, "Task canceled")
            return "canceled"

        result = BulkExecutionResult.objects.select_related("host").get(id=result_id)
        if result.host is None:
            mark_result(result, BulkExecutionResult.STATUS_SKIPPED, error="Host no longer exists")
            refresh_task_counts(BulkExecutionTask.objects.get(id=task_id))
            return "skipped"

        result.status = BulkExecutionResult.STATUS_RUNNING
        result.started_at = result.started_at or timezone.now()
        result.finished_at = None
        result.stdout = ""
        result.stderr = ""
        result.exit_code = None
        result.error = ""
        result.output_truncated = False
        result.save(
            update_fields=[
                "status",
                "started_at",
                "finished_at",
                "stdout",
                "stderr",
                "exit_code",
                "error",
                "output_truncated",
            ]
        )

        stdout_text, stderr_text, exit_code = run_plain_ssh_command(result.host, command, timeout)
        stdout, stdout_truncated = truncate_output(stdout_text)
        stderr, stderr_truncated = truncate_output(stderr_text)
        has_output = bool(stdout_text.strip() or stderr_text.strip())
        shell_success = exit_code == 0 or not has_output
        effective_exit_code = 0 if shell_success and exit_code != 0 and not has_output else exit_code
        result.status = BulkExecutionResult.STATUS_SUCCESS if shell_success else BulkExecutionResult.STATUS_FAILED
        result.stdout = stdout
        result.stderr = stderr
        result.exit_code = effective_exit_code
        result.error = "" if shell_success else stderr or f"远程命令退出码 {exit_code}"
        result.output_truncated = stdout_truncated or stderr_truncated
        result.finished_at = timezone.now()
        result.save(
            update_fields=[
                "status",
                "stdout",
                "stderr",
                "exit_code",
                "error",
                "output_truncated",
                "finished_at",
            ]
        )
        refresh_task_counts(BulkExecutionTask.objects.get(id=task_id))
        return "completed"
    except Exception as error:
        mark_plain_shell_result_failed(task_id, result_id, str(error))
        return "failed"
    finally:
        close_old_connections()


def run_plain_ssh_command(host: ManagedHost, command: str, timeout: int) -> tuple[str, str, int]:
    client = open_ssh_client(host)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=max(1, timeout))
        stdin.close()
        stdout_bytes = stdout.read()
        stderr_bytes = stderr.read()
        exit_code = stdout.channel.recv_exit_status()
        return (
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
            int(exit_code),
        )
    finally:
        client.close()


def mark_plain_shell_result_skipped(task_id: int, result_id: int, error: str) -> None:
    result = BulkExecutionResult.objects.get(id=result_id)
    mark_result(result, BulkExecutionResult.STATUS_SKIPPED, error=error)
    refresh_task_counts(BulkExecutionTask.objects.get(id=task_id))


def mark_plain_shell_result_failed(task_id: int, result_id: int, error: str) -> None:
    result = BulkExecutionResult.objects.get(id=result_id)
    result.status = BulkExecutionResult.STATUS_FAILED
    result.error = error
    result.started_at = result.started_at or timezone.now()
    result.finished_at = timezone.now()
    result.save(update_fields=["status", "error", "started_at", "finished_at"])
    refresh_task_counts(BulkExecutionTask.objects.get(id=task_id))


def run_file_upload(task: BulkExecutionTask, results: list[BulkExecutionResult], config: dict[str, int | bool]):
    upload_files = list(task.upload_files.all())
    if not upload_files and not task.upload_file:
        raise RuntimeError("No upload file attached to task")
    if not upload_files:
        filename = normalize_remote_file_name(task.upload_filename)
        remote_directory = normalize_remote_directory(task.remote_directory or "/tmp/")
        upload_files = [
            BulkExecutionUploadFile.objects.create(
                task=task,
                file=task.upload_file.name,
                filename=filename,
                remote_path=join_remote_path(remote_directory, filename),
                size=task.upload_size,
            )
        ]
        create_transfer_items_for_uploads(task)

    for upload_file in upload_files:
        if is_cancel_requested(task.id):
            return SimpleNamespace(status="canceled", rc=1)
        item_result = run_upload_file_item(task, upload_file, results, config)
        if getattr(item_result, "status", "") == "canceled":
            return item_result

    aggregate_file_upload_results(task)
    return SimpleNamespace(status="successful", rc=0)


def run_upload_file_item(
    task: BulkExecutionTask,
    upload_file: BulkExecutionUploadFile,
    results: list[BulkExecutionResult],
    config: dict[str, int | bool],
):
    result_by_id = {result.id: result for result in results}
    transfers = list(upload_file.transfers.select_related("result", "result__host").all())
    runnable_ids: list[int] = []
    for transfer in transfers:
        result = result_by_id.get(transfer.result_id) or transfer.result
        if result.host_id:
            runnable_ids.append(transfer.id)
        else:
            mark_upload_transfer_skipped(transfer, "Host no longer exists")

    if not runnable_ids:
        return SimpleNamespace(status="successful", rc=0)

    forks = max(1, min(len(runnable_ids), int(config["forks"])))
    if forks == 1:
        canceled = False
        for transfer_id in runnable_ids:
            if is_cancel_requested(task.id):
                canceled = True
                transfer = BulkExecutionTransferItem.objects.get(id=transfer_id)
                mark_upload_transfer_skipped(transfer, "Task canceled")
                continue
            if run_upload_transfer(task.id, transfer_id, task.upload_overwrite) == "canceled":
                canceled = True
        return SimpleNamespace(status="canceled" if canceled else "successful", rc=1 if canceled else 0)

    pending = list(runnable_ids)
    running = {}
    canceled = False

    with ThreadPoolExecutor(max_workers=forks, thread_name_prefix=f"bulk-upload-{task.id}") as executor:
        while pending or running:
            while pending and len(running) < forks:
                if is_cancel_requested(task.id):
                    canceled = True
                    break
                transfer_id = pending.pop(0)
                future = executor.submit(run_upload_transfer, task.id, transfer_id, task.upload_overwrite)
                running[future] = transfer_id

            if canceled:
                for transfer_id in pending:
                    transfer = BulkExecutionTransferItem.objects.get(id=transfer_id)
                    mark_upload_transfer_skipped(transfer, "Task canceled")
                pending = []

            if not running:
                break

            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                running.pop(future)
                try:
                    if future.result() == "canceled":
                        canceled = True
                except Exception:
                    pass
                if is_cancel_requested(task.id):
                    canceled = True

    return SimpleNamespace(status="canceled" if canceled else "successful", rc=1 if canceled else 0)


def run_upload_transfer(task_id: int, transfer_id: int, overwrite: bool) -> str:
    close_old_connections()
    try:
        if is_cancel_requested(task_id):
            transfer = BulkExecutionTransferItem.objects.select_related("result").get(id=transfer_id)
            mark_upload_transfer_skipped(transfer, "Task canceled")
            return "canceled"

        transfer = BulkExecutionTransferItem.objects.select_related("result__host", "upload_file").get(id=transfer_id)
        result = transfer.result
        host = result.host
        if host is None:
            mark_upload_transfer_skipped(transfer, "Host no longer exists")
            return "skipped"

        now = timezone.now()
        transfer.status = BulkExecutionTransferItem.STATUS_RUNNING
        transfer.started_at = transfer.started_at or now
        transfer.finished_at = None
        transfer.stdout = ""
        transfer.stderr = ""
        transfer.error = ""
        transfer.save(update_fields=["status", "started_at", "finished_at", "stdout", "stderr", "error"])

        result.status = BulkExecutionResult.STATUS_RUNNING
        result.started_at = result.started_at or now
        result.finished_at = None
        result.error = ""
        result.save(update_fields=["status", "started_at", "finished_at", "error"])

        if not overwrite and remote_path_exists(host, transfer.remote_path):
            raise FileExistsError(f"Remote file already exists: {transfer.remote_path}")

        upload_file = transfer.upload_file
        storage = upload_file.file.storage
        with storage.open(upload_file.file.name, "rb") as source:
            payload = upload_remote_file_stream(
                host,
                parent_remote_path(transfer.remote_path),
                transfer.remote_path.rstrip("/").split("/")[-1],
                source,
            )

        size = int(payload.get("size", transfer.size) or 0)
        protocol = str(payload.get("protocol") or "file transfer")
        stdout, truncated = truncate_output(f"Uploaded {size} bytes via {protocol}: {transfer.remote_path}\n")
        transfer.status = BulkExecutionTransferItem.STATUS_SUCCESS
        transfer.stdout = stdout
        transfer.finished_at = timezone.now()
        transfer.save(update_fields=["status", "stdout", "finished_at"])

        combined, combined_truncated = append_limited_output(result.stdout, stdout)
        result.stdout = combined
        result.output_truncated = result.output_truncated or truncated or combined_truncated
        result.save(update_fields=["stdout", "output_truncated"])
        return "completed"
    except Exception as error:
        transfer = BulkExecutionTransferItem.objects.select_related("result").get(id=transfer_id)
        message = str(error)
        transfer.status = BulkExecutionTransferItem.STATUS_FAILED
        transfer.error = message
        transfer.started_at = transfer.started_at or timezone.now()
        transfer.finished_at = timezone.now()
        transfer.save(update_fields=["status", "error", "started_at", "finished_at"])
        result = transfer.result
        result.error = message
        result.save(update_fields=["error"])
        return "failed"
    finally:
        close_old_connections()


def remote_path_exists(host: ManagedHost, path: str) -> bool:
    output = run_one_shot_ssh_command(
        host,
        f"if test -e {shlex.quote(path)}; then printf '%s' exists; fi",
    )
    return output.strip() == "exists"


def mark_upload_transfer_skipped(transfer: BulkExecutionTransferItem, error: str) -> None:
    transfer.status = BulkExecutionTransferItem.STATUS_SKIPPED
    transfer.error = error
    transfer.started_at = transfer.started_at or timezone.now()
    transfer.finished_at = timezone.now()
    transfer.save(update_fields=["status", "error", "started_at", "finished_at"])


def append_output(current: str, addition: str) -> str:
    if not current:
        return addition
    separator = "" if current.endswith("\n") or addition.startswith("\n") else "\n"
    return current + separator + addition


def aggregate_file_upload_results(task: BulkExecutionTask) -> None:
    for result in task.results.prefetch_related("transfers").all():
        transfers = list(result.transfers.all())
        if not transfers:
            continue
        if any(transfer.status == BulkExecutionTransferItem.STATUS_FAILED for transfer in transfers):
            result.status = BulkExecutionResult.STATUS_FAILED
            failed = next(transfer for transfer in transfers if transfer.status == BulkExecutionTransferItem.STATUS_FAILED)
            result.error = failed.error
        elif all(transfer.status == BulkExecutionTransferItem.STATUS_SUCCESS for transfer in transfers):
            result.status = BulkExecutionResult.STATUS_SUCCESS
            result.error = ""
        elif all(transfer.status == BulkExecutionTransferItem.STATUS_SKIPPED for transfer in transfers):
            result.status = BulkExecutionResult.STATUS_SKIPPED
            result.error = result.error or "Task canceled"
        else:
            result.status = BulkExecutionResult.STATUS_FAILED
            result.error = result.error or "Some upload transfers did not finish"
        result.started_at = result.started_at or timezone.now()
        result.finished_at = timezone.now()
        result.save(update_fields=["status", "error", "started_at", "finished_at"])


def cleanup_upload_file(task: BulkExecutionTask) -> None:
    if task.execution_type != BulkExecutionTask.EXECUTION_FILE_UPLOAD or not task.upload_file:
        if task.execution_type == BulkExecutionTask.EXECUTION_FILE_UPLOAD:
            cleanup_upload_files(task)
        return
    cleanup_upload_files(task)


def cleanup_upload_files(task: BulkExecutionTask) -> None:
    names = set()
    if task.upload_file:
        names.add(task.upload_file.name)
    for upload_file in task.upload_files.all():
        if upload_file.file:
            names.add(upload_file.file.name)
    try:
        storage = task.upload_file.storage if task.upload_file else default_storage
        for name in names:
            if name and storage.exists(name):
                storage.delete(name)
    except Exception:
        pass


def is_cancel_requested(task_id: int) -> bool:
    return bool(BulkExecutionTask.objects.filter(id=task_id, cancel_requested=True).exists())


def append_limited_output(current: str, addition: str) -> tuple[str, bool]:
    if not addition:
        return current, False
    return truncate_output(append_output(current, addition))


def truncate_output(value: str) -> tuple[str, bool]:
    if len(value) <= OUTPUT_LIMIT:
        return value, False
    return value[:OUTPUT_LIMIT], True


def mark_result(result: BulkExecutionResult, status: str, error: str = "") -> None:
    result.status = status
    result.error = error
    result.started_at = result.started_at or timezone.now()
    result.finished_at = timezone.now()
    result.save(update_fields=["status", "error", "started_at", "finished_at"])


def mark_unfinished_results(task: BulkExecutionTask, status: str, error: str) -> None:
    now = timezone.now()
    task.results.filter(status__in=[BulkExecutionResult.STATUS_PENDING, BulkExecutionResult.STATUS_RUNNING]).update(
        status=status,
        error=error,
        started_at=now,
        finished_at=now,
    )


def mark_unfinished_transfers(task: BulkExecutionTask, status: str, error: str) -> None:
    if task.execution_type != BulkExecutionTask.EXECUTION_FILE_UPLOAD:
        return
    now = timezone.now()
    task.transfer_items.filter(status__in=[BulkExecutionTransferItem.STATUS_PENDING, BulkExecutionTransferItem.STATUS_RUNNING]).update(
        status=status,
        error=error,
        started_at=now,
        finished_at=now,
    )


def final_task_status(task: BulkExecutionTask) -> str:
    if task.results.filter(status=BulkExecutionResult.STATUS_FAILED).exists():
        return BulkExecutionTask.STATUS_FAILED
    return BulkExecutionTask.STATUS_COMPLETED


def refresh_task_counts(task: BulkExecutionTask) -> None:
    task.refresh_from_db(fields=["id"])
    task.completed_count = task.results.filter(
        status__in=[BulkExecutionResult.STATUS_SUCCESS, BulkExecutionResult.STATUS_FAILED, BulkExecutionResult.STATUS_SKIPPED]
    ).count()
    task.success_count = task.results.filter(status=BulkExecutionResult.STATUS_SUCCESS).count()
    task.failed_count = task.results.filter(status=BulkExecutionResult.STATUS_FAILED).count()
    task.skipped_count = task.results.filter(status=BulkExecutionResult.STATUS_SKIPPED).count()
    task.save(update_fields=["completed_count", "success_count", "failed_count", "skipped_count"])
