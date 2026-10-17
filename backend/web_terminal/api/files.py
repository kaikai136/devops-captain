import mimetypes
import re
from functools import wraps
from urllib.parse import quote

from django.http import HttpResponse, StreamingHttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from operations.responses import bad_request, get_object_or_error
from host_management.models import ManagedHost

from ..gateway.audit import record_file_audit
from ..services import (
    TerminalConnectionError,
    create_remote_directory,
    create_remote_file,
    create_remote_symlink,
    delete_remote_file,
    download_remote_file,
    get_remote_file_properties,
    list_remote_directory,
    rename_remote_file,
    transfer_remote_files,
    stream_remote_file_content,
    update_remote_file_content,
    update_remote_file_properties,
    upload_remote_file,
    upload_remote_file_stream,
)
from .common import terminal_permission_required
from ..services.errors import TerminalFileChangedError
from ..services.file_operations import FileOperationError


def with_terminal_host(view_func):
    """按 ``host_id`` 解析 ManagedHost 并统一处理终端异常。

    替代每个文件视图开头重复的「取 host → 404 / 捕获 TerminalConnectionError」样板。
    被包装的视图签名为 ``view(request, host, ...)``,直接拿到已解析的 host 实例。
    """

    @wraps(view_func)
    def wrapped(request, host_id: int, *args, **kwargs):
        host, error = get_object_or_error(ManagedHost, id=host_id, error_message="主机不存在")
        if error:
            return error
        try:
            return view_func(request, host, *args, **kwargs)
        except TerminalConnectionError as connection_error:
            return bad_request(connection_error)

    return wrapped


def audit_protocol(value) -> str:
    normalized = str(value or "").lower()
    if normalized in {"", "auto"}:
        return "auto"
    if "sftp" in normalized:
        return "sftp"
    if "scp" in normalized:
        return "scp"
    return "ssh"


def requested_upload_path(directory: str, relative_path: str, filename: str) -> str:
    name = relative_path or filename
    if directory in {"", "."}:
        return name
    if directory == "/":
        return "/" + name.lstrip("/")
    return directory.rstrip("/") + "/" + name.lstrip("/")


def audited_download_stream(content, *, host, user, path: str, protocol: str):
    transferred = 0
    try:
        for chunk in content:
            transferred += len(chunk or b"")
            yield chunk
    except BaseException as error:
        record_file_audit(
            operation="read",
            host=host,
            user=user,
            path=path,
            size=transferred,
            protocol=protocol,
            status="failed",
            error_message=str(error) or error.__class__.__name__,
        )
        raise
    else:
        record_file_audit(
            operation="read",
            host=host,
            user=user,
            path=path,
            size=transferred,
            protocol=protocol,
        )


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_list(request, host):
    return Response(list_remote_directory(host, str(request.data.get("path", "."))))


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_download_list(request, host):
    return Response(list_remote_directory(host, str(request.data.get("path", "."))))


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_download(request, host):
    return Response(download_remote_file(host, str(request.data.get("path", ""))))


@api_view(["GET"])
@terminal_permission_required
@with_terminal_host
def terminal_file_download_attachment(request, host):
    return file_content_response(request, host)


