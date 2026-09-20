from __future__ import annotations

import asyncio
import logging
import stat
import threading
import time
import weakref
from pathlib import Path

import asyncssh
from django.contrib.auth import get_user_model
from django.utils import timezone

from host_management.models import ManagedHost

from ..consumers.protocol import AUDIT_OUTPUT_FLUSH_CHARS, command_buffer_after_input
from ..models import TerminalCommandAudit, TerminalSession
from ..services import (
    DEFAULT_TERMINAL_COLS,
    DEFAULT_TERMINAL_ROWS,
    TerminalConnectionError,
    append_audit_output,
    create_command_audit,
    initialize_session_recording,
    open_live_terminal,
    open_ssh_client,
    save_session_recording,
)
from ..services.recordings import asciicast_event
from .assets import GatewayAssetError, gateway_menu_text, resolve_gateway_host, resolve_gateway_host_selector
from .audit import record_file_audit
from .auth import (
    GatewayAuthError,
    authenticate_platform_user,
    authenticate_platform_user_password,
    parse_gateway_username,
    user_has_totp_enabled,
    validate_platform_user_totp,
)
from .config import gateway_config


logger = logging.getLogger(__name__)
AUTHENTICATED_USERS_BY_CONNECTION: dict[int, object] = {}
SFTP_CHANNELS_BY_CONNECTION: dict[int, weakref.WeakSet] = {}


def ensure_host_key(path: Path | str) -> Path:
    key_path = Path(path)
    if key_path.exists() and key_path.stat().st_size > 0:
        return key_path

    key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = asyncssh.generate_private_key("ssh-ed25519")
    private_key.write_private_key(key_path)
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return key_path


def run_gateway_server() -> None:
    config = gateway_config()
    if not config.enabled:
        logger.warning("SSH gateway is disabled; set SSH_GATEWAY_ENABLED=1 to enable it.")
        return
    host_key = ensure_host_key(config.host_key_path)
    asyncio.run(_run_gateway_server(config.bind_host, config.port, host_key))


async def _run_gateway_server(bind_host: str, port: int, host_key: Path):
    server = await asyncssh.create_server(
        GatewaySSHServer,
        bind_host,
        port,
        server_host_keys=[str(host_key)],
        session_factory=gateway_stream_session,
        sftp_factory=GatewaySFTPServer,
        allow_scp=True,
        line_editor=False,
    )
    logger.info("SSH gateway listening on %s:%s", bind_host, port)
    await server.wait_closed()


class GatewaySSHServer(asyncssh.SSHServer):
    def connection_made(self, conn):
        self.conn = conn
        self.user = None
        self.parsed_username = None
        self.pending_kbdint_user = None
        self.pending_kbdint_username = None
        self.client_ip = client_ip_from_connection(conn)

    def connection_lost(self, exc):
        conn = getattr(self, "conn", None)
        AUTHENTICATED_USERS_BY_CONNECTION.pop(id(conn), None)
        SFTP_CHANNELS_BY_CONNECTION.pop(id(conn), None)

    def begin_auth(self, username: str) -> bool:
        self.parsed_username = parse_gateway_username(username)
        return True

    def password_auth_supported(self) -> bool:
        return True

    def kbdint_auth_supported(self) -> bool:
        return True

    async def validate_password(self, username: str, password: str) -> bool:
        try:
            self.user = await asyncio.to_thread(authenticate_platform_user, username, password)
            self.parsed_username = parse_gateway_username(username)
            return True
        except GatewayAuthError:
            return False

    def get_kbdint_challenge(self, username: str, lang: str, submethods: str):
        return (
            "SSH Gateway",
            "Enter your platform password.",
            "",
            [("Password: ", False)],
        )

    async def validate_kbdint_response(self, username: str, responses) -> bool:
        pending_user = getattr(self, "pending_kbdint_user", None)
        if pending_user is not None:
            totp_code = responses[0] if responses else ""
            try:
                self.user = await asyncio.to_thread(validate_platform_user_totp, pending_user, totp_code)
                self.parsed_username = getattr(self, "pending_kbdint_username", None)
                self.pending_kbdint_user = None
                self.pending_kbdint_username = None
                return True
            except GatewayAuthError:
                self.pending_kbdint_user = None
                self.pending_kbdint_username = None
                return False

        password = responses[0] if responses else ""
        try:
            user = await asyncio.to_thread(authenticate_platform_user_password, username, password)
            parsed_username = parse_gateway_username(username)
            if await asyncio.to_thread(user_has_totp_enabled, user):
                self.pending_kbdint_user = user
                self.pending_kbdint_username = parsed_username
                return (
                    "SSH Gateway",
                    "Enter your 6-digit verification code.",
                    "",
                    [("Verification code: ", False)],
                )
            self.user = user
            self.parsed_username = parsed_username
            return True
        except GatewayAuthError:
            return False

    def auth_completed(self):
        if self.user is not None:
            AUTHENTICATED_USERS_BY_CONNECTION[id(self.conn)] = self.user

    def session_requested(self):
        return GatewayShellSession(
            user=self.user,
            parsed_username=self.parsed_username,
            client_ip=self.client_ip,
        )


