from django.db import IntegrityError
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from accounts.permissions import require_feature_permission
from operations.responses import bad_request, get_object_or_error
from .models import DatabaseAsset
from .serializers import DatabaseAssetSerializer
from .services import connect, databases, tables, columns, table_data, connection_error
from .advanced import (
    types_view, sqlite_files, asset_tree, asset_objects, asset_columns_v2,
    asset_indexes, asset_schema,
    asset_data_v2, asset_sql, asset_redis, asset_export, asset_import,
    asset_rows, asset_transaction,
)
from . import adapters
from .catalog import directory_for, unique_name

def guard(request, action=None): return require_feature_permission(request, "databaseManagement", action, "没有应用管理权限")

def asset_payload(asset): return DatabaseAssetSerializer(asset).data

@api_view(["GET", "POST"])
def assets(request):
    error = guard(request, "view")
    if error: return error
    if request.method == "GET":
        keyword = request.query_params.get("keyword", "").strip()
        qs = DatabaseAsset.objects.all()
        if keyword: qs = qs.filter(name__icontains=keyword)
        if "directoryId" in request.query_params:
            try:
                folder = directory_for(request.query_params.get("directoryId"))
            except ValueError as exc: return bad_request(str(exc))
            qs = qs.filter(directory=folder)
        return Response(DatabaseAssetSerializer(qs, many=True).data)
    error = guard(request, "create")
    if error: return error
    serializer = DatabaseAssetSerializer(data=request.data)
    if not serializer.is_valid(): return bad_request(str(serializer.errors))
    try: unique_name(serializer.validated_data["name"], serializer.validated_data.get("directory"), DatabaseAsset)
    except ValueError as exc: return bad_request(str(exc))
    return Response(asset_payload(serializer.save(created_by=request.user)), status=status.HTTP_201_CREATED)

@api_view(["PUT", "DELETE"])
def asset_detail(request, asset_id):
    error = guard(request, "edit" if request.method == "PUT" else "delete")
    if error: return error
    asset, error = get_object_or_error(DatabaseAsset, id=asset_id, error_message="数据库资产不存在")
    if error: return error
    if request.method == "DELETE": asset.delete(); return Response({"deleted": True})
    serializer = DatabaseAssetSerializer(asset, data=request.data, partial=True)
    if not serializer.is_valid(): return bad_request(str(serializer.errors))
    try:
        unique_name(serializer.validated_data.get("name", asset.name), serializer.validated_data.get("directory", asset.directory), DatabaseAsset, asset.pk)
    except ValueError as exc: return bad_request(str(exc))
    return Response(asset_payload(serializer.save()))

@api_view(["POST"])
def asset_test(request, asset_id):
    error = guard(request, "test_connection")
    if error: return error
    asset, error = get_object_or_error(DatabaseAsset, id=asset_id, error_message="数据库资产不存在")
    if error: return error
    try:
        adapters.test(asset); return Response({"ok": True, "message": "连接成功"})
    except Exception as exc: return Response({"ok": False, "message": adapters.connection_error(exc)}, status=status.HTTP_400_BAD_REQUEST)

def selected_asset(request):
    asset, error = get_object_or_error(DatabaseAsset, id=request.query_params.get("asset"), error_message="数据库资产不存在")
    return asset, error

@api_view(["GET"])
def asset_databases(request):
    error = guard(request, "view_data")
    if error: return error
    asset, error = selected_asset(request)
    if error: return error
    try: return Response({"databases": databases(asset)})
    except Exception as exc: return bad_request(connection_error(exc))

@api_view(["GET"])
def asset_tables(request):
    error = guard(request, "view_data")
    if error: return error
    asset, error = selected_asset(request)
    if error: return error
    try: return Response({"tables": tables(asset, request.query_params.get("database", ""))})
    except Exception as exc: return bad_request(connection_error(exc))

@api_view(["GET"])
def asset_columns(request):
    error = guard(request, "view_data")
    if error: return error
    asset, error = selected_asset(request)
    if error: return error
    try: return Response({"columns": columns(asset, request.query_params.get("database", ""), request.query_params.get("table", ""))})
    except Exception as exc: return bad_request(connection_error(exc))

@api_view(["GET"])
def asset_data(request):
    error = guard(request, "view_data")
    if error: return error
    asset, error = selected_asset(request)
    if error: return error
    try:
        page = max(int(request.query_params.get("page", 1)), 1); page_size = min(max(int(request.query_params.get("pageSize", 25)), 1), 200)
        fields = [item for item in request.query_params.get("fields", "").split(",") if item]
        result = table_data(asset, request.query_params.get("database", ""), request.query_params.get("table", ""), fields, request.query_params.get("whereField"), request.query_params.get("whereValue"), request.query_params.get("sortField"), request.query_params.get("sortDirection", "asc"), page, page_size)
        return Response(result)
    except (ValueError, TypeError) as exc: return bad_request(str(exc))
    except Exception as exc: return bad_request(connection_error(exc))


