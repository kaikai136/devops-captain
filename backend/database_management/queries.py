from django.db import transaction
from django.http import HttpResponse
from django.utils.http import content_disposition_header
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import require_feature_permission
from operations.responses import bad_request, get_object_or_error
from system_management.services import record_operation_log

from .models import DatabaseAsset, SavedDatabaseQuery


def payload(item):
    return {"id": item.id, "assetId": item.asset_id, "database": item.database, "schema": item.schema,
            "name": item.name, "sql": item.sql, "pinned": item.pinned,
            "createdAt": item.created_at, "updatedAt": item.updated_at}


def allowed(request, action):
    return require_feature_permission(request, "databaseManagement", action, "没有应用管理权限")


def validate_fields(data):
    values = {}
    if "name" in data:
        values["name"] = str(data.get("name", "")).strip()
        if not values["name"] or len(values["name"]) > 160:
            raise ValueError("查询名称不能为空且最多 160 字符")
    if "sql" in data:
        values["sql"] = str(data.get("sql", ""))
        if len(values["sql"]) > 100000:
            raise ValueError("查询 SQL 最多 100000 字符")
    for field in ("database", "schema"):
        if field in data: values[field] = str(data.get(field, ""))[:160]
    if "pinned" in data: values["pinned"] = bool(data.get("pinned"))
    return values


@api_view(["GET", "POST"])
def saved_queries(request):
    denied = allowed(request, "view_data" if request.method == "GET" else "execute_sql")
    if denied: return denied
    if request.method == "GET":
        qs = SavedDatabaseQuery.objects.filter(owner=request.user)
        if request.query_params.get("assetId"): qs = qs.filter(asset_id=request.query_params["assetId"])
        if request.query_params.get("database") is not None: qs = qs.filter(database=request.query_params.get("database", ""))
        if request.query_params.get("schema") is not None: qs = qs.filter(schema=request.query_params.get("schema", ""))
        return Response([payload(item) for item in qs])
    asset, error = get_object_or_error(DatabaseAsset, pk=request.data.get("assetId"), error_message="数据库资产不存在")
    if error: return error
    data = request.data
    try:
        if data.get('imported'):
            denied = allowed(request, 'import_export')
            if denied: return denied
        values = validate_fields(data)
        if not values.get("name"): raise ValueError("查询名称不能为空")
        with transaction.atomic():
            item = SavedDatabaseQuery.objects.create(owner=request.user, asset=asset, database=values.get("database", ""),
                schema=values.get("schema", ""), name=values.get("name", ""), sql=values.get("sql", ""), pinned=values.get("pinned", False))
        record_operation_log(request, "应用管理", "新建数据库查询", item.name, f"资产={asset.name}")
        return Response(payload(item), status=201)
    except ValueError as exc: return bad_request(str(exc))
    except Exception: return bad_request("查询保存失败，名称可能已存在")


@api_view(['GET'])
def export_saved_query(request, query_id):
    for action in ('view_data', 'import_export'):
        denied = allowed(request, action)
        if denied: return denied
    item, error = get_object_or_error(SavedDatabaseQuery, pk=query_id, owner=request.user, error_message="查询不存在")
    if error: return error
    response = HttpResponse(item.sql, content_type='application/sql; charset=utf-8')
    response['Content-Disposition'] = content_disposition_header(True, f'{item.name}.sql')
    return response


@api_view(["PUT", "DELETE"])
def saved_query_detail(request, query_id):
    denied = allowed(request, "execute_sql")
    if denied: return denied
    item, error = get_object_or_error(SavedDatabaseQuery, pk=query_id, owner=request.user, error_message="查询不存在")
    if error: return error
    if request.method == "DELETE":
        name = item.name; item.delete(); record_operation_log(request, "应用管理", "删除数据库查询", name); return Response({"deleted": True})
    try:
        if "assetId" in request.data:
            asset, error = get_object_or_error(DatabaseAsset, pk=request.data["assetId"], error_message="数据库资产不存在")
            if error: return error
            item.asset = asset
        for field, value in validate_fields(request.data).items(): setattr(item, field, value)
        with transaction.atomic(): item.save()
        record_operation_log(request, "应用管理", "更新数据库查询", item.name)
        return Response(payload(item))
    except ValueError as exc: return bad_request(str(exc))
    except Exception: return bad_request("查询保存失败，名称可能已存在")
