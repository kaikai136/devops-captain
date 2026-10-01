"""Persistent asset folders and credential-free connection manifests."""

from django.db import transaction
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.permissions import require_feature_permission
from operations.responses import bad_request, get_object_or_error
from system_management.services import record_operation_log

from .models import AssetDirectory, DatabaseAsset
from .serializers import DatabaseAssetSerializer


def permitted(request, action):
    return require_feature_permission(request, "databaseManagement", action, "没有应用管理权限")


def directory_for(value):
    if value in (None, "", 0):
        return None
    try:
        return AssetDirectory.objects.get(pk=int(value))
    except (ValueError, TypeError, AssetDirectory.DoesNotExist) as exc:
        raise ValueError("资产目录不存在") from exc


def directory_payload(folder):
    return {"id": folder.id, "name": folder.name, "parentId": folder.parent_id}


def unique_name(name, parent, model, exclude=None):
    name = str(name or "").strip()
    if not name or len(name) > 160 or any(char in name for char in "/\\\x00"):
        raise ValueError("名称必须为 1 至 160 字符，且不能包含路径分隔符")
    existing = model.objects.filter(parent=parent, name=name) if model is AssetDirectory else model.objects.filter(directory=parent, name=name)
    if exclude:
        existing = existing.exclude(pk=exclude)
    if existing.exists():
        raise ValueError("当前目录已存在同名项目")
    return name


def copy_name(name, parent, model):
    for number in range(1, 1000):
        candidate = f"{name} - 副本" if number == 1 else f"{name} - 副本 {number}"
        if len(candidate) > 160:
            candidate = candidate[:160]
        try:
            return unique_name(candidate, parent, model)
        except ValueError:
            pass
    raise ValueError("无法生成不重复的名称")


