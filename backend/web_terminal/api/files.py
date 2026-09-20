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
    stream_remote_file_content,
    update_remote_file_properties,
    upload_remote_file,
    upload_remote_file_stream,
)
from .common import terminal_permission_required


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
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    if "size" in payload:
        response["Content-Length"] = str(int(payload.get("size") or 0))
    else:
        response["Content-Length"] = str(len(content))
    return response


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
