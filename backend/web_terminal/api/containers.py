from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from host_management.models import ManagedHost
from operations.responses import bad_request, get_object_or_error
from system_management.services import record_operation_log

from ..models import TerminalSession
from ..services.audit import create_command_audit
from ..services.commands import run_one_shot_ssh_command
from ..services.containers import container_action_command, get_remote_containers, read_bounded_logs
from ..services.errors import TerminalConnectionError
from ..services.docker_resources import get_remote_docker_resources
from .common import terminal_permission_required


def container_host(host_id):
    host, error = get_object_or_error(ManagedHost, id=host_id, error_message="主机不存在")
    if not error and host.os == "windows":
        return None, bad_request("Windows 主机暂不支持容器监控")
    return host, error


def audit_container_operation(request, host, command, output, action):
    session = TerminalSession.objects.create(
        host=host, user=request.user, username=request.user.username,
        entrypoint="host-containers", status="closed", ended_at=timezone.now(),
    )
    create_command_audit(session, command, request.user, output=output[:4096])
    record_operation_log(request, "主机容器", action, host.name, f"{command}\n{output[:1000]}")


@api_view(["POST"])
@terminal_permission_required
def terminal_containers(request, host_id):
    host, error = container_host(host_id)
    if error is not None:
        return error
    try:
        return Response(get_remote_containers(host))
    except TerminalConnectionError as error:
        return bad_request(error)


@api_view(["POST"])
@terminal_permission_required
def terminal_container_action(request, host_id):
    host, error = container_host(host_id)
    if error is not None:
        return error
    command = ""
    try:
        command = container_action_command(host, request.data.get("containerId"), request.data.get("action"))
        output = run_one_shot_ssh_command(host, command)
    except (TerminalConnectionError, ValueError, TypeError) as error:
        audit_container_operation(request, host, command or "拒绝容器操作", str(error), "操作失败")
        return bad_request(error)
    audit_container_operation(request, host, command, output, "容器操作")
    return Response({"success": True})


@api_view(["POST"])
@terminal_permission_required
def terminal_container_logs(request, host_id):
    host, error = container_host(host_id)
    if error is not None:
        return error
    try:
        payload = read_bounded_logs(host, request.data.get("containerId"), request.data.get("tail", 200))
    except (TerminalConnectionError, ValueError, TypeError) as error:
        audit_container_operation(request, host, "docker logs", str(error), "日志读取失败")
        return bad_request(error)
    audit_container_operation(request, host, "docker logs", "读取成功", "查看日志")
    return Response(payload)


def docker_resource_response(request, host_id, resource):
    host, error = container_host(host_id)
    if error is not None:
        return error
    try:
        return Response(get_remote_docker_resources(host, resource))
    except TerminalConnectionError as error:
        return bad_request(error)


@api_view(["POST"])
@terminal_permission_required
def terminal_images(request, host_id):
    return docker_resource_response(request, host_id, "images")


@api_view(["POST"])
@terminal_permission_required
def terminal_networks(request, host_id):
    return docker_resource_response(request, host_id, "networks")


@api_view(["POST"])
@terminal_permission_required
def terminal_volumes(request, host_id):
    return docker_resource_response(request, host_id, "volumes")
