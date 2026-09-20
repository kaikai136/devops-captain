from __future__ import annotations

import base64
import shlex
import stat
import time
from uuid import uuid4

from host_management.models import ManagedHost

from .commands import run_one_shot_ssh_command, run_one_shot_ssh_upload
from .connections import borrow_sftp_client, borrow_ssh_client, ssh_client_pool_key
from .errors import TerminalConnectionError
from .file_parsers import (
    format_remote_timestamp,
    join_remote_path,
    natural_sort_key,
    normalize_remote_download_protocol,
    normalize_remote_file_name,
    normalize_remote_file_octal_mode,
    normalize_remote_file_owner,
    normalize_remote_file_path,
    normalize_remote_relative_file_path,
    normalize_remote_stat_identity,
    normalize_remote_symlink_target,
    parent_remote_entry,
    parent_remote_path,
    parse_remote_find_entries,
    parse_remote_ls_entries,
    parse_remote_stat_output,
    remote_file_properties_payload,
    remote_file_sort_key,
    remote_stat_command,
)


REMOTE_FILE_STREAM_CHUNK_BYTES = 1024 * 1024
REMOTE_IDENTITY_CACHE_TTL_SECONDS = 300.0
REMOTE_IDENTITY_CACHE_MAX_ENTRIES = 2048
_REMOTE_IDENTITY_CACHE: dict[tuple[tuple[str, str, int, str], str, str], tuple[float, str]] = {}

def list_remote_directory(host: ManagedHost, path: str) -> dict:
    path = normalize_remote_file_path(path or ".")
    return run_remote_file_operation(
        "目录读取失败",
        (
            ("SFTP protocol", lambda: list_remote_directory_with_sftp(host, path)),
            ("SCP (enhanced speed)", lambda: list_remote_directory_with_scp_enhanced(host, path)),
            ("SCP (normal speed)", lambda: list_remote_directory_with_scp_normal(host, path)),
        ),
        path,
    )

def download_remote_file(host: ManagedHost, path: str) -> dict:
    path = normalize_remote_file_path(path)
    return run_remote_file_operation(
        "文件下载失败",
        (
            ("SFTP protocol", lambda: download_remote_file_with_sftp(host, path)),
            ("SCP (enhanced speed)", lambda: download_remote_file_with_scp_enhanced(host, path)),
            ("SCP (normal speed)", lambda: download_remote_file_with_scp_normal(host, path)),
        ),
        path,
    )

def download_remote_file_content(host: ManagedHost, path: str) -> dict:
    path = normalize_remote_file_path(path)
    payload = run_remote_file_operation(
        "文件下载失败",
        (
            ("SFTP protocol", lambda: download_remote_file_content_with_sftp(host, path)),
            ("SCP (enhanced speed)", lambda: download_remote_file_content_with_scp_enhanced(host, path)),
            ("SCP (normal speed)", lambda: download_remote_file_content_with_scp_normal(host, path)),
        ),
        path,
    )
    return {"filename": path.rstrip("/").split("/")[-1] or "download", "content": payload["content"]}

def stream_remote_file_content(host: ManagedHost, path: str, protocol: str = "auto") -> dict:
    path = normalize_remote_file_path(path)
    protocol = normalize_remote_download_protocol(protocol)
    if protocol == "sftp":
        payload = stream_remote_file_content_with_sftp(host, path)
        payload.setdefault("path", path)
        payload.setdefault("protocol", "SFTP protocol")
        return payload
    if protocol == "scp":
        payload = stream_remote_file_content_with_scp(host, path)
        payload.setdefault("path", path)
        payload.setdefault("protocol", "SCP command")
        return payload
    try:
        payload = stream_remote_file_content_with_scp(host, path)
        payload.setdefault("path", path)
        payload.setdefault("protocol", "SCP command")
        return payload
    except Exception:
        payload = stream_remote_file_content_with_sftp(host, path)
        payload.setdefault("path", path)
        payload.setdefault("protocol", "SFTP protocol")
        return payload


def upload_remote_file_stream(host: ManagedHost, directory: str, filename: str, source, relative_path: str = "") -> dict:
    directory = normalize_remote_file_path(directory or ".")
    upload_name = normalize_remote_relative_file_path(relative_path) if str(relative_path or "").strip() else normalize_remote_file_name(filename)
    path = join_remote_path(directory, upload_name)
    return run_remote_file_operation(
        "文件上传失败",
        (
            ("SFTP protocol", lambda: upload_remote_file_with_sftp_stream(host, path, source)),
            ("SSH stream", lambda: upload_remote_file_with_ssh_stream(host, path, source)),
        ),
        path,
    )