class GatewayShellSession(asyncssh.SSHServerSession):
    def __init__(self, *, user, parsed_username, client_ip: str | None = None):
        self.user = user
        self.parsed_username = parsed_username
        self.client_ip = client_ip
        self.channel = None
        self.connection = None
        self.session: TerminalSession | None = None
        self.loop = None
        self.loop_thread = None
        self.stop_reader = threading.Event()
        self.reader_thread: threading.Thread | None = None
        self.cols = DEFAULT_TERMINAL_COLS
        self.rows = DEFAULT_TERMINAL_ROWS
        self.menu_buffer = ""
        self.exec_command = None
        self.command_buffer = ""
        self.pending_command_audit: TerminalCommandAudit | None = None
        self.pending_command_output_chunks: list[str] = []
        self.pending_command_output_size = 0
        self.recording_events: list[str] = []
        self.recording_last_event_at = None
        self.recording_lock = threading.Lock()
        self.transcript_chunks: list[str] = []

    def connection_made(self, chan):
        self.channel = chan
        try:
            self.loop = asyncio.get_running_loop()
            self.loop_thread = threading.current_thread()
        except RuntimeError:
            self.loop = None
            self.loop_thread = None

    def pty_requested(self, term_type, term_size, term_modes):
        width, height, _pixwidth, _pixheight = term_size
        self.cols = max(1, min(int(width or DEFAULT_TERMINAL_COLS), 300))
        self.rows = max(1, min(int(height or DEFAULT_TERMINAL_ROWS), 120))
        return True

    def shell_requested(self):
        self.exec_command = None
        return True

    def exec_requested(self, command: str):
        self.exec_command = command
        return True

    def session_started(self):
        if self.exec_command is not None:
            threading.Thread(target=self._run_exec_command, args=(self.exec_command,), daemon=True).start()
        else:
            self._start_session_thread()

    def _start_session_thread(self):
        threading.Thread(target=self._start_session, name="ssh-gateway-session-start", daemon=True).start()

    def _start_session(self):
        if self.parsed_username and self.parsed_username.direct_mode:
            self._connect_host_id(self.parsed_username.host_id)
        else:
            self._write(gateway_menu_text(self.user))

    def terminal_size_changed(self, width, height, pixwidth, pixheight):
        self.cols = max(1, min(int(width or self.cols), 300))
        self.rows = max(1, min(int(height or self.rows), 120))
        if self.connection is not None:
            try:
                self.connection.resize(self.cols, self.rows)
                self._record_resize(self.cols, self.rows)
            except Exception:
                pass

    def data_received(self, data, datatype):
        if self.connection is None:
            self._handle_menu_input(str(data))
            return
        try:
            self._record_input(str(data))
            self.connection.send_data(str(data))
        except Exception as error:
            self._write(f"\r\nSSH gateway input failed: {error}\r\n")
            self._close_channel(1)

    def eof_received(self):
        return False

    def connection_lost(self, exc):
        self.stop_reader.set()
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
        self._close_session(exc)

    def _handle_menu_input(self, data: str):
        self.menu_buffer += data.replace("\r\n", "\n").replace("\r", "\n")
        if "\n" not in self.menu_buffer:
            return
        line, _sep, rest = self.menu_buffer.partition("\n")
        self.menu_buffer = rest
        value = line.strip()
        if not value:
            self._write("asset> ")
            return
        if value.lower() in {"q", "quit", "exit"}:
            self._write("\r\nbye\r\n")
            self._close_channel(0)
            return
        threading.Thread(target=self._connect_host_selector, args=(value,), name=f"ssh-gateway-connect-{value}", daemon=True).start()

    def _connect_host_selector(self, selector: str):
        try:
            host = resolve_gateway_host_selector(self.user, selector)
            self._connect_host(host)
        except (GatewayAssetError, TerminalConnectionError, ValueError) as error:
            self._write(f"\r\n连接失败：{error}\r\n")
            self._write(gateway_menu_text(self.user))

    def _connect_host_id(self, host_id: int | None):
        try:
            host = resolve_gateway_host(self.user, int(host_id or 0))
            self._connect_host(host)
        except (GatewayAssetError, TerminalConnectionError, ValueError) as error:
            self._write(f"\r\n连接失败：{error}\r\n")
            self._close_channel(1)

    def _connect_host(self, host: ManagedHost):
        self._write(f"\r\nConnecting to {host.name} ({host.public_ip or host.private_ip})...\r\n")
        self.connection = open_live_terminal(host, cols=self.cols, rows=self.rows)
        self.session = TerminalSession.objects.create(
            host=host,
            user=self.user if getattr(self.user, "is_authenticated", False) else None,
            username=getattr(self.user, "username", "") or "anonymous",
            entrypoint="ssh_gateway",
            client_ip=self.client_ip,
            remote_username=host.login_user,
            direct_mode=bool(self.parsed_username and self.parsed_username.direct_mode),
            transcript=f"connect {host.name}\n",
        )
        initialize_session_recording(self.session, self.cols, self.rows)
        self.recording_last_event_at = self.session.recording_last_event_at
        greeting = self.connection.read_available_raw(timeout=2.0, idle_timeout=0.25)
        if greeting:
            self._record_output(greeting)
            self._write(greeting)
        self.reader_thread = threading.Thread(target=self._read_target_output, name=f"ssh-gateway-{self.session.session_id}", daemon=True)
        self.reader_thread.start()

    def _read_target_output(self):
        while not self.stop_reader.is_set() and self.connection is not None:
            try:
                output = self.connection.read_raw()
                if output:
                    self._record_output(output)
                    self._write(output)
                    continue
                if self.connection.channel.closed or self.connection.channel.exit_status_ready():
                    self._handle_target_closed("\r\nSSH 会话已关闭。\r\n", exit_code=0)
                    return
            except Exception as error:
                if not self.stop_reader.is_set():
                    self._handle_target_closed(f"\r\n读取 SSH 输出失败：{error}\r\n", exit_code=1, exc=error)
                return
            time.sleep(0.03)

    def _handle_target_closed(self, message: str, *, exit_code: int = 0, exc=None):
        self._write(message)
        if self.channel is not None:
            close_sftp_channels_for_connection(self.channel.get_connection())
        connection = self.connection
        self.connection = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        self._close_session(exc)
        if self.parsed_username and self.parsed_username.direct_mode:
            self._close_channel(exit_code)
        else:
            self._write(gateway_menu_text(self.user))

    def _run_exec_command(self, command: str):
        if not self.parsed_username or not self.parsed_username.direct_mode:
            self._write("请使用 用户名#主机ID 直连模式执行远程命令。\n")
            self._close_channel(1)
            return
        try:
            host = resolve_gateway_host(self.user, self.parsed_username.host_id)
            session = TerminalSession.objects.create(
                host=host,
                user=self.user if getattr(self.user, "is_authenticated", False) else None,
                username=getattr(self.user, "username", "") or "anonymous",
                entrypoint="ssh_gateway",
                client_ip=self.client_ip,
                remote_username=host.login_user,
                direct_mode=True,
                transcript=f"exec {host.name}: {command}\n",
            )
            client = open_ssh_client(host)
            try:
                _stdin, stdout, stderr = client.exec_command(command, timeout=60)
                output = stdout.read().decode("utf-8", errors="replace")
                error_output = stderr.read().decode("utf-8", errors="replace")
                exit_code = stdout.channel.recv_exit_status()
            finally:
                client.close()
            if output:
                self._write(output)
            if error_output:
                self._write(error_output)
            create_command_audit(session, command, user=self.user, output=output + error_output)
            session.status = "closed"
            session.ended_at = timezone.now()
            session.last_command_at = timezone.now()
            session.transcript += output + error_output
            session.save(update_fields=["status", "ended_at", "last_command_at", "transcript"])
            self._close_channel(exit_code)
        except Exception as error:
            self._write(f"命令执行失败：{error}\n")
            self._close_channel(1)

    def _write(self, data: str):
        if not self.channel or not data:
            return
        if self.loop and self.loop_thread and threading.current_thread() is not self.loop_thread:
            self.loop.call_soon_threadsafe(self._channel_write, data)
        else:
            self._channel_write(data)

    def _channel_write(self, data: str):
        try:
            self.channel.write(data)
        except (BrokenPipeError, OSError):
            pass

    def _close_channel(self, exit_code: int):
        if not self.channel:
            return
        def close():
            try:
                self.channel.exit(exit_code)
            except Exception:
                try:
                    self.channel.close()
                except Exception:
                    pass

        if self.loop and self.loop_thread and threading.current_thread() is not self.loop_thread:
            self.loop.call_soon_threadsafe(close)
        else:
            close()

    def _record_input(self, data: str):
        if not self.session or not data:
            return
        self._append_recording_event("i", data)
        self.command_buffer, commands = command_buffer_after_input(self.command_buffer, data)
        for command in commands:
            self._flush_pending_audit_output()
            self.pending_command_audit = create_command_audit(self.session, command, user=self.user)

    def _record_output(self, output: str):
        if not self.session or not output:
            return
        self.transcript_chunks.append(output)
        self._append_recording_event("o", output)
        if self.pending_command_audit:
            self.pending_command_output_chunks.append(output)
            self.pending_command_output_size += len(output)
            if self.pending_command_output_size >= AUDIT_OUTPUT_FLUSH_CHARS:
                self._flush_pending_audit_output()

    def _record_resize(self, cols: int, rows: int):
        if not self.session:
            return
        self.session.recording_cols = cols
        self.session.recording_rows = rows
        self._append_recording_event("r", f"{cols}x{rows}")

    def _append_recording_event(self, event_type: str, data):
        if not self.session or not self.session.recording_started_at:
            return
        with self.recording_lock:
            previous_event_at = self.recording_last_event_at or self.session.recording_last_event_at or self.session.recording_started_at
            event, event_at = asciicast_event(previous_event_at, event_type, data)
            self.recording_events.append(event + "\n")
            self.recording_last_event_at = event_at
            self.session.recording_last_event_at = event_at

    def _flush_pending_audit_output(self):
        if not self.pending_command_audit or not self.pending_command_output_chunks:
            return
        append_audit_output(self.pending_command_audit, "".join(self.pending_command_output_chunks))
        self.pending_command_output_chunks = []
        self.pending_command_output_size = 0

    def _close_session(self, exc):
        if self.session is None:
            return
        self._flush_pending_audit_output()
        self._append_recording_event("x", 0 if exc is None else 1)
        self.session.status = "closed"
        self.session.ended_at = timezone.now()
        self.session.last_command_at = timezone.now()
        transcript = "".join(self.transcript_chunks)
        update_fields = ["status", "ended_at", "last_command_at", "recording_cols", "recording_rows", "recording_last_event_at"]
        if transcript:
            self.session.transcript += transcript
            update_fields.append("transcript")
        with self.recording_lock:
            events = list(self.recording_events)
            self.recording_events.clear()
        save_session_recording(self.session, events, update_fields=update_fields)
        self.session = None
        self.command_buffer = ""
        self.pending_command_audit = None
        self.pending_command_output_chunks = []
        self.pending_command_output_size = 0
        self.recording_last_event_at = None
        self.transcript_chunks = []


