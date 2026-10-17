from __future__ import annotations

import errno
import posixpath
import stat
from uuid import uuid4

from .connections import borrow_sftp_client
from .errors import TerminalConnectionError
from .file_parsers import normalize_remote_file_path


class FileOperationError(TerminalConnectionError):
    def __init__(self, message, code="file_operation_failed", status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def entry_stat(sftp, path):
    try:
        return sftp.lstat(path)
    except OSError as error:
        if error.errno == errno.ENOENT:
            return None
        raise


def entry_kind(attrs):
    if stat.S_ISLNK(attrs.st_mode):
        return "link"
    if stat.S_ISDIR(attrs.st_mode):
        return "directory"
    if stat.S_ISREG(attrs.st_mode):
        return "file"
    raise FileOperationError("不支持复制或移动特殊设备文件", "unsupported_file")


def child_paths(sftp, path):
    for name in sftp.listdir(path):
        if not name or name in {".", ".."} or "/" in name:
            raise FileOperationError("远端目录项不合法", "invalid_path")
        yield name, posixpath.join(path, name)


def check_merge(sftp, source, destination):
    source_attrs = sftp.lstat(source)
    destination_attrs = entry_stat(sftp, destination)
    source_kind = entry_kind(source_attrs)
    if destination_attrs is None:
        if source_kind == "directory":
            for name, child in child_paths(sftp, source):
                check_merge(sftp, child, posixpath.join(destination, name))
        return
    destination_kind = entry_kind(destination_attrs)
    if destination_kind != source_kind:
        raise FileOperationError(f"文件与目录类型冲突：{destination}", "file_type_conflict", 409)
    if source_kind == "directory":
        for name, child in child_paths(sftp, source):
            check_merge(sftp, child, posixpath.join(destination, name))


def remove_entry(sftp, path):
    attrs = entry_stat(sftp, path)
    if attrs is None:
        return
    if stat.S_ISDIR(attrs.st_mode) and not stat.S_ISLNK(attrs.st_mode):
        sftp.chmod(path, stat.S_IMODE(attrs.st_mode) | 0o700)
        for _name, child in child_paths(sftp, path):
            remove_entry(sftp, child)
        sftp.rmdir(path)
    else:
        sftp.remove(path)


def copy_entry(sftp, source, destination):
    attrs = sftp.lstat(source)
    kind = entry_kind(attrs)
    existing = entry_stat(sftp, destination)
    if existing is not None and entry_kind(existing) != kind:
        raise FileOperationError(f"文件类型在操作期间发生变化：{destination}", "file_type_conflict", 409)
    if kind == "directory":
        if existing is None:
            sftp.mkdir(destination, 0o700)
        else:
            sftp.chmod(destination, stat.S_IMODE(existing.st_mode) | 0o700)
        for name, child in child_paths(sftp, source):
            copy_entry(sftp, child, posixpath.join(destination, name))
        sftp.chmod(destination, stat.S_IMODE(attrs.st_mode))
    else:
        if existing is not None:
            sftp.remove(destination)
        if kind == "link":
            sftp.symlink(sftp.readlink(source), destination)
        else:
            written = 0
            with sftp.open(source, "rb") as reader, sftp.open(destination, "wx") as writer:
                while True:
                    chunk = reader.read(1024 * 1024)
                    if not chunk:
                        break
                    writer.write(chunk)
                    written += len(chunk)
            if written != attrs.st_size or sftp.stat(destination).st_size != written:
                raise FileOperationError("文件未完整写入", "incomplete_write")
            sftp.chmod(destination, stat.S_IMODE(attrs.st_mode))
    if kind != "link":
        sftp.utime(destination, (attrs.st_atime, attrs.st_mtime))


def absolute_entry_path(sftp, path):
    path = normalize_remote_file_path(path)
    if path == "~" or path.startswith("~/"):
        path = posixpath.join(sftp.normalize("."), path[2:] if path != "~" else "")
    parent, name = posixpath.split(path.rstrip("/"))
    if not name or name in {".", ".."}:
        raise FileOperationError("不能操作根目录、当前目录或上级目录", "invalid_path")
    resolved_parent = sftp.normalize(parent or ".")
    if not resolved_parent.startswith("/"):
        raise FileOperationError("远端目录路径解析失败", "invalid_path")
    return posixpath.join(resolved_parent, name)


def transfer_files(host, paths, target_directory, operation, overwrite=False):
    if operation not in {"copy", "move"}:
        raise FileOperationError("不支持的文件操作", "invalid_operation")
    try:
        with borrow_sftp_client(host) as (_client, sftp, _reused):
            target_directory = normalize_remote_file_path(target_directory)
            if target_directory == "~" or target_directory.startswith("~/"):
                target_directory = posixpath.join(sftp.normalize("."), target_directory[2:] if target_directory != "~" else "")
            directory = sftp.normalize(target_directory)
            if not directory.startswith("/"):
                raise FileOperationError("远端目录路径解析失败", "invalid_path")
            if not stat.S_ISDIR(sftp.stat(directory).st_mode):
                raise FileOperationError("目标必须是目录", "invalid_directory")
            sources = list(dict.fromkeys(absolute_entry_path(sftp, path) for path in paths))
            if not sources:
                raise FileOperationError("请选择要操作的文件", "invalid_path")
            source_attributes = {}
            for source in sources:
                source_attributes[source] = entry_stat(sftp, source)
                if source_attributes[source] is None:
                    raise FileOperationError(f"源文件不存在：{source}", "source_not_found", 404)
            sources = [source for source in sources if not any(source.startswith(parent + "/") and stat.S_ISDIR(source_attributes[parent].st_mode) for parent in sources if parent != source)]
            records = []
            destinations = set()
            for source in sources:
                attrs = entry_stat(sftp, source)
                if attrs is None:
                    raise FileOperationError(f"源文件不存在：{source}", "source_not_found", 404)
                destination = posixpath.join(directory, posixpath.basename(source))
                if destination == source or directory == source or directory.startswith(source + "/"):
                    raise FileOperationError("不能粘贴到原位置或源目录内部", "invalid_destination")
                if destination in destinations or any(other == destination or other.startswith(destination + "/") for other in sources):
                    raise FileOperationError("选择的源文件存在同名或路径重叠", "invalid_destination")
                destinations.add(destination)
                check_merge(sftp, source, destination)
                exists = entry_stat(sftp, destination) is not None
                if exists and not overwrite:
                    raise FileOperationError(f"目标已存在：{destination}。是否覆盖同名文件并合并目录？", "file_exists", 409)
                records.append({"path": source, "targetPath": destination, "exists": exists, "published": False, "backedUp": False, "sourceHeld": False})
            return staged_transfer(sftp, records, directory, operation)
    except FileOperationError:
        raise
    except TerminalConnectionError as error:
        raise FileOperationError(str(error), "invalid_path") from error
    except OSError as error:
        code = "permission_denied" if error.errno in {errno.EACCES, errno.EPERM} else "file_operation_failed"
        raise FileOperationError(f"文件操作失败：{error}", code, 403 if code == "permission_denied" else 400) from error
    except Exception as error:
        raise FileOperationError(f"文件操作失败：{error}") from error


def staged_transfer(sftp, records, directory, operation):
    transaction = posixpath.join(directory, ".captain-operation-" + uuid4().hex)
    sftp.mkdir(transaction, 0o700)
    warnings = []
    try:
        for index, record in enumerate(records):
            stage = posixpath.join(transaction, str(index))
            record["stage"] = stage
            record["backup"] = stage + ".backup"
            record["held"] = posixpath.join(posixpath.dirname(record["path"]), ".captain-move-" + uuid4().hex)
            if record["exists"] and stat.S_ISDIR(sftp.lstat(record["targetPath"]).st_mode):
                copy_entry(sftp, record["targetPath"], stage)
            copy_entry(sftp, record["path"], stage)
        for record in records:
            if operation == "move":
                sftp.rename(record["path"], record["held"])
                record["sourceHeld"] = True
            if record["exists"]:
                sftp.rename(record["targetPath"], record["backup"])
                record["backedUp"] = True
            sftp.rename(record["stage"], record["targetPath"])
            record["published"] = True
    except Exception as error:
        rollback_errors = []
        for record in reversed(records):
            try:
                if record["published"]:
                    sftp.rename(record["targetPath"], record["stage"])
                if record["backedUp"]:
                    sftp.rename(record["backup"], record["targetPath"])
                if record["sourceHeld"]:
                    sftp.rename(record["held"], record["path"])
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise FileOperationError(f"操作失败，恢复未完成；请检查 {transaction} 及源目录中的 .captain-move-* 备份：{'；'.join(rollback_errors)}", "rollback_failed") from error
        try:
            remove_entry(sftp, transaction)
        except Exception as cleanup_error:
            raise FileOperationError(f"操作失败，原文件已恢复；临时目录 {transaction} 清理失败：{cleanup_error}", "cleanup_failed") from error
        raise
    for record in records:
        if record["sourceHeld"]:
            try:
                remove_entry(sftp, record["held"])
            except Exception as error:
                warnings.append(f"移动成功，源备份清理失败：{record['held']}：{error}")
    try:
        remove_entry(sftp, transaction)
    except Exception as error:
        warnings.append(f"操作成功，临时备份清理失败：{transaction}：{error}")
    return {"items": [{"path": record["path"], "targetPath": record["targetPath"]} for record in records], "targetDirectory": directory, "warnings": warnings}