def file_content_response(request, host, *, preview=False):
    requested_path = str(request.query_params.get("path", ""))
    requested_protocol = str(request.query_params.get("protocol", "auto"))
    try:
        payload = stream_remote_file_content(host, requested_path, requested_protocol)
        filename = str(payload.get("filename") or "download")
        content = payload.get("content") or b""
    except TerminalConnectionError as error:
        record_file_audit(
            operation="read",
            host=host,
            user=request.user,
            path=requested_path,
            protocol=audit_protocol(requested_protocol),
            status="failed",
            error_message=str(error),
        )
        return bad_request(error)
    except Exception as error:
        record_file_audit(
            operation="read",
            host=host,
            user=request.user,
            path=requested_path,
            protocol=audit_protocol(requested_protocol),
            status="failed",
            error_message=str(error),
        )
        return bad_request("文件下载失败")

    protocol = audit_protocol(payload.get("protocol"))
    path = str(payload.get("path") or requested_path)
    if isinstance(content, (bytes, bytearray)):
        record_file_audit(
            operation="read",
            host=host,
            user=request.user,
            path=path,
            size=len(content),
            protocol=protocol,
        )
        response = HttpResponse(content, content_type="application/octet-stream")
    else:
        response = StreamingHttpResponse(
            audited_download_stream(content, host=host, user=request.user, path=path, protocol=protocol),
            content_type="application/octet-stream",
        )
    if preview:
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        response["Content-Type"] = mime
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        response["Cache-Control"] = "no-store"
    disposition = "inline" if preview else "attachment"
    response["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{quote(filename)}"
    if "size" in payload:
        response["Content-Length"] = str(int(payload.get("size") or 0))
    else:
        response["Content-Length"] = str(len(content))
    return response


@api_view(["GET"])
@terminal_permission_required
@with_terminal_host
def terminal_file_content(request, host):
    return file_content_response(request, host, preview=True)


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_content_update(request, host):
    requested_path = str(request.data.get("path", ""))
    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return bad_request("请选择文件内容")
    expected_hash = request.data.get("expected_hash")
    force_value = request.data.get("force", "false")
    if force_value not in ("true", "false"):
        return bad_request("force 必须为 true 或 false")
    force = force_value == "true"
    if not force and (not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)):
        return bad_request("缺少有效的文件内容基线，请重新打开文件")
    try:
        payload = update_remote_file_content(host, requested_path, uploaded_file, expected_hash=expected_hash, force=force)
        record_file_audit(
            operation="write", host=host, user=request.user, path=requested_path,
            size=int(payload.get("size") or getattr(uploaded_file, "size", 0) or 0),
            protocol=audit_protocol(payload.get("protocol")),
        )
        return Response(payload)
    except TerminalFileChangedError as error:
        record_file_audit(
            operation="write", host=host, user=request.user, path=requested_path,
            protocol="auto", status="failed", error_message=str(error),
        )
        return Response({"code": "file_changed", "error": str(error)}, status=409)
    except TerminalConnectionError as error:
        record_file_audit(
            operation="write", host=host, user=request.user, path=requested_path,
            protocol="auto", status="failed", error_message=str(error),
        )
        return bad_request(error)
    except Exception as error:
        record_file_audit(
            operation="write", host=host, user=request.user, path=requested_path,
            protocol="auto", status="failed", error_message=str(error) or error.__class__.__name__,
        )
        return bad_request("文件保存失败")


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_upload(request, host):
    uploaded_file = request.FILES.get("file")
    directory = str(request.data.get("directory", "."))
    filename = str(request.data.get("filename", ""))
    relative_path = str(request.data.get("relativePath", ""))

    try:
        if uploaded_file is not None:
            payload = upload_remote_file_stream(
                host,
                directory,
                filename or uploaded_file.name,
                uploaded_file,
                relative_path,
            )
        else:
            payload = upload_remote_file(
                host,
                directory,
                filename,
                str(request.data.get("contentBase64", "")),
                relative_path,
            )
    except TerminalConnectionError as error:
        record_file_audit(
            operation="write",
            host=host,
            user=request.user,
            path=requested_upload_path(directory, relative_path, filename or getattr(uploaded_file, "name", "")),
            size=0,
            protocol="auto",
            status="failed",
            error_message=str(error),
        )
        raise

    record_file_audit(
        operation="write",
        host=host,
        user=request.user,
        path=str(payload.get("path") or relative_path or filename),
        size=int(payload.get("size") or getattr(uploaded_file, "size", 0) or 0),
        protocol=audit_protocol(payload.get("protocol")),
    )
    return Response(payload)


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_create_file(request, host):
    return Response(
        create_remote_file(
            host,
            str(request.data.get("directory", ".")),
            str(request.data.get("filename", "")),
            str(request.data.get("octalMode", "")),
        )
    )


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_create_directory(request, host):
    return Response(
        create_remote_directory(
            host,
            str(request.data.get("directory", ".")),
            str(request.data.get("dirname", "")),
            str(request.data.get("octalMode", "")),
        )
    )


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_create_symlink(request, host):
    return Response(
        create_remote_symlink(
            host,
            str(request.data.get("directory", ".")),
            str(request.data.get("linkName", "")),
            str(request.data.get("targetPath", "")),
        )
    )


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_rename(request, host):
    return Response(rename_remote_file(host, str(request.data.get("path", "")), str(request.data.get("newName", ""))))


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_delete(request, host):
    return Response(delete_remote_file(host, str(request.data.get("path", ""))))

@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_transfer(request, host):
    paths = request.data.get("paths", [])
    if not isinstance(paths, list) or not 1 <= len(paths) <= 200 or any(not isinstance(path, str) or not path.strip() for path in paths):
        return Response({"code": "invalid_path", "error": "请选择 1 至 200 个有效文件路径"}, status=400)
    operation = str(request.data.get("operation", ""))
    target_directory = request.data.get("targetDirectory", ".")
    if not isinstance(target_directory, str) or not target_directory.strip():
        return Response({"code": "invalid_directory", "error": "请输入目标目录"}, status=400)
    overwrite = request.data.get("overwrite", False)
    if not isinstance(overwrite, bool) or operation not in {"copy", "move"}:
        return Response({"code": "invalid_operation", "error": "操作或覆盖参数不合法"}, status=400)
    audit_operation = operation
    try:
        payload = transfer_remote_files(host, paths, target_directory, operation, overwrite)
        for item in payload.get("items", []):
            record_file_audit(operation=audit_operation, host=host, user=request.user, path=item["path"], target_path=item["targetPath"], protocol="sftp")
        return Response(payload)
    except Exception as error:
        for path in paths:
            record_file_audit(operation=audit_operation, host=host, user=request.user, path=path, target_path=target_directory, protocol="sftp", status="failed", error_message=str(error))
        if isinstance(error, FileOperationError):
            return Response({"code": error.code, "error": str(error)}, status=error.status)
        return Response({"code": "file_operation_failed", "error": "文件操作失败，请检查远端连接及权限"}, status=400)


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_properties(request, host):
    return Response(get_remote_file_properties(host, str(request.data.get("path", ""))))


@api_view(["POST"])
@terminal_permission_required
@with_terminal_host
def terminal_file_properties_update(request, host):
    return Response(
        update_remote_file_properties(
            host,
            str(request.data.get("path", "")),
            str(request.data.get("owner", "")),
            str(request.data.get("group", "")),
            str(request.data.get("octalMode", "")),
            bool(request.data.get("recursive", False)),
        )
    )
