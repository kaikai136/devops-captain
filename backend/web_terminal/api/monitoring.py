from rest_framework.decorators import api_view
from rest_framework.response import Response

from host_management.models import ManagedHost
from operations.responses import bad_request, get_object_or_error

from ..services import TerminalConnectionError, get_remote_resource_monitor
from .common import terminal_permission_required


@api_view(["POST"])
@terminal_permission_required
def terminal_monitor(request, host_id: int):
    host, error = get_object_or_error(ManagedHost, id=host_id, error_message="主机不存在")
    if error:
        return error
    if host.os == "windows":
        return bad_request("Windows 主机暂不支持资源监控")

    try:
        return Response(get_remote_resource_monitor(host))
    except TerminalConnectionError as error:
        return bad_request(error)
