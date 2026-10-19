from rest_framework.decorators import api_view
from rest_framework.response import Response

from operations.responses import bad_request, paginate_queryset

from ..models import TerminalFileAudit
from ..serializers import TerminalFileAuditSerializer
from .common import session_audit_permission_required


@api_view(["GET"])
@session_audit_permission_required
def terminal_file_audits(request):
    queryset = TerminalFileAudit.objects.select_related("session", "host", "user")
    operation = str(request.query_params.get("operation", "")).strip().lower()
    protocol = str(request.query_params.get("protocol", "")).strip().lower()
    status = str(request.query_params.get("status", "")).strip().lower()
    host = str(request.query_params.get("host", "")).strip()
    username = str(request.query_params.get("username", "")).strip()
    search = str(request.query_params.get("search", "")).strip()

    allowed_operations = {choice for choice, _label in TerminalFileAudit.OPERATION_CHOICES}
    allowed_statuses = {choice for choice, _label in TerminalFileAudit.STATUS_CHOICES}
    if operation in allowed_operations:
        queryset = queryset.filter(operation=operation)
    if protocol:
        queryset = queryset.filter(protocol=protocol[:20])
    if status in allowed_statuses:
        queryset = queryset.filter(status=status)
    if username:
        queryset = queryset.filter(username__icontains=username)
    if search:
        queryset = queryset.filter(path__icontains=search)
    if host:
        try:
            queryset = queryset.filter(host_id=int(host))
        except (TypeError, ValueError):
            return bad_request("主机筛选条件无效")

    return Response(paginate_queryset(queryset, request, serializer=TerminalFileAuditSerializer))
