from importlib import import_module
from django.test import TestCase

from web_terminal import views


ENDPOINTS = [
    ("containers", "terminal_images", "/api/web-terminal/hosts/1/images/", ("post",)),
    ("containers", "terminal_networks", "/api/web-terminal/hosts/1/networks/", ("post",)),
    ("containers", "terminal_volumes", "/api/web-terminal/hosts/1/volumes/", ("post",)),
    ("files", "terminal_file_content", "/api/web-terminal/hosts/1/files/content/", ("get",)),
    ("files", "terminal_file_content_update", "/api/web-terminal/hosts/1/files/content/update/", ("post",)),
    ("sessions", "terminal_tree", "/api/web-terminal/tree/", ("get",)),
    ("sessions", "terminal_sessions", "/api/web-terminal/sessions/", ("post",)),
    (
        "sessions",
        "terminal_commands",
        "/api/web-terminal/sessions/00000000-0000-0000-0000-000000000001/commands/",
        ("post",),
    ),
    (
        "recordings",
        "terminal_session_recording",
        "/api/web-terminal/sessions/00000000-0000-0000-0000-000000000001/recording.cast",
        ("get",),
    ),
    (
        "recordings",
        "terminal_rdp_recording",
        "/api/web-terminal/sessions/00000000-0000-0000-0000-000000000001/rdp-recording/",
        ("get",),
    ),
    ("sessions", "session_audits", "/api/web-terminal/session-audits/", ("get",)),
    ("file_audits", "terminal_file_audits", "/api/web-terminal/file-audits/", ("get",)),
    ("sessions", "terminal_quick_commands", "/api/web-terminal/quick-commands/", ("get", "post")),
    (
        "sessions",
        "terminal_quick_commands_reorder",
        "/api/web-terminal/quick-commands/reorder/",
        ("post",),
    ),
    (
        "sessions",
        "terminal_quick_command_detail",
        "/api/web-terminal/quick-commands/1/",
        ("put", "delete"),
    ),
    ("monitoring", "terminal_monitor", "/api/web-terminal/hosts/1/monitor/", ("post",)),
    ("containers", "terminal_containers", "/api/web-terminal/hosts/1/containers/", ("post",)),
    ("containers", "terminal_container_action", "/api/web-terminal/hosts/1/containers/action/", ("post",)),
    ("containers", "terminal_container_logs", "/api/web-terminal/hosts/1/containers/logs/", ("post",)),
    ("files", "terminal_file_list", "/api/web-terminal/hosts/1/files/list/", ("post",)),
    (
        "files",
        "terminal_file_download_list",
        "/api/web-terminal/hosts/1/files/list-download/",
        ("post",),
    ),
    ("files", "terminal_file_download", "/api/web-terminal/hosts/1/files/download/", ("post",)),
    (
        "files",
        "terminal_file_download_attachment",
        "/api/web-terminal/hosts/1/files/download/raw/",
        ("get",),
    ),
    ("files", "terminal_file_upload", "/api/web-terminal/hosts/1/files/upload/", ("post",)),
    (
        "files",
        "terminal_file_create_file",
        "/api/web-terminal/hosts/1/files/create-file/",
        ("post",),
    ),
    (
        "files",
        "terminal_file_create_directory",
        "/api/web-terminal/hosts/1/files/create-directory/",
        ("post",),
    ),
    (
        "files",
        "terminal_file_create_symlink",
        "/api/web-terminal/hosts/1/files/create-symlink/",
        ("post",),
    ),
    ("files", "terminal_file_rename", "/api/web-terminal/hosts/1/files/rename/", ("post",)),
    ("files", "terminal_file_delete", "/api/web-terminal/hosts/1/files/delete/", ("post",)),
    (
        "files",
        "terminal_file_properties",
        "/api/web-terminal/hosts/1/files/properties/",
        ("post",),
    ),
    (
        "files",
        "terminal_file_properties_update",
        "/api/web-terminal/hosts/1/files/properties/update/",
        ("post",),
    ),
]


class TerminalApiModuleContractTests(TestCase):
    def test_views_explicitly_reexport_endpoint_implementations(self):
        for module_name, view_name, _url, _methods in ENDPOINTS:
            with self.subTest(view_name=view_name):
                implementation = getattr(import_module(f"web_terminal.api.{module_name}"), view_name)
                self.assertIs(getattr(views, view_name), implementation)

    def test_each_endpoint_preserves_allowed_methods_and_requires_authentication(self):
        for _module_name, view_name, url, methods in ENDPOINTS:
            view = getattr(views, view_name)
            allowed_methods = {method.lower() for method in view.cls.http_method_names if method != "options"}
            with self.subTest(view_name=view_name, contract="methods"):
                self.assertEqual(allowed_methods, set(methods))

            for method in methods:
                with self.subTest(view_name=view_name, method=method, contract="auth"):
                    response = getattr(self.client, method)(url, data={}, content_type="application/json")
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(set(response.json()), {"error"})

            unsupported_method = "delete" if "delete" not in methods else "patch"
            with self.subTest(view_name=view_name, method=unsupported_method, contract="method_not_allowed"):
                response = getattr(self.client, unsupported_method)(url, data={}, content_type="application/json")
                self.assertEqual(response.status_code, 405)
                self.assertEqual(set(response.json()), {"detail"})