def upload_remote_file(host: ManagedHost, directory: str, filename: str, content_base64: str, relative_path: str = "") -> dict:
    directory = normalize_remote_file_path(directory or ".")
    upload_name = normalize_remote_relative_file_path(relative_path) if str(relative_path or "").strip() else normalize_remote_file_name(filename)
    try:
        data = base64.b64decode(content_base64 or "", validate=False)
    except Exception as error:
        raise TerminalConnectionError(f"上传文件内容解析失败：{error}")
    path = join_remote_path(directory, upload_name)
    return run_remote_file_operation(
        "文件上传失败",
        (
            ("SFTP protocol", lambda: upload_remote_file_with_sftp(host, path, data)),
            ("SCP (enhanced speed)", lambda: upload_remote_file_with_scp_enhanced(host, path, data)),
            ("SCP (normal speed)", lambda: upload_remote_file_with_scp_normal(host, path, data)),
        ),
        path,
    )

def create_remote_file(host: ManagedHost, directory: str, filename: str, octal_mode: str = "") -> dict:
    directory = normalize_remote_file_path(directory or ".")
    filename = normalize_remote_file_name(filename)
    octal_mode = normalize_remote_file_octal_mode(octal_mode) if str(octal_mode or "").strip() else ""
    path = join_remote_path(directory, filename)
    run_one_shot_ssh_command(host, f"if test -e {shlex.quote(path)}; then printf %s {shlex.quote('目标已存在')} >&2; exit 1; fi; : > {shlex.quote(path)}")
    if octal_mode:
        run_one_shot_ssh_command(host, f"chmod {octal_mode} {shlex.quote(path)}")
    return get_remote_file_properties(host, path)

def create_remote_directory(host: ManagedHost, directory: str, dirname: str, octal_mode: str = "") -> dict:
    directory = normalize_remote_file_path(directory or ".")
    dirname = normalize_remote_file_name(dirname)
    octal_mode = normalize_remote_file_octal_mode(octal_mode) if str(octal_mode or "").strip() else ""
    path = join_remote_path(directory, dirname)
    run_one_shot_ssh_command(host, f"if test -e {shlex.quote(path)}; then printf %s {shlex.quote('目标已存在')} >&2; exit 1; fi; mkdir {shlex.quote(path)}")
    if octal_mode:
        run_one_shot_ssh_command(host, f"chmod {octal_mode} {shlex.quote(path)}")
    return get_remote_file_properties(host, path)

def create_remote_symlink(host: ManagedHost, directory: str, link_name: str, target_path: str) -> dict:
    directory = normalize_remote_file_path(directory or ".")
    link_name = normalize_remote_file_name(link_name)
    target_path = normalize_remote_symlink_target(target_path)
    path = join_remote_path(directory, link_name)
    run_one_shot_ssh_command(host, f"if test -e {shlex.quote(path)}; then printf %s {shlex.quote('目标已存在')} >&2; exit 1; fi; ln -s {shlex.quote(target_path)} {shlex.quote(path)}")
    return get_remote_file_properties(host, path)

def rename_remote_file(host: ManagedHost, path: str, new_name: str) -> dict:
    path = normalize_remote_file_path(path)
    new_name = normalize_remote_file_name(new_name)
    current = get_remote_file_properties(host, path)
    target = join_remote_path(str(current.get("directory") or parent_remote_path(path)), new_name)
    if target == current.get("path"):
        return current
    command = f"if test -e {shlex.quote(target)}; then printf %s {shlex.quote('目标已存在')} >&2; exit 1; fi; mv {shlex.quote(str(current.get('path') or path))} {shlex.quote(target)}"
    run_one_shot_ssh_command(host, command)
    return get_remote_file_properties(host, target)

def delete_remote_file(host: ManagedHost, path: str) -> dict:
    path = normalize_remote_file_path(path)
    current = get_remote_file_properties(host, path)
    current_path = str(current.get("path") or path)
    if current_path.rstrip("/") in {"", ".", "~", "/"}:
        raise TerminalConnectionError("不能删除根目录或当前目录")
    run_one_shot_ssh_command(host, f"rm -rf {shlex.quote(current_path)}")
    return {"deleted": True, "path": current_path, "directory": current.get("directory") or parent_remote_path(current_path)}

