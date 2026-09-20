from collections import defaultdict

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import require_feature_permission
from host_management.models import HostGroup
from host_management.serializers import HostGroupSerializer
from operations.responses import bad_request, get_object_or_error, paginate_queryset
from web_terminal.services.errors import TerminalConnectionError

from .models import BulkExecutionResult, BulkExecutionTask
from .serializers import BulkExecutionTaskDetailSerializer, BulkExecutionTaskSerializer
from .services import (
    check_bulk_file_upload_targets,
    create_bulk_execution_task,
    create_bulk_file_upload_task,
    list_executable_targets,
    mark_interrupted_tasks,
    refresh_task_counts,
    start_bulk_execution_task,
    target_payload,
)


def bulk_execution_permission(request, action_key: str | None = None):
    return require_feature_permission(request, "bulkExecution", action_key, "没有批量执行权限")


@api_view(["GET"])
def targets(request):
    auth_error = bulk_execution_permission(request, "execute")
    if auth_error:
        return auth_error
    hosts = list_executable_targets()
    return Response([target_payload(host) for host in hosts])


def target_group_tree_payload(hosts):
    groups = list(HostGroup.objects.all())
    groups_by_id = {group.id: group for group in groups}
    relevant_group_ids: set[int] = set()
    for host in hosts:
        group = groups_by_id.get(host.group_id)
        while group:
            relevant_group_ids.add(group.id)
            group = groups_by_id.get(group.parent_id)

    children_by_parent: dict[int | None, list[HostGroup]] = defaultdict(list)
    for group in groups:
        group._prefetched_children = []
        if group.id in relevant_group_ids:
            children_by_parent[group.parent_id].append(group)

    for group in groups:
        if group.id in relevant_group_ids:
            group._prefetched_children = children_by_parent[group.id]

    direct_counts: dict[int, int] = defaultdict(int)
    for host in hosts:
        direct_counts[host.group_id] += 1

    counts: dict[int, int] = {}

    def visit(group: HostGroup) -> int:
        total = direct_counts[group.id]
        for child in getattr(group, "_prefetched_children", []):
            total += visit(child)
        counts[group.id] = total
        return total

    roots = children_by_parent[None]
    for group in roots:
        visit(group)
    return HostGroupSerializer(roots, many=True, context={"counts": counts}).data


@api_view(["GET"])
def target_tree(request):
    auth_error = bulk_execution_permission(request, "execute")
    if auth_error:
        return auth_error
    hosts = list_executable_targets()
    return Response({"groups": target_group_tree_payload(hosts), "targets": [target_payload(host) for host in hosts]})


@api_view(["GET", "POST"])
def tasks(request):
    if request.method == "GET":
        auth_error = bulk_execution_permission(request, "refresh")
        if auth_error:
            return auth_error
        mark_interrupted_tasks()
        queryset = BulkExecutionTask.objects.select_related("created_by").filter(execution_type__in=[BulkExecutionTask.EXECUTION_SHELL, BulkExecutionTask.EXECUTION_FILE_UPLOAD])
        status_filter = str(request.query_params.get("status", "")).strip()
        keyword = str(request.query_params.get("keyword", "")).strip()
        host = str(request.query_params.get("host", "")).strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if keyword:
            queryset = queryset.filter(Q(name__icontains=keyword) | Q(command__icontains=keyword))
        if host:
            try:
                queryset = queryset.filter(results__host_id=int(host)).distinct()
            except (TypeError, ValueError):
                return bad_request("主机筛选条件无效")
        return Response(paginate_queryset(queryset, request, serializer=BulkExecutionTaskSerializer))

    auth_error = bulk_execution_permission(request, "execute")
    if auth_error:
        return auth_error
    try:
        payload = request.data if isinstance(request.data, dict) else {}
        if request.FILES.get("file") or str(payload.get("executionType") or payload.get("execution_type") or "") == "file_upload":
            files = request.FILES.getlist("files")
            task = create_bulk_file_upload_task(request.user, payload, files or request.FILES.get("file"))
        else:
            task = create_bulk_execution_task(request.user, payload)
    except (TypeError, ValueError, TerminalConnectionError) as error:
        return bad_request(error)
    start_bulk_execution_task(task.id)
    task.refresh_from_db()
    return Response(BulkExecutionTaskSerializer(task).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def upload_check(request):
    auth_error = bulk_execution_permission(request, "execute")
    if auth_error:
        return auth_error
    try:
        payload = request.data if isinstance(request.data, dict) else {}
        return Response(check_bulk_file_upload_targets(payload))
    except (TypeError, ValueError, TerminalConnectionError) as error:
        return bad_request(error)


@api_view(["GET", "DELETE"])
def task_detail(request, task_id: int):
    action = "delete" if request.method == "DELETE" else "refresh"
    auth_error = bulk_execution_permission(request, action)
    if auth_error:
        return auth_error
    task, error = get_object_or_error(
        BulkExecutionTask,
        queryset=BulkExecutionTask.objects.select_related("created_by").prefetch_related("upload_files", "results__transfers").filter(execution_type__in=[BulkExecutionTask.EXECUTION_SHELL, BulkExecutionTask.EXECUTION_FILE_UPLOAD]),
        id=task_id,
        error_message="批量执行任务不存在",
    )
    if error:
        return error
    if request.method == "DELETE":
        task.delete()
        return Response({"deleted": True})
    refresh_task_counts(task)
    task.refresh_from_db()
    return Response(BulkExecutionTaskDetailSerializer(task).data)


@api_view(["POST"])
def task_cancel(request, task_id: int):
    auth_error = bulk_execution_permission(request, "cancel")
    if auth_error:
        return auth_error
    task, error = get_object_or_error(BulkExecutionTask, id=task_id, error_message="批量执行任务不存在")
    if error:
        return error
    if task.status not in {BulkExecutionTask.STATUS_QUEUED, BulkExecutionTask.STATUS_RUNNING}:
        return bad_request("仅排队中或执行中的任务可以取消")
    task.cancel_requested = True
    if task.status == BulkExecutionTask.STATUS_QUEUED:
        now = timezone.now()
        task.status = BulkExecutionTask.STATUS_CANCELED
        task.finished_at = task.finished_at or now
        task.results.filter(status__in=[BulkExecutionResult.STATUS_PENDING, BulkExecutionResult.STATUS_RUNNING]).update(
            status=BulkExecutionResult.STATUS_SKIPPED,
            error="Task canceled",
            finished_at=now,
        )
        refresh_task_counts(task)
        task.save(update_fields=["cancel_requested", "status", "finished_at", "completed_count", "success_count", "failed_count", "skipped_count"])
    else:
        task.save(update_fields=["cancel_requested"])
    return Response({"cancelRequested": True, "status": task.status})