async def gateway_stream_session(stdin, stdout, stderr):
    channel = stdout.channel
    error = None
    session = None
    try:
        user = await asyncio.to_thread(authenticated_user_from_channel, channel)
        parsed_username = parse_gateway_username(channel.get_extra_info("username", ""))
        session = GatewayShellSession(
            user=user,
            parsed_username=parsed_username,
            client_ip=client_ip_from_connection(channel.get_connection()),
        )
        session.connection_made(channel)
        session.pty_requested(
            channel.get_terminal_type() or "",
            channel.get_terminal_size(),
            channel.get_terminal_modes(),
        )
        command = channel.get_command()
        if command:
            session.exec_requested(command)
        else:
            session.shell_requested()
        session.session_started()

        while not stdin.at_eof():
            try:
                data = await stdin.read(4096)
            except asyncssh.TerminalSizeChanged as resize:
                session.terminal_size_changed(resize.width, resize.height, resize.pixwidth, resize.pixheight)
                continue
            except (asyncssh.BreakReceived, asyncssh.SignalReceived):
                continue
            except (asyncssh.ConnectionLost, ConnectionResetError):
                break
            if not data:
                break
            if isinstance(data, bytes):
                data = data.decode("utf-8", "replace")
            await asyncio.to_thread(session.data_received, data, None)
    except Exception as exc:
        error = exc
        logger.exception("SSH gateway stream session failed")
        try:
            stderr.write(f"SSH gateway session failed: {exc}\r\n")
        except Exception:
            pass
    finally:
        if session is not None:
            await asyncio.to_thread(session.connection_lost, error)