def get_remote_file_properties(host: ManagedHost, path: str) -> dict:
    path = normalize_remote_file_path(path)
    return run_remote_file_operation(
        "文件属性读取失败",
        (
            ("SFTP protocol", lambda: get_remote_file_properties_with_sftp(host, path)),
            ("SCP (normal speed)", lambda: get_remote_file_properties_with_stat(host, path)),
        ),
        path,
    )

def update_remote_file_properties(host: ManagedHost, path: str, owner: str, group: str, octal_mode: str, recursive: bool = False) -> dict:
    path = normalize_remote_file_path(path)
    owner = normalize_remote_file_owner(owner, "所有者")
    group = normalize_remote_file_owner(group, "组")
    octal_mode = normalize_remote_file_octal_mode(octal_mode)
    current = get_remote_file_properties(host, path)
    if recursive and current.get("type") != "directory":
        raise TerminalConnectionError("只有文件夹属性可以递归应用")

    quoted_path = shlex.quote(str(current.get("path") or path))
    recursive_flag = " -R" if recursive else ""
    run_one_shot_ssh_command(host, f"chmod{recursive_flag} {octal_mode} {quoted_path}")
    run_one_shot_ssh_command(host, f"chown{recursive_flag} {shlex.quote(owner + ':' + group)} {quoted_path}")
    updated = get_remote_file_properties(host, str(current.get("path") or path))
    updated["recursive"] = bool(recursive)
    return updated

def run_remote_file_operation(label: str, operations, path: str) -> dict:
    attempts: list[dict] = []
    for protocol, operation in operations:
        try:
            payload = operation()
            attempts.append({"protocol": protocol, "status": "success"})
            payload.setdefault("path", path)
            payload.update({"protocol": protocol, "attempts": attempts})
            return payload
        except Exception as error:
            attempts.append({"protocol": protocol, "status": "failed", "error": str(error)})
    raise TerminalConnectionError(label + "：" + "；".join(f"{item['protocol']} {item.get('error', '')}" for item in attempts))

def list_remote_directory_with_sftp(host: ManagedHost, path: str) -> dict:
    started_at = time.perf_counter()
    session_started_at = started_at
    with borrow_sftp_client(host) as (client, sftp, session_reused):
        session_ms = elapsed_ms(session_started_at)
        normalize_started_at = time.perf_counter()
        current_path = sftp.normalize(path)
        normalize_ms = elapsed_ms(normalize_started_at)

        read_started_at = time.perf_counter()
        remote_entries = sftp.listdir_attr(current_path)
        read_ms = elapsed_ms(read_started_at)
        entries = [
            {
                "name": item.filename,
                "type": "directory" if stat.S_ISDIR(item.st_mode) else "file",
                "modifiedAt": time.strftime("%Y/%m/%d %H:%M", time.localtime(item.st_mtime or 0)),
                "size": item.st_size or 0,
                "permissions": stat.filemode(item.st_mode),
                "owner": str(getattr(item, "st_uid", "") or ""),
                "group": str(getattr(item, "st_gid", "") or ""),
                "path": join_remote_path(current_path, item.filename),
            }
            for item in remote_entries
        ]

        identity_started_at = time.perf_counter()
        enrich_remote_entries_with_identities(host, client, entries)
        identity_ms = elapsed_ms(identity_started_at)

    sort_started_at = time.perf_counter()
    entries.sort(key=remote_file_sort_key)
    return {
        "path": current_path,
        "entries": [parent_remote_entry(current_path), *entries],
        "metrics": {
            "entryCount": len(entries),
            "sessionReused": session_reused,
            "sessionMs": session_ms,
            "normalizeMs": normalize_ms,
            "readMs": read_ms,
            "identityMs": identity_ms,
            "sortMs": elapsed_ms(sort_started_at),
            "totalMs": elapsed_ms(started_at),
        },
    }

