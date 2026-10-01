from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings


class FrontendServingTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.frontend_dist = Path(self.temp_dir.name)
        (self.frontend_dist / "index.html").write_text(
            "<!doctype html><html><body><div id=\"app\"></div></body></html>",
            encoding="utf-8",
        )
        (self.frontend_dist / "terminal.html").write_text(
            "<!doctype html><html><body><div id=\"terminal-app\"></div></body></html>",
            encoding="utf-8",
        )
        (self.frontend_dist / "host-terminal.html").write_text(
            "<!doctype html><html><body><div id=\"host-terminal-app\"></div></body></html>",
            encoding="utf-8",
        )
        self.banner_bytes = b"\x89PNG\r\n\x1a\nbrand"
        (self.frontend_dist / "captain-banner.png").write_bytes(self.banner_bytes)
        self.static_root = self.frontend_dist / "static-root"
        self.static_root.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_root_serves_frontend_index(self):
        with override_settings(FRONTEND_DIST_DIR=self.frontend_dist, STATIC_ROOT=self.static_root):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertIn(b'id="app"', b"".join(response.streaming_content))

    def test_terminal_html_serves_terminal_entry_with_querystring(self):
        with override_settings(FRONTEND_DIST_DIR=self.frontend_dist, STATIC_ROOT=self.static_root):
            response = self.client.get("/terminal.html?hostId=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="terminal-app"', b"".join(response.streaming_content))

    def test_host_terminal_html_serves_simple_terminal_entry_with_querystring(self):
        with override_settings(FRONTEND_DIST_DIR=self.frontend_dist, STATIC_ROOT=self.static_root):
            response = self.client.get("/host-terminal.html?host=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="host-terminal-app"', b"".join(response.streaming_content))

    def test_frontend_route_falls_back_to_index(self):
        with override_settings(FRONTEND_DIST_DIR=self.frontend_dist, STATIC_ROOT=self.static_root):
            response = self.client.get("/hosts")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="app"', b"".join(response.streaming_content))

    def test_root_level_frontend_asset_serves_file(self):
        with override_settings(FRONTEND_DIST_DIR=self.frontend_dist, STATIC_ROOT=self.static_root):
            response = self.client.get("/captain-banner.png")

        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")
            self.assertEqual(b"".join(response.streaming_content), self.banner_bytes)
        finally:
            response.close()

    def test_missing_frontend_dist_returns_not_found(self):
        with override_settings(FRONTEND_DIST_DIR=self.frontend_dist / "missing", STATIC_ROOT=self.static_root):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 404)


class ConfigFileTests(SimpleTestCase):
    def test_load_config_file_parses_deployment_config(self):
        with TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "app.conf"
            config_file.write_text(
                "\n".join(
                    [
                        "# comment",
                        "DJANGO_ALLOWED_HOSTS=ops.example.com,172.16.0.99",
                        "DJANGO_DEBUG=0",
                        "GUACD_PORT=4822",
                        "DJANGO_SECRET_KEY=",
                    ]
                ),
                encoding="utf-8",
            )

            from ops_tool import settings

            config = settings.load_config_file(config_file)

        self.assertEqual(config["DJANGO_ALLOWED_HOSTS"], "ops.example.com,172.16.0.99")
        self.assertEqual(config["DJANGO_SECRET_KEY"], "")
        self.assertFalse(settings.config_bool("DJANGO_DEBUG", True, config=config))
        self.assertEqual(settings.config_int("GUACD_PORT", 1, config=config), 4822)
        self.assertEqual(settings.config_list("DJANGO_ALLOWED_HOSTS", config=config), ["ops.example.com", "172.16.0.99"])

    def test_database_config_uses_mysql_when_configured(self):
        from ops_tool import settings

        database = settings.database_config(
            {
                "DATABASE_ENGINE": "mysql",
                "DATABASE_NAME": "devops_tools",
                "DATABASE_USER": "devops_tools",
                "DATABASE_PASSWORD": "secret-password",
                "DATABASE_HOST": "mysql.example.com",
                "DATABASE_PORT": "3306",
            }
        )

        self.assertEqual(database["ENGINE"], "django.db.backends.mysql")
        self.assertEqual(database["NAME"], "devops_tools")
        self.assertEqual(database["USER"], "devops_tools")
        self.assertEqual(database["PASSWORD"], "secret-password")
        self.assertEqual(database["HOST"], "mysql.example.com")
        self.assertEqual(database["PORT"], "3306")
        self.assertEqual(database["OPTIONS"], {"charset": "utf8mb4"})

    def test_database_config_mysql_default_host_is_not_compose_service(self):
        from ops_tool import settings

        database = settings.database_config({"DATABASE_ENGINE": "mysql"})

        self.assertEqual(database["HOST"], "127.0.0.1")

    def test_database_config_keeps_sqlite_default(self):
        from ops_tool import settings

        database = settings.database_config({"DATABASE_ENGINE": "sqlite", "DJANGO_DB_PATH": "/tmp/app.sqlite3"})

        self.assertEqual(database["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(database["NAME"], Path("/tmp/app.sqlite3"))

    def test_config_path_resolves_relative_values_from_config_root(self):
        from ops_tool import settings

        original_config_file = settings.APP_CONFIG_FILE
        try:
            settings.APP_CONFIG_FILE = Path("/repo/config/local.app.conf")
            path = settings.config_path("DJANGO_DB_PATH", Path("/fallback.sqlite3"), config={"DJANGO_DB_PATH": "backend/db.sqlite3"})
        finally:
            settings.APP_CONFIG_FILE = original_config_file

        self.assertEqual(path, Path("/repo/backend/db.sqlite3"))

    def test_runtime_uses_local_cache_db_sessions_and_redis_channels(self):
        from ops_tool import settings

        self.assertEqual(settings.CACHES["default"]["BACKEND"], "django.core.cache.backends.locmem.LocMemCache")
        self.assertEqual(settings.SESSION_ENGINE, "django.contrib.sessions.backends.db")
        self.assertEqual(settings.CHANNEL_LAYERS["default"]["BACKEND"], "channels_redis.core.RedisChannelLayer")