def register_sftp_channel(channel):
    conn = channel.get_connection()
    SFTP_CHANNELS_BY_CONNECTION.setdefault(id(conn), weakref.WeakSet()).add(channel)


def close_sftp_channels_for_connection(conn):
    channels = list(SFTP_CHANNELS_BY_CONNECTION.pop(id(conn), ()))
    for channel in channels:
        try:
            loop = channel.get_loop()
            if loop and loop.is_running():
                loop.call_soon_threadsafe(channel.close)
            else:
                channel.close()
        except Exception:
            pass


class GatewaySFTPServer:
    def __new__(cls, chan):
        class _GatewaySFTPServer(asyncssh.SFTPServer):
            def __init__(self, channel):
                super().__init__(channel)
                register_sftp_channel(channel)
                self.user = authenticated_user_from_channel(channel)
                self.parsed_username = parse_gateway_username(channel.get_extra_info("username", ""))

            async def realpath(self, path):
                return self._encode(self._decode(path) or "/")

            async def stat(self, path):
                return await asyncio.to_thread(self._stat_sync, path)

            def _stat_sync(self, path):
                remote = self._resolve_remote(path)
                if remote is None:
                    return directory_attrs()
                host, remote_path = remote
                client = open_ssh_client(host)
                try:
                    sftp = client.open_sftp()
                    try:
                        attrs = sftp.stat(remote_path)
                        record_file_audit(operation="stat", host=host, user=self.user, path=remote_path, protocol="sftp")
                        return attrs_from_paramiko(attrs)
                    finally:
                        sftp.close()
                finally:
                    client.close()

            async def lstat(self, path):
                return await self.stat(path)

            async def scandir(self, path):
                for item in await asyncio.to_thread(self._scandir_sync, path):
                    yield item

            def _scandir_sync(self, path):
                decoded = self._decode(path)
                remote = self._resolve_remote(path)
                if remote is None:
                    return list(self._virtual_names(decoded))

                host, remote_path = remote
                client = open_ssh_client(host)
                try:
                    sftp = client.open_sftp()
                    try:
                        items = [name_from_paramiko(item) for item in sftp.listdir_attr(remote_path)]
                        record_file_audit(operation="list", host=host, user=self.user, path=remote_path, protocol="sftp")
                        return items
                    finally:
                        sftp.close()
                finally:
                    client.close()

            async def open(self, path, pflags, attrs):
                return await asyncio.to_thread(self._open_sync, path, pflags)

            def _open_sync(self, path, pflags):
                host, remote_path = self._require_remote(path)
                return RemoteSFTPFile(host, self.user, remote_path, pflags)

            async def read(self, file_obj, offset, size):
                return await asyncio.to_thread(file_obj.read, offset, size)

            async def write(self, file_obj, offset, data):
                return await asyncio.to_thread(file_obj.write, offset, data)

            async def close(self, file_obj):
                await asyncio.to_thread(file_obj.close)

            async def fstat(self, file_obj):
                return await asyncio.to_thread(file_obj.stat)

            async def mkdir(self, path, attrs):
                await asyncio.to_thread(self._mkdir_sync, path)

            def _mkdir_sync(self, path):
                host, remote_path = self._require_remote(path)
                client = open_ssh_client(host)
                try:
                    sftp = client.open_sftp()
                    try:
                        sftp.mkdir(remote_path)
                        record_file_audit(operation="mkdir", host=host, user=self.user, path=remote_path, protocol="sftp")
                    finally:
                        sftp.close()
                finally:
                    client.close()

            async def remove(self, path):
                await asyncio.to_thread(self._remove_sync, path)

            def _remove_sync(self, path):
                host, remote_path = self._require_remote(path)
                client = open_ssh_client(host)
                try:
                    sftp = client.open_sftp()
                    try:
                        sftp.remove(remote_path)
                        record_file_audit(operation="remove", host=host, user=self.user, path=remote_path, protocol="sftp")
                    finally:
                        sftp.close()
                finally:
                    client.close()

            async def rmdir(self, path):
                await asyncio.to_thread(self._rmdir_sync, path)

            def _rmdir_sync(self, path):
                host, remote_path = self._require_remote(path)
                client = open_ssh_client(host)
                try:
                    sftp = client.open_sftp()
                    try:
                        sftp.rmdir(remote_path)
                        record_file_audit(operation="remove", host=host, user=self.user, path=remote_path, protocol="sftp")
                    finally:
                        sftp.close()
                finally:
                    client.close()

            async def rename(self, oldpath, newpath):
                await asyncio.to_thread(self._rename_sync, oldpath, newpath)

            def _rename_sync(self, oldpath, newpath):
                host, old_remote = self._require_remote(oldpath)
                next_host, new_remote = self._require_remote(newpath)
                if host.id != next_host.id:
                    raise asyncssh.SFTPPermissionDenied("跨主机重命名不受支持")
                client = open_ssh_client(host)
                try:
                    sftp = client.open_sftp()
                    try:
                        sftp.rename(old_remote, new_remote)
                        record_file_audit(
                            operation="rename",
                            host=host,
                            user=self.user,
                            path=old_remote,
                            target_path=new_remote,
                            protocol="sftp",
                        )
                    finally:
                        sftp.close()
                finally:
                    client.close()

            def _virtual_names(self, path: str):
                import asyncssh

                normalized = normalize_sftp_path(path)
                if normalized in {"/", ""}:
                    yield asyncssh.SFTPName(b"hosts", b"", attrs=directory_attrs())
                    return
                if normalized == "/hosts":
                    for host in ManagedHost.objects.select_related("group").order_by("name", "id"):
                        try:
                            resolved = resolve_gateway_host(self.user, host.id)
                        except GatewayAssetError:
                            continue
                        yield asyncssh.SFTPName(virtual_host_name(resolved).encode("utf-8"), b"", attrs=directory_attrs())

            def _resolve_remote(self, path):
                normalized = normalize_sftp_path(self._decode(path))
                if self.parsed_username.direct_mode:
                    return resolve_gateway_host(self.user, self.parsed_username.host_id), normalized or "/"
                parts = [item for item in normalized.split("/") if item]
                if len(parts) < 2 or parts[0] != "hosts":
                    return None
                host_token = parts[1].split("-", 1)[0]
                host = resolve_gateway_host(self.user, int(host_token))
                remote_path = "/" + "/".join(parts[2:]) if len(parts) > 2 else "/"
                return host, remote_path

            def _require_remote(self, path):
                import asyncssh

                remote = self._resolve_remote(path)
                if remote is None:
                    raise asyncssh.SFTPPermissionDenied("请选择具体主机目录")
                return remote

            def _decode(self, path) -> str:
                return path.decode("utf-8", errors="replace") if isinstance(path, bytes) else str(path or "")

            def _encode(self, path: str) -> bytes:
                return str(path or "/").encode("utf-8")

        return _GatewaySFTPServer(chan)