def list_remote_directory_with_scp_enhanced(host: ManagedHost, path: str) -> dict:
    current_path = resolve_remote_directory_path(host, path)
    quoted_path = shlex.quote(current_path)
    command = f"find {quoted_path} -maxdepth 1 -mindepth 1 -printf '%f\\t%y\\t%TY/%Tm/%Td %TH:%TM\\t%s\\t%M\\t%u\\t%g\\n'"
    return {"path": current_path, "entries": parse_remote_find_entries(current_path, run_one_shot_ssh_command(host, command))}

def list_remote_directory_with_scp_normal(host: ManagedHost, path: str) -> dict:
    current_path = resolve_remote_directory_path(host, path)
    quoted_path = shlex.quote(current_path)
    command = f"ls -la --time-style=+%Y/%m/%d_%H:%M {quoted_path}"
    return {"path": current_path, "entries": parse_remote_ls_entries(current_path, run_one_shot_ssh_command(host, command))}

def get_remote_file_properties_with_sftp(host: ManagedHost, path: str) -> dict:
    with borrow_sftp_client(host) as (client, sftp, _session_reused):
        current_path = sftp.normalize(path)
        attrs = sftp.stat(current_path)
        try:
            stat_payload = parse_remote_stat_output(current_path, run_client_command(client, remote_stat_command(current_path)))
            stat_payload["path"] = current_path
            return stat_payload
        except Exception:
            return remote_file_properties_payload(current_path, attrs, resolve_remote_identity_names(client, attrs))

def get_remote_file_properties_with_stat(host: ManagedHost, path: str) -> dict:
    current_path = resolve_remote_file_path(host, path)
    return parse_remote_stat_output(current_path, run_one_shot_ssh_command(host, remote_stat_command(current_path)))

def resolve_remote_directory_path(host: ManagedHost, path: str) -> str:
    quoted_path = shlex.quote(path)
    command = f"cd {quoted_path} && pwd -P"
    resolved = run_one_shot_ssh_command(host, command).strip().splitlines()
    current_path = resolved[-1].strip() if resolved else ""
    if not current_path.startswith("/"):
        raise TerminalConnectionError("远端目录路径解析失败")
    return current_path

def resolve_remote_file_path(host: ManagedHost, path: str) -> str:
    quoted_path = shlex.quote(path)
    command = "python3 -c " + shlex.quote("import os, sys; print(os.path.realpath(os.path.expanduser(sys.argv[1])))") + " " + quoted_path
    try:
        resolved = run_one_shot_ssh_command(host, command).strip().splitlines()
    except Exception:
        resolved = run_one_shot_ssh_command(host, f"readlink -f {quoted_path}").strip().splitlines()
    current_path = resolved[-1].strip() if resolved else ""
    if not current_path.startswith("/"):
        raise TerminalConnectionError("远端文件路径解析失败")
    return current_path

def run_client_command(client, command: str, timeout: int = 20) -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    stdin.close()
    output = stdout.read()
    error_output = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        raise TerminalConnectionError(error_output or f"远端命令退出码 {exit_code}")
    return output.decode("utf-8", errors="replace")

def resolve_remote_identity_names(client, attrs) -> dict:
    uid = str(int(getattr(attrs, "st_uid", 0) or 0))
    gid = str(int(getattr(attrs, "st_gid", 0) or 0))
    return {
        "owner": resolve_remote_user_name(client, uid),
        "group": resolve_remote_group_name(client, gid),
    }

def resolve_remote_user_name(client, uid: str) -> str:
    return run_optional_client_command(client, f"getent passwd {shlex.quote(uid)} 2>/dev/null | cut -d: -f1") or run_optional_client_command(
        client,
        f"id -nu {shlex.quote(uid)} 2>/dev/null",
    )

def resolve_remote_group_name(client, gid: str) -> str:
    return run_optional_client_command(client, f"getent group {shlex.quote(gid)} 2>/dev/null | cut -d: -f1")

def run_optional_client_command(client, command: str, timeout: int = 10) -> str:
    try:
        output = run_client_command(client, command, timeout=timeout).strip().splitlines()
    except Exception:
        return ""
    return output[-1].strip() if output else ""

def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def enrich_remote_entries_with_identities(host: ManagedHost, client, entries: list[dict]) -> None:
    user_ids = {str(entry.get("owner") or "") for entry in entries if str(entry.get("owner") or "").isdigit()}
    group_ids = {str(entry.get("group") or "") for entry in entries if str(entry.get("group") or "").isdigit()}
    if not user_ids and not group_ids:
        return

    users, groups = resolve_remote_identity_names_batch(host, client, user_ids, group_ids)
    for entry in entries:
        owner = str(entry.get("owner") or "")
        group = str(entry.get("group") or "")
        entry["owner"] = users.get(owner) or owner
        entry["group"] = groups.get(group) or group


