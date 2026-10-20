"""Request-scoped MySQL connection, optional SSH forwarding and policy checks."""
import io
import select
import socket
import threading
from contextlib import ExitStack

from .connection_config import enforce_policy, enforce_sql, secrets_for, ssl_context
from .credentials import resolve_credentials


class CheckedCursor:
    def __init__(self, cursor, asset):
        self.cursor, self.asset = cursor, asset

    def __getattr__(self, name): return getattr(self.cursor, name)

    def execute(self, sql, args=None):
        enforce_sql(self.asset, sql)
        return self.cursor.execute(sql, args)

    def executemany(self, sql, args):
        enforce_sql(self.asset, sql)
        return self.cursor.executemany(sql, args)

    def __enter__(self): return self

    def __exit__(self, *_args): self.close()

    def close(self): return self.cursor.close()


class ManagedConnection:
    def __init__(self, conn, resources, asset):
        self.conn, self.resources, self.asset = conn, resources, asset

    def __getattr__(self, name): return getattr(self.conn, name)

    def cursor(self, *args, **kwargs): return CheckedCursor(self.conn.cursor(*args, **kwargs), self.asset)

    def close(self): self.resources.close()

    def __enter__(self): return self

    def __exit__(self, *_args): self.close()


def prepare_export_snapshot(conn):
    """Trusted export setup, separate from user SQL and never enables writes."""
    from .mysql_dump import query
    if isinstance(conn, ManagedConnection):
        enforce_policy(conn.asset)
        raw = conn.conn
    else:
        raw = conn
    query(raw, "SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO'")
    query(raw, "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    query(raw, "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")


def ssh_socket(asset, secrets, timeout, resources):
    import paramiko
    ssh = asset.options["ssh"]
    client = paramiko.SSHClient()
    resources.callback(client.close)
    # Match the application's existing SSH host-key policy; never poll other credentials.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {}
    if ssh.get("authMethod") == "privateKey":
        data = secrets["sshPrivateKey"]["content"]
        error = None
        for kind in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
            try:
                kwargs["pkey"] = kind.from_private_key(io.StringIO(data), password=secrets.get("sshKeyPassword") or None)
                break
            except (ValueError, paramiko.SSHException) as exc: error = exc
        if "pkey" not in kwargs: raise ValueError("SSH 私钥无法解析") from error
    else:
        kwargs["password"] = secrets.get("sshPassword")
    client.connect(hostname=ssh["host"], port=ssh.get("port", 22), username=ssh["username"],
                   timeout=timeout, auth_timeout=timeout, banner_timeout=timeout,
                   allow_agent=False, look_for_keys=False, **kwargs)
    transport = client.get_transport()
    transport.set_keepalive(30)
    channel = transport.open_channel("direct-tcpip", (asset.host, asset.port), ("127.0.0.1", 0), timeout=timeout)
    resources.callback(channel.close)
    # A real socket is required by SSLContext. Socket-pair forwarding preserves
    # the original MySQL hostname for TLS identity validation without a listener.
    local, relay = socket.socketpair()
    resources.callback(relay.close)
    resources.callback(local.close)
    stopped = threading.Event()
    def forward():
        try:
            while not stopped.is_set():
                ready, _, _ = select.select([relay, channel], [], [], 0.25)
                for source in ready:
                    data = source.recv(65536)
                    if not data: return
                    (channel if source is relay else relay).sendall(data)
        except (OSError, EOFError, paramiko.SSHException):
            pass
        finally:
            try: relay.shutdown(socket.SHUT_RDWR)
            except OSError: pass
    thread = threading.Thread(target=forward, name="mysql-ssh-forward", daemon=True)
    thread.start()
    def stop():
        stopped.set()
        channel.close()
        relay.close()
        thread.join(timeout=1)
    resources.callback(stop)
    return local


def connect(asset, database, module, *, credentials=None):
    enforce_policy(asset)
    options, secrets = asset.options or {}, secrets_for(asset)
    params = options.get("parameters", {})
    timeout = options.get("connectTimeout", 5)
    username, password = resolve_credentials(asset) if credentials is None else credentials
    resources = ExitStack()
    try:
        kwargs = dict(host=asset.host, port=asset.port, user=username,
                      password=password,
                      database=database or asset.database or None, charset=options.get("charset", "auto"),
                      connect_timeout=timeout, read_timeout=params.get("readTimeout", 20),
                      write_timeout=params.get("writeTimeout", 20), autocommit=params.get("autocommit", False),
                      cursorclass=module.cursors.DictCursor)
        if kwargs["charset"] == "auto": kwargs["charset"] = "utf8mb4"
        if options.get("ssl"):
            kwargs["ssl"] = ssl_context(options, secrets)
        else:
            kwargs["ssl_disabled"] = True
        use_ssh = options.get("ssh", {}).get("enabled")
        if use_ssh or options.get("ssl"):
            sock = ssh_socket(asset, secrets, timeout, resources) if use_ssh else None
            conn = module.connect(**kwargs, defer_connect=True)
            resources.callback(conn.close)
            if options.get("ssl"):
                # PyMySQL 1.x otherwise silently falls back to plaintext when
                # a server omits CLIENT.SSL. Reject before sending credentials.
                authenticate = conn._request_authentication
                def require_tls():
                    if not conn.server_capabilities & 2048:  # MySQL CLIENT.SSL
                        raise ValueError("SSL 已启用，但 MySQL 服务端不支持 TLS")
                    return authenticate()
                conn._request_authentication = require_tls
            if sock is not None: conn.connect(sock=sock)
            else: conn.connect()
        else:
            conn = module.connect(**kwargs)
            resources.callback(conn.close)
        with conn.cursor() as cursor:
            if "sqlMode" in params: cursor.execute("SET SESSION sql_mode=%s", (params["sqlMode"],))
            if params.get("timeZone"): cursor.execute("SET SESSION time_zone=%s", (params["timeZone"],))
            if options.get("readOnly"): cursor.execute("SET SESSION TRANSACTION READ ONLY")
        return ManagedConnection(conn, resources, asset)
    except Exception:
        resources.close()
        raise