def descendants(folder):
    seen = {folder.id}
    frontier = {folder.id}
    while frontier:
        frontier = set(AssetDirectory.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
        if frontier & seen or len(seen) + len(frontier) > 500:
            raise ValueError("目录层级异常或项目超过 500 个")
        seen |= frontier
    return seen


def duplicate_asset(asset, folder=None):
    folder = asset.directory if folder is None else folder
    return DatabaseAsset.objects.create(
        name=copy_name(asset.name, folder, DatabaseAsset), directory=folder,
        db_type=asset.db_type, host=asset.host, port=asset.port,
        username=asset.username, password_encrypted=asset.password_encrypted,
        database=asset.database, remark=asset.remark, options=dict(asset.options or {}),
        created_by=asset.created_by,
    )


@api_view(["GET", "POST"])
def directories(request):
    denied = permitted(request, "view" if request.method == "GET" else "create")
    if denied: return denied
    if request.method == "GET":
        return Response([directory_payload(item) for item in AssetDirectory.objects.all()])
    try:
        parent = directory_for(request.data.get("parentId"))
        name = unique_name(request.data.get("name"), parent, AssetDirectory)
        item = AssetDirectory.objects.create(name=name, parent=parent)
        record_operation_log(request, "应用管理", "新建资产目录", item.name, "")
        return Response(directory_payload(item), status=status.HTTP_201_CREATED)
    except ValueError as exc: return bad_request(str(exc))


@api_view(["PUT", "DELETE"])
def directory_detail(request, directory_id):
    denied = permitted(request, "edit" if request.method == "PUT" else "delete")
    if denied: return denied
    item, error = get_object_or_error(AssetDirectory, pk=directory_id, error_message="资产目录不存在")
    if error: return error
    try:
        with transaction.atomic():
            if request.method == "DELETE":
                ids = descendants(item)
                DatabaseAsset.objects.filter(directory_id__in=ids).delete()
                AssetDirectory.objects.filter(pk=item.pk).delete()
                record_operation_log(request, "应用管理", "删除资产目录", item.name, f"目录数={len(ids)}")
                return Response({"deleted": True})
            parent = directory_for(request.data.get("parentId", item.parent_id))
            if parent and parent.id in descendants(item):
                raise ValueError("不能把目录移动到自身或子目录")
            item.name = unique_name(request.data.get("name", item.name), parent, AssetDirectory, item.id)
            item.parent = parent
            item.save(update_fields=["name", "parent", "updated_at"])
            return Response(directory_payload(item))
    except ValueError as exc: return bad_request(str(exc))


@api_view(["POST"])
def directory_copy(request, directory_id):
    denied = permitted(request, "create")
    if denied: return denied
    source, error = get_object_or_error(AssetDirectory, pk=directory_id, error_message="资产目录不存在")
    if error: return error
    try:
        target = directory_for(request.data.get("parentId"))
        ids = descendants(source)
        if target and target.id in ids:
            raise ValueError("不能复制到自身或子目录")
        with transaction.atomic():
            def copy_branch(folder, parent):
                copied = AssetDirectory.objects.create(name=copy_name(folder.name, parent, AssetDirectory), parent=parent)
                for asset in folder.assets.all():
                    duplicate_asset(asset, copied)
                for child in folder.children.all():
                    copy_branch(child, copied)
                return copied
            result = copy_branch(source, target)
        record_operation_log(request, "应用管理", "复制资产目录", source.name, f"目录数={len(ids)}")
        return Response(directory_payload(result), status=status.HTTP_201_CREATED)
    except ValueError as exc: return bad_request(str(exc))


@api_view(["POST"])
def asset_copy(request, asset_id):
    denied = permitted(request, "create")
    if denied: return denied
    asset, error = get_object_or_error(DatabaseAsset, pk=asset_id, error_message="数据库资产不存在")
    if error: return error
    try:
        with transaction.atomic():
            folder = directory_for(request.data.get("directoryId", asset.directory_id))
            result = duplicate_asset(asset, folder)
        record_operation_log(request, "应用管理", "复制连接资产", asset.name, f"新资产 ID={result.pk}")
        return Response(DatabaseAssetSerializer(result).data, status=status.HTTP_201_CREATED)
    except ValueError as exc: return bad_request(str(exc))


@api_view(["POST"])
def asset_move(request, asset_id):
    denied = permitted(request, "edit")
    if denied: return denied
    asset, error = get_object_or_error(DatabaseAsset, pk=asset_id, error_message="数据库资产不存在")
    if error: return error
    try:
        folder = directory_for(request.data.get("directoryId"))
        unique_name(asset.name, folder, DatabaseAsset, asset.id)
        asset.directory = folder
        asset.save(update_fields=["directory", "updated_at"])
        record_operation_log(request, "应用管理", "移动连接资产", asset.name, f"目录 ID={folder.id if folder else 0}")
        return Response(DatabaseAssetSerializer(asset).data)
    except ValueError as exc: return bad_request(str(exc))


def exported_asset(asset, path):
    return {"directory": path, "name": asset.name, "dbType": asset.db_type,
            "host": asset.host, "port": asset.port, "username": asset.username,
            "databaseName": asset.database, "remark": asset.remark, "options": asset.options}


def import_manifest_payload(owner, manifest, directory_id=None, conflict_policy="rename"):
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("连接配置格式或版本不正确")
    folders, assets = manifest.get("directories"), manifest.get("assets")
    if not isinstance(folders, list) or not isinstance(assets, list):
        raise ValueError("连接配置项目格式不正确")
    target = directory_for(directory_id)
    mapping = {(): target}
    paths = {tuple(path) for path in folders if isinstance(path, list)}
    for item in assets:
        if not isinstance(item, dict) or not isinstance(item.get("directory"), list): raise ValueError("连接配置目录格式不正确")
        path = tuple(item["directory"]); paths.update(path[:index] for index in range(1, len(path) + 1))
    with transaction.atomic():
        for path in sorted(paths, key=lambda value: (len(value), value)):
            if not path or len(path) > 20 or any(not isinstance(part, str) for part in path): raise ValueError("连接配置目录层级或名称不正确")
            parent = mapping[path[:-1]]
            existing = AssetDirectory.objects.filter(parent=parent, name=path[-1]).first()
            if existing and conflict_policy == "skip": mapping[path] = existing; continue
            name = copy_name(path[-1], parent, AssetDirectory) if existing else path[-1]
            mapping[path] = AssetDirectory.objects.create(name=name, parent=parent)
        imported = 0
        for item in assets:
            folder = mapping[tuple(item["directory"])]
            payload = {key: value for key, value in item.items() if key in {"name", "dbType", "host", "port", "username", "databaseName", "remark", "options"}}
            existing = DatabaseAsset.objects.filter(directory=folder, name=payload.get("name", "")).first()
            if existing and conflict_policy == "skip": continue
            if existing and conflict_policy == "overwrite": existing.delete()
            if existing and conflict_policy == "rename": payload["name"] = copy_name(payload.get("name"), folder, DatabaseAsset)
            payload["directoryId"] = folder.id if folder else None
            serializer = DatabaseAssetSerializer(data=payload)
            if not serializer.is_valid(): raise ValueError(str(serializer.errors))
            serializer.save(created_by=owner); imported += 1
    return {"imported": imported}


@api_view(["GET", "POST"])
def connection_manifest(request):
    denied = permitted(request, "import_export")
    if denied: return denied
    if request.method == "GET":
        try:
            root = directory_for(request.query_params.get("directoryId"))
            ids = descendants(root) if root else None
            folders = AssetDirectory.objects.filter(pk__in=ids) if ids else AssetDirectory.objects.all()
            folder_by_id = {folder.id: folder for folder in AssetDirectory.objects.all()}
            def path_for(folder):
                path = []
                while folder:
                    path.insert(0, folder.name)
                    folder = folder_by_id.get(folder.parent_id)
                return path
            asset_id = request.query_params.get("assetId")
            if asset_id not in (None, ""):
                try:
                    assets = DatabaseAsset.objects.filter(pk=int(asset_id))
                except (TypeError, ValueError) as exc:
                    raise ValueError("assetId must be an integer") from exc
                if not assets.exists():
                    raise ValueError("asset not found")
                asset_folder_ids = {value for value in assets.values_list("directory_id", flat=True) if value}
                paths = [path_for(folder) for folder in folders if folder.id in asset_folder_ids]
            else:
                assets = DatabaseAsset.objects.filter(directory_id__in=ids) if ids else DatabaseAsset.objects.all()
                paths = [path_for(folder) for folder in folders]
            manifest = {"version": 1, "directories": paths,
                        "assets": [exported_asset(asset, path_for(folder_by_id.get(asset.directory_id))) for asset in assets]}
            record_operation_log(request, "应用管理", "导出连接配置", root.name if root else "全部", f"连接数={len(manifest['assets'])}")
            import json
            response = HttpResponse(json.dumps(manifest, ensure_ascii=False), content_type="application/json; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="database-connections.json"'
            return response
        except ValueError as exc: return bad_request(str(exc))
    manifest = request.data
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        return bad_request("连接配置格式或版本不正确")
    folders = manifest.get("directories")
    assets = manifest.get("assets")
    if not isinstance(folders, list) or not isinstance(assets, list) or len(folders) + len(assets) > 500:
        return bad_request("连接配置项目过多或格式不正确")
    try:
        target = directory_for(request.query_params.get("directoryId"))
        with transaction.atomic():
            mapping = {(): target}
            if any(not isinstance(path, list) or not all(isinstance(name, str) for name in path) for path in folders):
                raise ValueError("directory paths must contain strings")
            paths = {tuple(path) for path in folders}
            for item in assets:
                if not isinstance(item, dict) or not isinstance(item.get("directory"), list):
                    raise ValueError("连接配置目录格式不正确")
                path = tuple(item["directory"])
                if any(not isinstance(part, str) for part in path):
                    raise ValueError("directory paths must contain strings")
                paths.update(path[:index] for index in range(1, len(path) + 1))
            for path in sorted(paths, key=lambda value: (len(value), value)):
                if len(path) > 20 or not path or any(not isinstance(part, str) for part in path):
                    raise ValueError("连接配置目录层级或名称不正确")
                parent = mapping[path[:-1]]
                name = unique_name(path[-1], parent, AssetDirectory)
                mapping[path] = AssetDirectory.objects.create(name=name, parent=parent)
            for item in assets:
                path = tuple(item["directory"])
                folder = mapping[path]
                payload = {key: value for key, value in item.items() if key in {"name", "dbType", "host", "port", "username", "databaseName", "remark", "options"}}
                payload["directoryId"] = folder.id if folder else None
                payload["name"] = unique_name(payload.get("name"), folder, DatabaseAsset)
                serializer = DatabaseAssetSerializer(data=payload)
                if not serializer.is_valid():
                    raise ValueError(str(serializer.errors))
                serializer.save(created_by=request.user)
        record_operation_log(request, "应用管理", "导入连接配置", target.name if target else "根目录", f"连接数={len(assets)}")
        return Response({"imported": len(assets)}, status=status.HTTP_201_CREATED)
    except ValueError as exc: return bad_request(str(exc))