class RemoteSFTPFile:
    def __init__(self, host: ManagedHost, user, path: str, pflags: int):
        import asyncssh

        self.host = host
        self.user = user
        self.path = path
        self.client = open_ssh_client(host)
        self.sftp = self.client.open_sftp()
        self.mode = sftp_mode_from_flags(asyncssh, pflags)
        self.file_obj = self.sftp.open(path, self.mode)
        self.lock = threading.Lock()
        self.read_bytes = 0
        self.write_bytes = 0
        self.read_attempted = False
        self.write_attempted = False
        self.read_error = ""
        self.write_error = ""
        self.audit_recorded = False

    def read(self, offset: int, size: int) -> bytes:
        with self.lock:
            self.read_attempted = True
            try:
                self.file_obj.seek(offset)
                data = self.file_obj.read(size)
                self.read_bytes += len(data or b"")
                return data
            except Exception as error:
                self.read_error = str(error)
                raise

    def write(self, offset: int, data: bytes) -> int:
        with self.lock:
            self.write_attempted = True
            try:
                self.file_obj.seek(offset)
                self.file_obj.write(data)
                written = len(data or b"")
                self.write_bytes += written
                return written
            except Exception as error:
                self.write_error = str(error)
                raise

    def stat(self):
        with self.lock:
            return attrs_from_paramiko(self.file_obj.stat())

    def close(self):
        with self.lock:
            close_error = None
            for resource in (self.file_obj, self.sftp, self.client):
                try:
                    resource.close()
                except Exception as error:
                    if close_error is None:
                        close_error = error
            self._record_transfer_audits(close_error)
            if close_error is not None:
                raise close_error

    def _record_transfer_audits(self, close_error=None):
        if self.audit_recorded:
            return
        self.audit_recorded = True
        close_message = str(close_error or "")
        if self.read_attempted:
            error_message = self.read_error or close_message
            record_file_audit(
                operation="read",
                host=self.host,
                user=self.user,
                path=self.path,
                size=self.read_bytes,
                protocol="sftp",
                status="failed" if error_message else "success",
                error_message=error_message,
            )
        if self.write_attempted:
            error_message = self.write_error or close_message
            record_file_audit(
                operation="write",
                host=self.host,
                user=self.user,
                path=self.path,
                size=self.write_bytes,
                protocol="sftp",
                status="failed" if error_message else "success",
                error_message=error_message,
            )


