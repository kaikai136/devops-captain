import os
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent.parent


def load_config_file(path: str | Path) -> dict[str, str]:
    config_path = Path(path)
    if not config_path.is_file():
        return {}

    config: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        config[key] = value
    return config


def config_file_path() -> Path:
    explicit_path = os.environ.get("APP_CONFIG_FILE", "").strip()
    if explicit_path:
        return Path(explicit_path)

    container_path = Path("/app/config/app.conf")
    if container_path.is_file():
        return container_path

    return container_path


APP_CONFIG_FILE = config_file_path()
APP_CONFIG = load_config_file(APP_CONFIG_FILE)


def config_value(name: str, default: str = "", *, config: dict[str, str] | None = None) -> str:
    # 优先级:app.conf 文件(部署权威) > 环境变量 > 代码默认值。
    # 支持环境变量便于本地开发临时覆盖与容器编排注入,
    # 无需改动不入库的 app.conf。
    source = APP_CONFIG if config is None else config
    if name in source:
        return source[name]
    env_value = os.environ.get(name)
    if env_value is not None:
        return env_value
    return default


def config_bool(name: str, default: bool = False, *, config: dict[str, str] | None = None) -> bool:
    value = config_value(name, "", config=config)
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def config_int(name: str, default: int, *, config: dict[str, str] | None = None) -> int:
    value = config_value(name, "", config=config)
    if not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def config_list(name: str, default: list[str] | None = None, *, config: dict[str, str] | None = None) -> list[str]:
    value = config_value(name, "", config=config)
    if not value.strip():
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


def config_path(name: str, default: Path, *, config: dict[str, str] | None = None) -> Path:
    value = config_value(name, "", config=config)
    if not value.strip():
        return default
    path = Path(value)
    if path.is_absolute():
        return path
    config_root = Path(APP_CONFIG_FILE).resolve().parent.parent
    return config_root / path


def redis_config_path() -> Path:
    configured_path = os.environ.get("REDIS_CONFIG_FILE", "").strip()
    if not configured_path:
        configured_path = APP_CONFIG.get("REDIS_CONFIG_FILE", "").strip()
    if configured_path:
        path = Path(configured_path)
        if path.is_absolute():
            return path
        return Path(APP_CONFIG_FILE).resolve().parent.parent / path

    return Path(APP_CONFIG_FILE).resolve().parent / "redis.conf"


def redis_channel_url() -> str:
    environment_url = os.environ.get("CHANNEL_REDIS_URL", "").strip()
    if environment_url:
        return environment_url

    redis_config = load_config_file(redis_config_path())
    configured_url = redis_config.get("REDIS_URL", redis_config.get("CHANNEL_REDIS_URL", "")).strip()
    if configured_url:
        return configured_url

    # Keep CHANNEL_REDIS_URL in app.conf working for older deployments.
    legacy_url = APP_CONFIG.get("CHANNEL_REDIS_URL", "").strip()
    if legacy_url:
        return legacy_url

    host = redis_config.get("REDIS_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = redis_config.get("REDIS_PORT", "6379").strip() or "6379"
    database = redis_config.get("REDIS_DB", "3").strip() or "3"
    password = redis_config.get("REDIS_PASSWORD", "")
    scheme = redis_config.get("REDIS_SCHEME", "redis").strip() or "redis"
    auth = f":{quote(password, safe='')}@" if password else ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{scheme}://{auth}{host}:{port}/{database}"


def django_secret_key() -> str:
    configured_secret = config_value("DJANGO_SECRET_KEY", "")
    if configured_secret.strip():
        return configured_secret

    secret_file = config_path("DJANGO_SECRET_KEY_FILE", Path("/app/data/django-secret-key"))
    try:
        persisted_secret = secret_file.read_text(encoding="utf-8").strip()
    except OSError:
        persisted_secret = ""
    return persisted_secret or "django-vue-dev-secret-key"


def database_config(config: dict[str, str] | None = None) -> dict:
    engine = config_value("DATABASE_ENGINE", "sqlite", config=config).strip().lower()
    if engine == "mysql":
        import pymysql

        pymysql.install_as_MySQLdb()
        return {
            "ENGINE": "django.db.backends.mysql",
            "NAME": config_value("DATABASE_NAME", "devops_tools", config=config),
            "USER": config_value("DATABASE_USER", "devops_tools", config=config),
            "PASSWORD": config_value("DATABASE_PASSWORD", "", config=config),
            "HOST": config_value("DATABASE_HOST", "127.0.0.1", config=config),
            "PORT": config_value("DATABASE_PORT", "3306", config=config),
            "OPTIONS": {"charset": "utf8mb4"},
        }

    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": config_path("DJANGO_DB_PATH", BASE_DIR / "db.sqlite3", config=config),
    }


SECRET_KEY = django_secret_key()
DEBUG = config_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = config_list("DJANGO_ALLOWED_HOSTS", ["*"])
CSRF_TRUSTED_ORIGINS = config_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "accounts",
    "network_tools",
    "passwords",
    "authenticators",
    "host_management",
    "web_terminal",
    "security_scanner",
    "bulk_execution",
    "company_assets",
    "application_market",
    "database_management",
    "operations",
    "system_management",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.SessionLockMiddleware",
    "system_management.middleware.OperationLogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ops_tool.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ops_tool.wsgi.application"
ASGI_APPLICATION = "ops_tool.asgi.application"

