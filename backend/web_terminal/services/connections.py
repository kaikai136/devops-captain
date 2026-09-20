from __future__ import annotations

import codecs
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
import threading
import time

from django.utils import timezone

from host_management.models import HostCredential, ManagedHost
from system_management.settings_defaults import DEFAULT_TERMINAL_SETTINGS

from .errors import TerminalConnectionError

class LiveTerminalConnection:
    def __init__(self, client, channel, terminal_settings: dict | None = None):
        self.client = client
        self.channel = channel
        self.lock = threading.Lock()
        self.terminal_settings = normalize_terminal_settings(terminal_settings)
        self.output_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def read_available(self, timeout: float = 4.0, idle_timeout: float = 0.35) -> str:
        return normalize_terminal_output(self.read_available_raw(timeout=timeout, idle_timeout=idle_timeout))

    def read_available_raw(self, timeout: float = 4.0, idle_timeout: float = 0.35) -> str:
        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout
        last_data_at: float | None = None

        while time.monotonic() < deadline:
            if self.channel.recv_ready():
                chunks.append(self.channel.recv(65535))
                last_data_at = time.monotonic()
                continue

            if chunks and last_data_at and time.monotonic() - last_data_at >= idle_timeout:
                break
            if self.channel.closed or self.channel.exit_status_ready():
                break
            time.sleep(0.05)

        return self._decode_output(b"".join(chunks))

    def read_raw(self, max_bytes: int = 65535) -> str:
        if not self.channel.recv_ready():
            return ""
        return self._decode_output(self.channel.recv(max_bytes))

    def _decode_output(self, data: bytes) -> str:
        if not data:
            return ""
        return self.output_decoder.decode(data, final=False)

    def send_data(self, data: str) -> None:
        with self.lock:
            if self.channel.closed:
                raise TerminalConnectionError("SSH 会话已关闭，请重新连接主机。")
            if data:
                self.channel.sendall(data)

    def send_command(self, command: str) -> str:
        self.send_data(command + "\n")
        return self.read_available(
            timeout=float(self.terminal_settings["commandReadTimeoutSeconds"]),
            idle_timeout=float(self.terminal_settings["commandReadIdleTimeoutMs"]) / 1000,
        )

    def resize(self, cols: int, rows: int) -> None:
        cols = max(1, min(cols, 300))
        rows = max(1, min(rows, 120))
        with self.lock:
            if not self.channel.closed:
                self.channel.resize_pty(width=cols, height=rows)

    def close(self) -> None:
        try:
            self.channel.close()
        finally:
            self.client.close()

LIVE_TERMINALS: dict[str, LiveTerminalConnection] = {}

DEFAULT_TERMINAL_COLS = 120
DEFAULT_TERMINAL_ROWS = 36
DEFAULT_SSH_TERMINAL_TYPE = "vt100"
SSH_CONNECT_ATTEMPTS = 3
SSH_CONNECT_TIMEOUT = 15
SSH_BANNER_TIMEOUT = 30
SSH_AUTH_TIMEOUT = 20
SSH_RETRY_DELAY_SECONDS = 0.8
SSH_CREDENTIAL_POLL_ATTEMPTS = 1
SSH_CLIENT_POOL_IDLE_SECONDS = 45.0
SSH_CLIENT_POOL_MAX_PER_HOST = 2
_SSH_CLIENT_POOL: dict[tuple[str, str, int, str], list[tuple[float, object]]] = {}
_SSH_CLIENT_POOL_LOCK = threading.Lock()
SSH_RETRY_ERROR_MARKERS = (
    "error reading ssh protocol banner",
    "error reading protocol banner",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "temporarily unavailable",
)
SSH_CONNECTIVITY_FAILURE_MARKERS = SSH_RETRY_ERROR_MARKERS + (
    "connection refused",
    "no route to host",
    "network is unreachable",
    "unable to connect",
)


def normalize_terminal_settings(value: dict | None = None) -> dict:
    if not isinstance(value, dict):
        return DEFAULT_TERMINAL_SETTINGS.copy()
    return {**DEFAULT_TERMINAL_SETTINGS, **value}


