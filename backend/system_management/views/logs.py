from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response

from operations.responses import paginate_queryset

from ..dashboard import build_dashboard_summary
from ..models import LoginLog, OperationLog
from ..serializers import LoginLogSerializer, OperationLogSerializer
from .common import require_dashboard_access, require_system_permission


def _query_datetime(value):
    parsed = parse_datetime(str(value or "").strip())
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _filter_created_at(queryset, request):
    start_time = _query_datetime(request.query_params.get("startTime"))
    end_time = _query_datetime(request.query_params.get("endTime"))
    if start_time:
        queryset = queryset.filter(created_at__gte=start_time)
    if end_time:
        queryset = queryset.filter(created_at__lte=end_time)
    return queryset


@api_view(["GET"])
def dashboard_summary(request):
    access_error = require_dashboard_access(request)
    if access_error:
        return access_error
    return Response(build_dashboard_summary())


@api_view(["GET"])
def login_logs(request):
    access_error = require_system_permission(request, "loginLogs")
    if access_error:
        return access_error

    queryset = LoginLog.objects.select_related("user")
    status_filter = str(request.query_params.get("status", "")).strip()
    username = str(request.query_params.get("username", "")).strip()
    ip_address = str(request.query_params.get("ip", request.query_params.get("ipAddress", ""))).strip()
    if status_filter in {LoginLog.STATUS_SUCCESS, LoginLog.STATUS_FAILED}:
        queryset = queryset.filter(status=status_filter)
    if username:
        queryset = queryset.filter(username__icontains=username)
    if ip_address:
        queryset = queryset.annotate(ip_address_text=Cast("ip_address", CharField())).filter(ip_address_text__icontains=ip_address)
    queryset = _filter_created_at(queryset, request)

    return Response(paginate_queryset(queryset, request, serializer=LoginLogSerializer, default_page_size=10))


@api_view(["GET"])
def operation_logs(request):
    access_error = require_system_permission(request, "operationLogs")
    if access_error:
        return access_error

    queryset = OperationLog.objects.select_related("user")
    username = str(request.query_params.get("username", "")).strip()
    module = str(request.query_params.get("module", "")).strip()
    action = str(request.query_params.get("action", "")).strip()
    keyword = str(request.query_params.get("keyword", "")).strip()
    ip_address = str(request.query_params.get("ip", request.query_params.get("ipAddress", ""))).strip()

    if username:
        queryset = queryset.filter(username__icontains=username)
    if module:
        queryset = queryset.filter(module__icontains=module)
    if action:
        queryset = queryset.filter(action__icontains=action)
    if keyword:
        queryset = queryset.filter(
            Q(target__icontains=keyword)
            | Q(detail__icontains=keyword)
            | Q(module__icontains=keyword)
            | Q(action__icontains=keyword)
            | Q(username__icontains=keyword)
        )
    if ip_address:
        queryset = queryset.annotate(ip_address_text=Cast("ip_address", CharField())).filter(ip_address_text__icontains=ip_address)
    queryset = _filter_created_at(queryset, request)

    return Response(paginate_queryset(queryset, request, serializer=OperationLogSerializer, default_page_size=10))