DATABASES = {"default": database_config()}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = config_value("TZ", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True

STATIC_URL = config_value("DJANGO_STATIC_URL", "/static/")
STATIC_ROOT = config_path("DJANGO_STATIC_ROOT", BASE_DIR / "staticfiles")
FRONTEND_DIST_DIR = config_path("DJANGO_FRONTEND_DIST_DIR", BASE_DIR / "frontend_dist")
STATICFILES_DIRS = [FRONTEND_DIST_DIR] if FRONTEND_DIST_DIR.exists() else []
MEDIA_URL = config_value("DJANGO_MEDIA_URL", "/media/")
MEDIA_ROOT = config_path("DJANGO_MEDIA_ROOT", BASE_DIR / "media")
DATABASE_ASSET_SQLITE_ROOT = config_path("DATABASE_ASSET_SQLITE_ROOT", BASE_DIR / "data" / "database_assets")
SERVE_MEDIA_FILES = config_bool("DJANGO_SERVE_MEDIA_FILES", DEBUG)
GUACD_HOST = config_value("GUACD_HOST", "127.0.0.1")
GUACD_PORT = config_int("GUACD_PORT", 4822)
RDP_RECORDING_ROOT = config_path("RDP_RECORDING_ROOT", BASE_DIR / "rdp_recordings")
RDP_RECORDING_RETENTION_DAYS = config_int("RDP_RECORDING_RETENTION_DAYS", 30)
RDP_RECORDING_DEFAULT_ENABLED = config_bool("RDP_RECORDING_DEFAULT_ENABLED", False)
SSH_GATEWAY_ENABLED = config_bool("SSH_GATEWAY_ENABLED", True)
SSH_GATEWAY_BIND_HOST = config_value("SSH_GATEWAY_BIND_HOST", "0.0.0.0")
SSH_GATEWAY_PORT = config_int("SSH_GATEWAY_PORT", 2222)
SSH_GATEWAY_PUBLIC_HOST = config_value("SSH_GATEWAY_PUBLIC_HOST", "")
SSH_GATEWAY_PUBLIC_PORT = config_int("SSH_GATEWAY_PUBLIC_PORT", SSH_GATEWAY_PORT)
SSH_GATEWAY_HOST_KEY_PATH = config_path("SSH_GATEWAY_HOST_KEY_PATH", BASE_DIR / "data" / "ssh-gateway-host-key")
BULK_EXECUTION_MAX_TARGETS = config_int("BULK_EXECUTION_MAX_TARGETS", 500)
BULK_EXECUTION_FORKS = config_int("BULK_EXECUTION_FORKS", 10)
BULK_EXECUTION_TIMEOUT_SECONDS = config_int("BULK_EXECUTION_TIMEOUT_SECONDS", 300)
BULK_EXECUTION_RUN_ASYNC = config_bool("BULK_EXECUTION_RUN_ASYNC", True)
DATA_UPLOAD_MAX_NUMBER_FILES = config_int("DATA_UPLOAD_MAX_NUMBER_FILES", 1000)
WHITENOISE_AUTOREFRESH = config_bool("WHITENOISE_AUTOREFRESH", DEBUG)
WHITENOISE_USE_FINDERS = config_bool("WHITENOISE_USE_FINDERS", DEBUG)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOW_ALL_ORIGINS = config_bool("DJANGO_CORS_ALLOW_ALL_ORIGINS", DEBUG)
CORS_ALLOWED_ORIGINS = config_list("DJANGO_CORS_ALLOWED_ORIGINS")

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.CsrfExemptSessionAuthentication"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser", "rest_framework.parsers.MultiPartParser", "rest_framework.parsers.FormParser"],
    "URL_FORMAT_OVERRIDE": None,
}

# 缓存 TTL(秒)集中管理,替代散落在各处的魔法值。
DASHBOARD_CACHE_SECONDS = config_int("DASHBOARD_CACHE_SECONDS", 30)
EGRESS_CACHE_SECONDS = config_int("EGRESS_CACHE_SECONDS", 300)
FEATURE_PERMISSION_CACHE_SECONDS = config_int("FEATURE_PERMISSION_CACHE_SECONDS", 300)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.db"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [redis_channel_url()]},
    }
}
DATABASE_TRANSFER_DIR = config_path("DATABASE_TRANSFER_DIR", BASE_DIR / "database-transfer")
DATABASE_TRANSFER_RETENTION_DAYS = config_int("DATABASE_TRANSFER_RETENTION_DAYS", 7)
DATABASE_TRANSFER_CHUNK_BYTES = config_int("DATABASE_TRANSFER_CHUNK_BYTES", 8 * 1024 * 1024)
DATABASE_TRANSFER_BATCH_ROWS = config_int("DATABASE_TRANSFER_BATCH_ROWS", 500)
DATABASE_TRANSFER_TASK_TIMEOUT_SECONDS = config_int("DATABASE_TRANSFER_TASK_TIMEOUT_SECONDS", 86400)
DATABASE_TRANSFER_MIN_FREE_BYTES = config_int("DATABASE_TRANSFER_MIN_FREE_BYTES", 2 * 1024 * 1024 * 1024)
DATABASE_TRANSFER_MAX_ROWS = config_int("DATABASE_TRANSFER_MAX_ROWS", 0)
DATABASE_TRANSFER_MAX_TABLES = config_int("DATABASE_TRANSFER_MAX_TABLES", 0)
DATABASE_TRANSFER_MAX_UPLOAD_BYTES = config_int("DATABASE_TRANSFER_MAX_UPLOAD_BYTES", 0)
DATABASE_TRANSFER_MAX_RESULT_BYTES = config_int("DATABASE_TRANSFER_MAX_RESULT_BYTES", 0)
DATABASE_TRANSFER_MAX_SQL_STATEMENT_BYTES = config_int("DATABASE_TRANSFER_MAX_SQL_STATEMENT_BYTES", 64 * 1024 * 1024)