@dataclass(frozen=True)
class SshLoginCandidate:
    username: str
    password: str = ""
    private_key_name: str = ""
    private_key: str = ""
    persist_to_host: bool = False


def open_live_terminal(host: ManagedHost, cols: int = 120, rows: int = 36, terminal_settings: dict | None = None) -> LiveTerminalConnection:
    effective_settings = normalize_terminal_settings(terminal_settings)
    client = open_ssh_client(host, terminal_settings=effective_settings)
    try:
        channel = client.invoke_shell(term=DEFAULT_SSH_TERMINAL_TYPE, width=cols, height=rows)
        channel.settimeout(0.0)
        return LiveTerminalConnection(client, channel, terminal_settings=effective_settings)
    except Exception as error:
        client.close()
        raise TerminalConnectionError(f"SSH 会话创建失败：{error}")


def open_ssh_client(host: ManagedHost, *, terminal_settings: dict | None = None):
    effective_settings = normalize_terminal_settings(terminal_settings)
    current_candidate = current_host_login_candidate(host)
    errors: list[str] = []
    stop_credential_polling = False

    if current_candidate is not None:
        try:
            return connect_ssh_candidate(host, current_candidate, terminal_settings=effective_settings)
        except TerminalConnectionError as error:
            message = str(error)
            errors.append(message)
            stop_credential_polling = is_connectivity_ssh_failure_message(message)

    if should_poll_host_credentials(host) and not stop_credential_polling:
        seen = {candidate_identity(current_candidate)} if current_candidate is not None else set()
        for candidate in host_credential_login_candidates(seen):
            try:
                client = connect_ssh_candidate(
                    host,
                    candidate,
                    attempts=SSH_CREDENTIAL_POLL_ATTEMPTS,
                    terminal_settings=effective_settings,
                )
            except TerminalConnectionError as error:
                message = str(error)
                errors.append(message)
                if is_connectivity_ssh_failure_message(message):
                    break
                continue
            persist_login_candidate_to_host(host, candidate)
            return client

    if not errors and current_candidate is None:
        raise TerminalConnectionError("主机未配置登录用户，请先在主机管理中补充用户或选择账号。")

    last_error = errors[-1] if errors else "unknown error"
    if last_error.startswith("SSH 连接失败："):
        raise TerminalConnectionError(last_error)
    raise TerminalConnectionError(f"SSH 连接失败：{last_error}")


@contextmanager
def borrow_ssh_client(host: ManagedHost, *, terminal_settings: dict | None = None):
    """Borrow an exclusive SSH client and return it to a small idle pool.

    Live terminal shells intentionally keep dedicated connections. The pool is
    only for short-lived file operations which would otherwise pay a full SSH
    handshake for every HTTP request.
    """

    key = ssh_client_pool_key(host)
    client = _take_pooled_ssh_client(key)
    if client is None:
        client = open_ssh_client(host, terminal_settings=terminal_settings)
        key = ssh_client_pool_key(host)
    try:
        yield client
    except Exception:
        _close_ssh_client(client)
        raise
    else:
        if _ssh_client_is_active(client):
            _return_pooled_ssh_client(key, client)
        else:
            _close_ssh_client(client)


def ssh_client_pool_key(host: ManagedHost) -> tuple[str, str, int, str]:
    target = str(getattr(host, "public_ip", "") or getattr(host, "private_ip", "") or "")
    port = int(getattr(host, "port", 22) or 22)
    host_identity = str(getattr(host, "pk", None) or getattr(host, "id", None) or id(host))
    credential_material = "\0".join(
        (
            str(getattr(host, "login_user", "") or ""),
            str(getattr(host, "login_password", "") or ""),
            str(getattr(host, "private_key", "") or ""),
        )
    )
    credential_fingerprint = hashlib.sha256(credential_material.encode("utf-8")).hexdigest()
    return host_identity, target, port, credential_fingerprint


def clear_ssh_client_pool() -> None:
    with _SSH_CLIENT_POOL_LOCK:
        pooled = [client for entries in _SSH_CLIENT_POOL.values() for _returned_at, client in entries]
        _SSH_CLIENT_POOL.clear()
    for client in pooled:
        _close_ssh_client(client)