def sftp_mode_from_flags(asyncssh, pflags: int) -> str:
    if pflags & asyncssh.FXF_WRITE:
        if pflags & asyncssh.FXF_APPEND:
            return "ab"
        if pflags & (asyncssh.FXF_CREAT | asyncssh.FXF_TRUNC):
            return "wb"
        return "r+b"
    return "rb"


def authenticated_user_from_channel(channel):
    conn = channel.get_connection()
    user = AUTHENTICATED_USERS_BY_CONNECTION.get(id(conn))
    if user is not None:
        return user
    username = channel.get_extra_info("username", "")
    parsed = parse_gateway_username(username)
    return get_user_model().objects.get(username=parsed.username)


def attrs_from_paramiko(attrs):
    import asyncssh

    return asyncssh.SFTPAttrs(
        size=int(getattr(attrs, "st_size", 0) or 0),
        uid=int(getattr(attrs, "st_uid", 0) or 0),
        gid=int(getattr(attrs, "st_gid", 0) or 0),
        permissions=int(getattr(attrs, "st_mode", 0) or 0),
        atime=int(getattr(attrs, "st_atime", 0) or 0),
        mtime=int(getattr(attrs, "st_mtime", 0) or 0),
    )


def name_from_paramiko(attrs):
    import asyncssh

    filename = str(attrs.filename).encode("utf-8")
    return asyncssh.SFTPName(filename, b"", attrs=attrs_from_paramiko(attrs))


def directory_attrs():
    import asyncssh

    return asyncssh.SFTPAttrs(permissions=stat.S_IFDIR | 0o755)


def virtual_host_name(host: ManagedHost) -> str:
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in host.name)
    return f"{host.id}-{safe_name or 'host'}"


def normalize_sftp_path(path: str) -> str:
    value = str(path or "/").replace("\\", "/").strip()
    if not value.startswith("/"):
        value = "/" + value
    parts = []
    for part in value.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def client_ip_from_connection(conn) -> str | None:
    peer = conn.get_extra_info("peername")
    if isinstance(peer, tuple) and peer:
        return str(peer[0])
    return None
