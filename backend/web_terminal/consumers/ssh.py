from __future__ import annotations

import json
import logging
import threading
import time
from urllib.parse import parse_qs

from channels.generic.websocket import WebsocketConsumer
from django.utils import timezone

from accounts.permissions import has_feature_permission
from accounts.session_expiry import is_authenticated_session_expired
from host_management.models import ManagedHost
from system_management.services import get_terminal_settings
from system_management.settings_defaults import DEFAULT_TERMINAL_SETTINGS

from ..models import TerminalCommandAudit, TerminalSession
from ..services.containers import container_terminal_command
from ..services import (
    DEFAULT_TERMINAL_COLS,
    DEFAULT_TERMINAL_ROWS,
    LiveTerminalConnection,
    TerminalConnectionError,
    append_audit_output,
    asciicast_event,
    create_command_audit,
    initialize_session_recording,
    is_session_audit_enabled,
    open_live_terminal,
    save_session_recording,
)
from .protocol import (
    AUDIT_OUTPUT_FLUSH_CHARS,
    CWD_HOOK_ECHO_OFF,
    CWD_HOOK_ECHO_ON,
    CWD_HOOK_INSTALL_SCRIPT,
    alternate_screen_state_after_output,
    command_buffer_after_input,
    filter_changed_cwd_paths,
    is_interactive_terminal_command,
    output_has_alternate_screen_sequence,
    should_continue_coalescing_output,
    strip_cwd_hook_install_echo,
    strip_cwd_markers_with_pending,
)


logger = logging.getLogger(__name__)