def _take_pooled_ssh_client(key):
    now = time.monotonic()
    expired = []
    selected = None
    with _SSH_CLIENT_POOL_LOCK:
        for pool_key, entries in list(_SSH_CLIENT_POOL.items()):
            active_entries = []
            for returned_at, client in entries:
                if now - returned_at > SSH_CLIENT_POOL_IDLE_SECONDS or not _ssh_client_is_active(client):
                    expired.append(client)
                else:
                    active_entries.append((returned_at, client))
            if active_entries:
                _SSH_CLIENT_POOL[pool_key] = active_entries
            else:
                _SSH_CLIENT_POOL.pop(pool_key, None)

        entries = _SSH_CLIENT_POOL.get(key, [])
        if entries:
            _returned_at, selected = entries.pop()
        if entries:
            _SSH_CLIENT_POOL[key] = entries
        else:
            _SSH_CLIENT_POOL.pop(key, None)

    for client in expired:
        _close_ssh_client(client)
    return selected


def _return_pooled_ssh_client(key, client) -> None:
    now = time.monotonic()
    to_close = []
    with _SSH_CLIENT_POOL_LOCK:
        entries = _SSH_CLIENT_POOL.setdefault(key, [])
        entries.append((now, client))
        while len(entries) > SSH_CLIENT_POOL_MAX_PER_HOST:
            _returned_at, stale_client = entries.pop(0)
            to_close.append(stale_client)
    for stale_client in to_close:
        _close_ssh_client(stale_client)


def _ssh_client_is_active(client) -> bool:
    try:
        transport = client.get_transport()
        return bool(transport and transport.is_active())
    except Exception:
        return False


def _close_ssh_client(client) -> None:
    try:
        client.close()
    except Exception:
        pass


def current_host_login_candidate(host: ManagedHost) -> SshLoginCandidate | None:
    username = str(getattr(host, "login_user", "") or "").strip()
    if not username:
        return None
    return SshLoginCandidate(
        username=username,
        password=str(getattr(host, "login_password", "") or ""),
        private_key_name=str(getattr(host, "private_key_name", "") or ""),
        private_key=str(getattr(host, "private_key", "") or ""),
    )


def should_poll_host_credentials(host: ManagedHost) -> bool:
    return isinstance(host, ManagedHost) and bool(getattr(host, "pk", None))


def host_credential_login_candidates(seen: set[tuple[str, str, str]]) -> list[SshLoginCandidate]:
    candidates: list[SshLoginCandidate] = []
    for credential in HostCredential.objects.order_by("id"):
        username = str(credential.username or "").strip()
        if not username:
            continue
        candidate = SshLoginCandidate(
            username=username,
            password=credential.password or "",
            private_key_name=credential.private_key_name or "",
            private_key=credential.private_key or "",
            persist_to_host=True,
        )
        identity = candidate_identity(candidate)
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append(candidate)
    return candidates


def candidate_identity(candidate: SshLoginCandidate | None) -> tuple[str, str, str]:
    if candidate is None:
        return ("", "", "")
    return (candidate.username, candidate.password, candidate.private_key)


def persist_login_candidate_to_host(host: ManagedHost, candidate: SshLoginCandidate) -> None:
    if not candidate.persist_to_host:
        return
    host.login_user = candidate.username
    host.login_password = candidate.password
    host.private_key_name = candidate.private_key_name
    host.private_key = candidate.private_key
    host.updated_at = timezone.now()
    host.save(update_fields=["login_user", "login_password", "private_key_name", "private_key", "updated_at"])