def resolve_remote_identity_names_batch(
    host: ManagedHost,
    client,
    user_ids: set[str],
    group_ids: set[str],
) -> tuple[dict[str, str], dict[str, str]]:
    pool_key = ssh_client_pool_key(host)
    now = time.monotonic()
    users: dict[str, str] = {}
    groups: dict[str, str] = {}
    missing_users: list[str] = []
    missing_groups: list[str] = []

    for kind, identities, resolved, missing in (
        ("user", user_ids, users, missing_users),
        ("group", group_ids, groups, missing_groups),
    ):
        for identity in sorted(identities):
            cached = _REMOTE_IDENTITY_CACHE.get((pool_key, kind, identity))
            if cached and now - cached[0] <= REMOTE_IDENTITY_CACHE_TTL_SECONDS:
                resolved[identity] = cached[1]
            else:
                missing.append(identity)

    if missing_users or missing_groups:
        command_parts = []
        for identity in missing_users:
            quoted = shlex.quote(identity)
            command_parts.append(
                f"printf 'U\\t{identity}\\t'; getent passwd {quoted} 2>/dev/null | cut -d: -f1 | head -n1; printf '\\n'"
            )
        for identity in missing_groups:
            quoted = shlex.quote(identity)
            command_parts.append(
                f"printf 'G\\t{identity}\\t'; getent group {quoted} 2>/dev/null | cut -d: -f1 | head -n1; printf '\\n'"
            )

        try:
            output = run_client_command(client, " ".join(command_parts), timeout=10)
        except Exception:
            output = ""

        for line in output.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            kind, identity, name = parts
            if kind == "U" and identity in user_ids:
                users[identity] = name.strip()
            elif kind == "G" and identity in group_ids:
                groups[identity] = name.strip()

        for kind, identities, resolved in (
            ("user", missing_users, users),
            ("group", missing_groups, groups),
        ):
            for identity in identities:
                _REMOTE_IDENTITY_CACHE[(pool_key, kind, identity)] = (now, resolved.get(identity, ""))

        if len(_REMOTE_IDENTITY_CACHE) > REMOTE_IDENTITY_CACHE_MAX_ENTRIES:
            overflow = len(_REMOTE_IDENTITY_CACHE) - REMOTE_IDENTITY_CACHE_MAX_ENTRIES
            oldest = sorted(_REMOTE_IDENTITY_CACHE.items(), key=lambda item: item[1][0])[:overflow]
            for key, _value in oldest:
                _REMOTE_IDENTITY_CACHE.pop(key, None)

    return users, groups


def enrich_remote_entries_with_stat(client, path: str, entries: list[dict]) -> None:
    if not entries:
        return

    command = f"find {shlex.quote(path)} -maxdepth 1 -mindepth 1 -printf '%f\\t%M\\t%u\\t%g\\n'"
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=20)
        stdin.close()
        output = stdout.read().decode("utf-8", errors="replace")
        if stdout.channel.recv_exit_status() != 0:
            return
    except Exception:
        return

    metadata = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        name, permissions, owner, group = parts[:4]
        metadata[name] = {"permissions": permissions, "owner": owner, "group": group}

    for entry in entries:
        entry.update(metadata.get(entry["name"], {}))

def download_remote_file_with_sftp(host: ManagedHost, path: str) -> dict:
    payload = download_remote_file_content_with_sftp(host, path)
    return encode_remote_download(path, payload["content"])

def download_remote_file_content_with_sftp(host: ManagedHost, path: str) -> dict:
    with borrow_sftp_client(host) as (_client, sftp, _session_reused):
        with sftp.open(path, "rb") as remote_file:
            data = remote_file.read()
        return {"content": data}