class TerminalConsumer(WebsocketConsumer):
    connection: LiveTerminalConnection | None = None
    session: TerminalSession | None = None
    reader_thread: threading.Thread | None = None
    stop_reader: threading.Event
    transcript_chunks: list[str]
    pending_output: str
    current_cwd: str
    suppress_internal_echo_until: float
    command_buffer: str
    pending_command_audit: TerminalCommandAudit | None
    pending_command_output_chunks: list[str]
    pending_command_output_size: int
    recording_events: list[str]
    recording_last_event_at: object | None
    recording_lock: threading.Lock
    terminal_settings: dict
    last_activity_monotonic: float
    alternate_screen_active: bool

    def connect(self):
        self.terminal_settings = get_terminal_settings()
        self.last_activity_monotonic = time.monotonic()
        self.stop_reader = threading.Event()
        self.transcript_chunks = []
        self.pending_output = ""
        self.current_cwd = ""
        self.suppress_internal_echo_until = 0.0
        self.command_buffer = ""
        self.pending_command_audit = None
        self.pending_command_output_chunks = []
        self.pending_command_output_size = 0
        self.recording_events = []
        self.recording_last_event_at = None
        self.recording_lock = threading.Lock()
        self.alternate_screen_active = False
        self.accept()

        if not self._is_authenticated():
            self._close_for_unauthenticated()
            return
        if not self._has_terminal_permission():
            self._close_for_forbidden()
            return

        host_id = self.scope["url_route"]["kwargs"]["host_id"]
        try:
            host = ManagedHost.objects.get(id=host_id)
            container = parse_qs(self.scope.get("query_string", b"").decode("utf-8", errors="replace")).get("container", [""])[0]
            container_command = container_terminal_command(host, container) if container else ""
            self.connection = open_live_terminal(
                host,
                cols=int(self.terminal_settings["defaultCols"]),
                rows=int(self.terminal_settings["defaultRows"]),
                terminal_settings=self.terminal_settings,
            )
        except ManagedHost.DoesNotExist:
            self._send_error("请选择要连接的主机")
            self.close()
            return
        except TerminalConnectionError as error:
            self._send_error(str(error))
            self.close()
            return
        except ValueError as error:
            self._send_error(str(error))
            self.close()
            return

        self._create_audit_session(host)
        self._send_initial_output()
        self._install_cwd_hook()
        if container_command:
            self._record_input(container_command)
            self.connection.send_data(container_command)
        ready_payload = {
            "type": "ready",
            "terminalSettings": {
                "webSocketHeartbeatSeconds": int(self.terminal_settings["webSocketHeartbeatSeconds"]),
                "defaultCols": int(self.terminal_settings["defaultCols"]),
                "defaultRows": int(self.terminal_settings["defaultRows"]),
                "defaultFontSize": int(self.terminal_settings["defaultFontSize"]),
                "scrollbackLines": int(self.terminal_settings["scrollbackLines"]),
            },
        }
        if self.session is not None:
            ready_payload["sessionId"] = str(self.session.session_id)
        self.send(text_data=json.dumps(ready_payload, ensure_ascii=False))
        thread_name = f"terminal-{self.session.session_id}" if self.session is not None else f"terminal-host-{host.id}"
        self.reader_thread = threading.Thread(target=self._read_ssh_output, name=thread_name, daemon=True)
        self.reader_thread.start()

    def receive(self, text_data=None, bytes_data=None):
        if not text_data or self.connection is None:
            return
        if not self._is_authenticated():
            self._close_for_unauthenticated()
            return

        try:
            message = json.loads(text_data)
        except json.JSONDecodeError:
            self._send_error("终端消息格式不正确")
            return

        message_type = message.get("type")
        try:
            if message_type == "ping":
                self.send(text_data=json.dumps({"type": "pong"}, ensure_ascii=False))
            elif message_type == "input":
                self.last_activity_monotonic = time.monotonic()
                data = str(message.get("data", ""))
                self._record_input(data)
                self.connection.send_data(data)
            elif message_type == "resize":
                self.last_activity_monotonic = time.monotonic()
                cols = int(message.get("cols", DEFAULT_TERMINAL_COLS))
                rows = int(message.get("rows", DEFAULT_TERMINAL_ROWS))
                self._record_resize(cols, rows)
                self.connection.resize(cols, rows)
            else:
                logger.debug("Ignoring unsupported terminal message type: %r", message_type)
        except (TypeError, ValueError):
            self._send_error("终端窗口尺寸不正确")
        except Exception as error:
            self._send_error(f"SSH 连接失败：{error}")
            self.close()

    def disconnect(self, close_code):
        self.stop_reader.set()
        self._record_exit(0 if close_code in (None, 1000) else 1)
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass

        if self.reader_thread and self.reader_thread.is_alive() and threading.current_thread() is not self.reader_thread:
            self.reader_thread.join(timeout=1.0)

        self._close_session()

    def terminal_output(self, event):
        self.send(text_data=json.dumps({"type": "output", "data": event["data"]}, ensure_ascii=False))

    def terminal_cwd(self, event):
        self.send(text_data=json.dumps({"type": "cwd", "path": event["path"]}, ensure_ascii=False))

    def terminal_pong(self, event):
        self.send(text_data=json.dumps({"type": "pong"}, ensure_ascii=False))

    def terminal_closed(self, event):
        self.send(text_data=json.dumps({"type": "closed", "reason": event["reason"]}, ensure_ascii=False))
        self.close()

    def terminal_error(self, event):
        self._send_error(event["message"])

    def _read_ssh_output(self):
        assert self.connection is not None

        next_auth_check = 0.0
        next_websocket_heartbeat = 0.0
        while not self.stop_reader.is_set():
            try:
                now = time.monotonic()
                next_websocket_heartbeat = self._send_websocket_heartbeat_if_due(
                    now=now,
                    next_due=next_websocket_heartbeat,
                )
                if now >= next_auth_check:
                    next_auth_check = now + 1.0
                    if not self._is_authenticated():
                        self._send_to_consumer({"type": "terminal.error", "message": "请先登录"})
                        self._send_to_consumer({"type": "terminal.closed", "reason": "请先登录"})
                        return
                    if self._close_if_idle(now=now):
                        return

                output = self.connection.read_raw()
                if output:
                    output = self._coalesce_available_output(output)
                    if time.monotonic() < self.suppress_internal_echo_until:
                        output = strip_cwd_hook_install_echo(output)
                    cleaned_output, cwd_paths, self.pending_output = strip_cwd_markers_with_pending(self.pending_output + output)
                    cwd_paths, self.current_cwd = filter_changed_cwd_paths(cwd_paths, self.current_cwd)
                    if cleaned_output:
                        self.transcript_chunks.append(cleaned_output)
                        self._record_output(cleaned_output)
                        self._send_to_consumer({"type": "terminal.output", "data": cleaned_output})
                    for path in cwd_paths:
                        self._send_to_consumer({"type": "terminal.cwd", "path": path})
                    continue

                if self.connection.channel.closed or self.connection.channel.exit_status_ready():
                    if self.pending_output:
                        self.transcript_chunks.append(self.pending_output)
                        self._record_output(self.pending_output)
                        self._send_to_consumer({"type": "terminal.output", "data": self.pending_output})
                        self.pending_output = ""
                    self._send_to_consumer({"type": "terminal.closed", "reason": "SSH 会话已关闭"})
                    return
            except Exception as error:
                if not self.stop_reader.is_set():
                    logger.exception("Terminal reader thread failed; closing the SSH session.")
                    self._send_to_consumer({"type": "terminal.error", "message": f"读取 SSH 输出失败：{error}"})
                    self._send_to_consumer({"type": "terminal.closed", "reason": "SSH 会话已关闭"})
                return

            time.sleep(float(self._terminal_setting("readerPollIntervalMs")) / 1000)

    def _coalesce_available_output(self, output: str) -> str:
        if self.connection is None:
            return output
        chunks = [output]
        size = len(output)
        started = time.monotonic()
        while should_continue_coalescing_output(size, (time.monotonic() - started) * 1000):
            extra = self.connection.read_raw()
            if not extra:
                break
            chunks.append(extra)
            size += len(extra)
        return "".join(chunks)

    def _close_if_idle(self, *, now: float | None = None) -> bool:
        idle_minutes = int(self._terminal_setting("idleDisconnectMinutes"))
        if idle_minutes <= 0:
            return False
        current = time.monotonic() if now is None else now
        if current - getattr(self, "last_activity_monotonic", current) < idle_minutes * 60:
            return False
        self._send_to_consumer({"type": "terminal.closed", "reason": "终端闲置超时，连接已关闭"})
        return True

    def _send_websocket_heartbeat_if_due(self, *, now: float, next_due: float) -> float:
        heartbeat_seconds = int(self._terminal_setting("webSocketHeartbeatSeconds"))
        if heartbeat_seconds <= 0:
            return next_due
        if next_due <= 0:
            return now + heartbeat_seconds
        if now < next_due:
            return next_due
        return now + heartbeat_seconds

    def _terminal_setting(self, key: str):
        settings_value = getattr(self, "terminal_settings", None)
        if isinstance(settings_value, dict) and key in settings_value:
            return settings_value[key]
        return DEFAULT_TERMINAL_SETTINGS[key]

    def _send_to_consumer(self, event: dict):
        # 直接派发给本实例的处理方法,不绕 channel layer。self.send 底层的 base_send 是在
        # daphne 事件循环上构造的 async_to_sync,跨线程调用会安全地投递回该循环;而在读取线程里
        # 现场构造 async_to_sync 会为每条输出新建事件循环和通道后端连接,vim 整屏重绘时直接压死。
        handler = getattr(self, event["type"].replace(".", "_"), None)
        if handler is None:
            logger.debug("Ignoring terminal event without a handler: %r", event["type"])
            return
        try:
            handler(event)
        except Exception:
            logger.exception("Terminal websocket send failed for %r; stopping the reader thread.", event["type"])
            self.stop_reader.set()

    def _send_error(self, message: str):
        self.send(text_data=json.dumps({"type": "error", "message": message}, ensure_ascii=False))

    def _close_for_unauthenticated(self):
        self._send_error("请先登录")
        self.close()

    def _close_for_forbidden(self):
        self._send_error("没有 Web 终端权限")
        self.close(code=4403)

    def _create_audit_session(self, host: ManagedHost):
        if not is_session_audit_enabled(self.scope.get("user")):
            self.session = None
            self.recording_last_event_at = None
            return
        try:
            self.session = TerminalSession.objects.create(host=host, transcript=f"connect {host.name}\n")
            initialize_session_recording(self.session, DEFAULT_TERMINAL_COLS, DEFAULT_TERMINAL_ROWS)
            self.recording_last_event_at = self.session.recording_last_event_at
        except Exception:
            logger.exception("Terminal audit session initialization failed; continuing without audit recording.")
            self.session = None
            self.recording_last_event_at = None
            self.send(
                text_data=json.dumps(
                    {
                        "type": "output",
                        "data": "\r\n\x1b[33m[会话审计暂不可用，终端已切换为实时连接模式。请执行数据库迁移后恢复审计。]\x1b[0m\r\n",
                    },
                    ensure_ascii=False,
                )
            )

    def _is_authenticated(self) -> bool:
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return False

        session = self.scope.get("session")
        session_key = getattr(session, "session_key", None)
        if not session_key:
            return False

        try:
            if is_authenticated_session_expired(session):
                return False
            return bool(session.exists(session_key))
        except Exception:
            # 会话存储读取失败不等于用户已登出。connect() 已经校验过身份,登出/过期会让 exists()
            # 正常返回 False,所以这里把异常按"暂时查不到"处理并保持连接;否则会话存储或数据库
            # 抖动一次,就会把正在使用的终端断成"请先登录"。
            logger.exception("Terminal session lookup failed; keeping the existing terminal session open.")
            return True

    def _has_terminal_permission(self) -> bool:
        return has_feature_permission(self.scope.get("user"), "hosts", "terminal")

    def _send_initial_output(self):
        if self.connection is None:
            return
        try:
            output = self.connection.read_available_raw(
                timeout=float(self._terminal_setting("initialReadTimeoutSeconds")),
                idle_timeout=float(self._terminal_setting("initialReadIdleTimeoutMs")) / 1000,
            )
        except Exception:
            logger.exception("Terminal initial output read failed; continuing without a banner.")
            return
        if not output:
            return
        cleaned_output, cwd_paths, self.pending_output = strip_cwd_markers_with_pending(output)
        cwd_paths, self.current_cwd = filter_changed_cwd_paths(cwd_paths, self.current_cwd)
        if cleaned_output:
            self.transcript_chunks.append(cleaned_output)
            self._record_output(cleaned_output)
            self.send(text_data=json.dumps({"type": "output", "data": cleaned_output}, ensure_ascii=False))
        for path in cwd_paths:
            self.send(text_data=json.dumps({"type": "cwd", "path": path}, ensure_ascii=False))

    def _install_cwd_hook(self):
        if self.connection is None:
            return
        try:
            self.suppress_internal_echo_until = time.monotonic() + (float(self._terminal_setting("cwdHookSuppressEchoMs")) / 1000)
            self.connection.send_data(CWD_HOOK_ECHO_OFF + CWD_HOOK_INSTALL_SCRIPT + CWD_HOOK_ECHO_ON)
            self._drain_cwd_hook_output()
        except Exception:
            pass

    def _drain_cwd_hook_output(self):
        if self.connection is None:
            return
        try:
            self.connection.read_available_raw(
                timeout=float(self._terminal_setting("cwdHookDrainTimeoutMs")) / 1000,
                idle_timeout=float(self._terminal_setting("cwdHookDrainIdleTimeoutMs")) / 1000,
            )
        except Exception:
            pass

    def _record_input(self, data: str):
        if not self.session or not data:
            return
        try:
            self._append_recording_event("i", data)
            if self.alternate_screen_active:
                return
            self.command_buffer, commands = command_buffer_after_input(self.command_buffer, data)
            for command in commands:
                self._flush_pending_audit_output()
                self.pending_command_audit = create_command_audit(self.session, command, user=self.scope.get("user"))
                if is_interactive_terminal_command(command):
                    self._clear_pending_command_audit()
        except Exception:
            self._disable_audit_session("Terminal input audit failed")

    def _record_output(self, output: str):
        if not self.session or not output:
            return
        try:
            self._append_recording_event("o", output)
            next_alternate_screen_active = alternate_screen_state_after_output(self.alternate_screen_active, output)
            if next_alternate_screen_active != self.alternate_screen_active:
                self.command_buffer = ""
            if self.alternate_screen_active or next_alternate_screen_active or output_has_alternate_screen_sequence(output):
                self.alternate_screen_active = next_alternate_screen_active
                self._clear_pending_command_audit()
                return
            self.alternate_screen_active = next_alternate_screen_active
            if self.pending_command_audit:
                self.pending_command_output_chunks.append(output)
                self.pending_command_output_size += len(output)
                if self.pending_command_output_size >= AUDIT_OUTPUT_FLUSH_CHARS:
                    self._flush_pending_audit_output()
        except Exception:
            self._disable_audit_session("Terminal output audit failed")

    def _record_resize(self, cols: int, rows: int):
        if not self.session:
            return
        try:
            cols = max(1, min(cols, 300))
            rows = max(1, min(rows, 120))
            self.session.recording_cols = cols
            self.session.recording_rows = rows
            self._append_recording_event("r", f"{cols}x{rows}")
        except Exception:
            self._disable_audit_session("Terminal resize audit failed")

    def _record_exit(self, exit_code: int):
        if not self.session:
            return
        try:
            self._append_recording_event("x", int(exit_code))
        except Exception:
            self._disable_audit_session("Terminal exit audit failed")

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
        try:
            append_audit_output(self.pending_command_audit, "".join(self.pending_command_output_chunks))
        except Exception:
            self._disable_audit_session("Terminal command output audit flush failed")
            return
        self.pending_command_output_chunks = []
        self.pending_command_output_size = 0

    def _clear_pending_command_audit(self):
        self.pending_command_audit = None
        self.pending_command_output_chunks = []
        self.pending_command_output_size = 0

    def _disable_audit_session(self, message: str):
        logger.exception("%s; continuing without audit recording.", message)
        self.session = None
        self.pending_command_audit = None
        self.pending_command_output_chunks = []
        self.pending_command_output_size = 0
        self.recording_events = []
        self.recording_last_event_at = None

    def _close_session(self):
        if self.session is None:
            return

        self._flush_pending_audit_output()
        if self.session is None:
            return
        transcript = "".join(self.transcript_chunks)
        update_fields = ["status", "last_command_at", "recording_cols", "recording_rows", "recording_last_event_at"]
        self.session.status = "closed"
        self.session.last_command_at = timezone.now()
        if transcript:
            self.session.transcript += transcript
            update_fields.append("transcript")
        with self.recording_lock:
            events = list(self.recording_events)
            self.recording_events.clear()
        save_session_recording(self.session, events, update_fields=update_fields)