def connect_ssh_candidate(
    host: ManagedHost,
    candidate: SshLoginCandidate,
    attempts: int | None = None,
    terminal_settings: dict | None = None,
):
    if not candidate.username:
        raise TerminalConnectionError("主机未配置登录用户，请先在主机管理中补充用户或选择账号。")

    try:
        import paramiko
    except ImportError:
        raise TerminalConnectionError("后端未安装 paramiko，无法建立 SSH 连接。请安装 requirements.txt 后重启后端。")

    target = str(host.public_ip or host.private_ip)
    try:
        pkey = load_private_key(paramiko, candidate.private_key)
    except ValueError as error:
        raise TerminalConnectionError(str(error))

    errors: list[str] = []
    effective_settings = normalize_terminal_settings(terminal_settings)
    max_attempts = max(1, int(attempts if attempts is not None else effective_settings["sshConnectAttempts"]))
    for attempt in range(1, max_attempts + 1):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=target,
                port=host.port,
                username=candidate.username,
                password=candidate.password or None,
                pkey=pkey,
                timeout=effective_settings["sshConnectTimeoutSeconds"],
                banner_timeout=effective_settings["sshBannerTimeoutSeconds"],
                auth_timeout=effective_settings["sshAuthTimeoutSeconds"],
                look_for_keys=False,
                allow_agent=False,
            )
            transport = client.get_transport()
            keepalive = int(effective_settings["sshKeepaliveSeconds"])
            if transport is not None and keepalive > 0:
                transport.set_keepalive(keepalive)
            return client
        except Exception as error:
            errors.append(str(error))
            client.close()
            if attempt >= max_attempts or not should_retry_ssh_connect_error(error):
                break
            time.sleep((float(effective_settings["sshRetryDelayMs"]) / 1000) * attempt)

    last_error = errors[-1] if errors else "unknown error"
    raise TerminalConnectionError(f"SSH 连接失败：{last_error}")


def _open_ssh_client_with_host_fields(host: ManagedHost):
    if not host.login_user:
        raise TerminalConnectionError("主机未配置登录用户，请先在主机管理中补充用户或选择账号。")

    try:
        import paramiko
    except ImportError:
        raise TerminalConnectionError("后端未安装 paramiko，无法建立 SSH 连接。请安装 requirements.txt 后重启后端。")

    target = str(host.public_ip or host.private_ip)
    try:
        pkey = load_private_key(paramiko, host.private_key)
    except ValueError as error:
        raise TerminalConnectionError(str(error))

    errors: list[str] = []
    for attempt in range(1, SSH_CONNECT_ATTEMPTS + 1):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=target,
                port=host.port,
                username=host.login_user,
                password=host.login_password or None,
                pkey=pkey,
                timeout=SSH_CONNECT_TIMEOUT,
                banner_timeout=SSH_BANNER_TIMEOUT,
                auth_timeout=SSH_AUTH_TIMEOUT,
                look_for_keys=False,
                allow_agent=False,
            )
            transport = client.get_transport()
            if transport is not None:
                transport.set_keepalive(30)
            return client
        except Exception as error:
            errors.append(str(error))
            client.close()
            if attempt >= SSH_CONNECT_ATTEMPTS or not should_retry_ssh_connect_error(error):
                break
            time.sleep(SSH_RETRY_DELAY_SECONDS * attempt)

    last_error = errors[-1] if errors else "unknown error"
    raise TerminalConnectionError(f"SSH 连接失败：{last_error}")


def should_retry_ssh_connect_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in SSH_RETRY_ERROR_MARKERS)


def is_connectivity_ssh_failure_message(message: str) -> bool:
    normalized = message.lower()
    return any(marker in normalized for marker in SSH_CONNECTIVITY_FAILURE_MARKERS)


def load_private_key(paramiko, private_key: str):
    if not private_key.strip():
        return None

    errors = []
    for key_class in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey):
        try:
            return key_class.from_private_key(io.StringIO(private_key))
        except Exception as error:
            errors.append(str(error))
    raise ValueError(f"私钥解析失败：{errors[-1] if errors else '未知错误'}")


def normalize_terminal_output(output: str) -> str:
    return output.replace("\r\n", "\n").replace("\r", "\n").rstrip()


__all__ = [
    'DEFAULT_TERMINAL_COLS',
    'DEFAULT_TERMINAL_ROWS',
    'LIVE_TERMINALS',
    'LiveTerminalConnection',
    'TerminalConnectionError',
    'borrow_ssh_client',
    'clear_ssh_client_pool',
    'load_private_key',
    'normalize_terminal_output',
    'open_live_terminal',
    'open_ssh_client',
    'ssh_client_pool_key',
    'should_retry_ssh_connect_error',
]