def stream_remote_file_content_with_sftp(host: ManagedHost, path: str) -> dict:
    with borrow_sftp_client(host) as (_client, sftp, _session_reused):
        attrs = sftp.stat(path)

    def chunks():
        with borrow_sftp_client(host) as (_client, sftp, _session_reused):
            with sftp.open(path, "rb") as remote_file:
                while True:
                    chunk = remote_file.read(REMOTE_FILE_STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk

    return {
        "filename": path.rstrip("/").split("/")[-1] or "download",
        "content": chunks(),
        "size": int(getattr(attrs, "st_size", 0) or 0),
    }

def stream_remote_file_content_with_scp(host: ManagedHost, path: str) -> dict:
    quoted_path = shlex.quote(path)
    with borrow_ssh_client(host) as client:
        _, stdout, stderr = client.exec_command(f"stat -c %s -- {quoted_path}", timeout=30)
        size_line = stdout.readline().strip()
        error_output = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            raise TerminalConnectionError(error_output or f"远端 stat 命令退出码 {exit_code}")
    try:
        size = int(size_line or "0")
    except ValueError:
        size = 0

    def chunks():
        with borrow_ssh_client(host) as client:
            _, stdout, stderr = client.exec_command(f"cat -- {quoted_path}", timeout=30)
            while True:
                chunk = stdout.read(REMOTE_FILE_STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                yield chunk
            error_output = stderr.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                raise TerminalConnectionError(error_output or f"远端下载命令退出码 {exit_code}")

    return {
        "filename": path.rstrip("/").split("/")[-1] or "download",
        "content": chunks(),
        "size": size,
    }

def download_remote_file_with_scp_enhanced(host: ManagedHost, path: str) -> dict:
    payload = download_remote_file_content_with_scp_enhanced(host, path)
    return encode_remote_download(path, payload["content"])

def download_remote_file_content_with_scp_enhanced(host: ManagedHost, path: str) -> dict:
    quoted_path = shlex.quote(path)
    command = f"base64 {quoted_path} | tr -d '\\n'"
    output = run_one_shot_ssh_command(host, command)
    return {"content": base64.b64decode(output.strip(), validate=False)}

def download_remote_file_with_scp_normal(host: ManagedHost, path: str) -> dict:
    payload = download_remote_file_content_with_scp_normal(host, path)
    return encode_remote_download(path, payload["content"])

def download_remote_file_content_with_scp_normal(host: ManagedHost, path: str) -> dict:
    quoted_path = shlex.quote(path)
    command = f"base64 {quoted_path} | tr -d '\\n'"
    output = run_one_shot_ssh_command(host, command)
    return {"content": base64.b64decode(output.strip(), validate=False)}

def upload_remote_file_with_sftp(host: ManagedHost, path: str, data: bytes) -> dict:
    from io import BytesIO

    return upload_remote_file_with_sftp_stream(host, path, BytesIO(data))


def upload_remote_file_with_sftp_stream(host: ManagedHost, path: str, source) -> dict:
    rewind_upload_source(source)
    temp_path = temporary_remote_upload_path(path)
    written = 0
    with borrow_sftp_client(host) as (_client, sftp, _session_reused):
        ensure_remote_sftp_directory(sftp, parent_remote_path(path))
        try:
            with sftp.open(temp_path, "wb") as remote_file:
                for chunk in iter_upload_chunks(source):
                    if not chunk:
                        continue
                    remote_file.write(chunk)
                    written += len(chunk)
            replace_remote_sftp_file(sftp, temp_path, path)
        except Exception:
            try:
                sftp.remove(temp_path)
            except Exception:
                pass
            raise
    return {"size": written}


def upload_remote_file_with_ssh_stream(host: ManagedHost, path: str, source) -> dict:
    rewind_upload_source(source)
    temp_path = temporary_remote_upload_path(path)
    quoted_path = shlex.quote(path)
    quoted_temp = shlex.quote(temp_path)
    quoted_parent = shlex.quote(parent_remote_path(path))
    command = f"mkdir -p {quoted_parent} && cat > {quoted_temp} && mv -f -- {quoted_temp} {quoted_path}"
    written = 0
    with borrow_ssh_client(host) as client:
        stdin, stdout, stderr = client.exec_command(command, timeout=60)
        try:
            for chunk in iter_upload_chunks(source):
                if not chunk:
                    continue
                stdin.write(chunk)
                written += len(chunk)
            stdin.channel.shutdown_write()
            error_output = stderr.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                raise TerminalConnectionError(error_output or f"远端上传命令退出码 {exit_code}")
        except Exception:
            try:
                client.exec_command(f"rm -f -- {quoted_temp}", timeout=10)
            except Exception:
                pass
            raise
    return {"size": written}


def iter_upload_chunks(source):
    chunks = getattr(source, "chunks", None)
    if callable(chunks):
        yield from chunks(REMOTE_FILE_STREAM_CHUNK_BYTES)
        return
    while True:
        chunk = source.read(REMOTE_FILE_STREAM_CHUNK_BYTES)
        if not chunk:
            return
        yield chunk


def rewind_upload_source(source) -> None:
    seek = getattr(source, "seek", None)
    if callable(seek):
        seek(0)


def temporary_remote_upload_path(path: str) -> str:
    parent = parent_remote_path(path)
    filename = path.rstrip("/").split("/")[-1] or "upload"
    return join_remote_path(parent, f".{filename}.upload-{uuid4().hex}")


def replace_remote_sftp_file(sftp, temp_path: str, path: str) -> None:
    posix_rename = getattr(sftp, "posix_rename", None)
    if callable(posix_rename):
        try:
            posix_rename(temp_path, path)
            return
        except Exception:
            pass
    try:
        sftp.remove(path)
    except Exception:
        pass
    sftp.rename(temp_path, path)


def ensure_remote_sftp_directory(sftp, directory: str) -> None:
    directory = str(directory or "").strip()
    if directory in {"", ".", "/", "~"}:
        return
    current = "/" if directory.startswith("/") else ""
    for part in [item for item in directory.split("/") if item]:
        current = f"{current.rstrip('/')}/{part}" if current else part
        try:
            sftp.stat(current)
        except Exception:
            sftp.mkdir(current)

def upload_remote_file_with_scp_enhanced(host: ManagedHost, path: str, data: bytes) -> dict:
    encoded = base64.b64encode(data)
    quoted_path = shlex.quote(path)
    quoted_parent = shlex.quote(parent_remote_path(path))
    run_one_shot_ssh_upload(host, f"mkdir -p {quoted_parent} && base64 -d > {quoted_path}", encoded)
    return {"size": len(data)}

def upload_remote_file_with_scp_normal(host: ManagedHost, path: str, data: bytes) -> dict:
    quoted_path = shlex.quote(path)
    quoted_parent = shlex.quote(parent_remote_path(path))
    run_one_shot_ssh_upload(host, f"mkdir -p {quoted_parent} && cat > {quoted_path}", data)
    return {"size": len(data)}

def encode_remote_download(path: str, data: bytes) -> dict:
    filename = path.rstrip("/").split("/")[-1] or "download"
    return {"filename": filename, "contentBase64": base64.b64encode(data).decode("ascii"), "size": len(data)}

__all__ = [
    'list_remote_directory',
    'download_remote_file',
    'download_remote_file_content',
    'stream_remote_file_content',
    'upload_remote_file_stream',
    'upload_remote_file',
    'create_remote_file',
    'create_remote_directory',
    'create_remote_symlink',
    'rename_remote_file',
    'delete_remote_file',
    'get_remote_file_properties',
    'update_remote_file_properties',
    'run_remote_file_operation',
    'list_remote_directory_with_sftp',
    'list_remote_directory_with_scp_enhanced',
    'list_remote_directory_with_scp_normal',
    'get_remote_file_properties_with_sftp',
    'get_remote_file_properties_with_stat',
    'resolve_remote_directory_path',
    'resolve_remote_file_path',
    'run_client_command',
    'resolve_remote_identity_names',
    'resolve_remote_user_name',
    'resolve_remote_group_name',
    'run_optional_client_command',
    'enrich_remote_entries_with_stat',
    'download_remote_file_with_sftp',
    'download_remote_file_content_with_sftp',
    'stream_remote_file_content_with_sftp',
    'stream_remote_file_content_with_scp',
    'download_remote_file_with_scp_enhanced',
    'download_remote_file_content_with_scp_enhanced',
    'download_remote_file_with_scp_normal',
    'download_remote_file_content_with_scp_normal',
    'upload_remote_file_with_sftp',
    'upload_remote_file_with_sftp_stream',
    'upload_remote_file_with_ssh_stream',
    'ensure_remote_sftp_directory',
    'upload_remote_file_with_scp_enhanced',
    'upload_remote_file_with_scp_normal',
    'encode_remote_download',
]
