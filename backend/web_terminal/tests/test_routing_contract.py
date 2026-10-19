import re

from django.test import SimpleTestCase

from web_terminal import routing, urls, views
from web_terminal.consumers import RdpTerminalConsumer, TerminalConsumer


EXPECTED_HTTP_ROUTES = [
    ("web-terminal/tree/", None, "terminal_tree", "view"),
    ("web-terminal/sessions/", None, "terminal_sessions", "view"),
    (
        "web-terminal/sessions/<uuid:session_id>/commands/",
        None,
        "terminal_commands",
        "view",
    ),
    (
        "web-terminal/sessions/<uuid:session_id>/recording.cast",
        None,
        "terminal_session_recording",
        "view",
    ),
    (
        "web-terminal/sessions/<uuid:session_id>/rdp-recording/",
        None,
        "terminal_rdp_recording",
        "view",
    ),
    ("web-terminal/session-audits/", None, "session_audits", "view"),
    ("web-terminal/file-audits/", None, "terminal_file_audits", "view"),
    (
        "web-terminal/quick-commands/",
        None,
        "terminal_quick_commands",
        "view",
    ),
    (
        "web-terminal/quick-commands/reorder/",
        None,
        "terminal_quick_commands_reorder",
        "view",
    ),
    (
        "web-terminal/quick-commands/<int:command_id>/",
        None,
        "terminal_quick_command_detail",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/monitor/",
        None,
        "terminal_monitor",
        "view",
    ),
    ("web-terminal/hosts/<int:host_id>/containers/", None, "terminal_containers", "view"),
    ("web-terminal/hosts/<int:host_id>/containers/action/", None, "terminal_container_action", "view"),
    ("web-terminal/hosts/<int:host_id>/containers/logs/", None, "terminal_container_logs", "view"),
    (
        "web-terminal/hosts/<int:host_id>/files/list/",
        None,
        "terminal_file_list",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/list-download/",
        None,
        "terminal_file_download_list",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/download/",
        None,
        "terminal_file_download",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/download/raw/",
        None,
        "terminal_file_download_attachment",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/content/",
        None,
        "terminal_file_content",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/content/update/",
        None,
        "terminal_file_content_update",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/upload/",
        None,
        "terminal_file_upload",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/create-file/",
        None,
        "terminal_file_create_file",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/create-directory/",
        None,
        "terminal_file_create_directory",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/create-symlink/",
        None,
        "terminal_file_create_symlink",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/rename/",
        None,
        "terminal_file_rename",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/delete/",
        None,
        "terminal_file_delete",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/transfer/",
        None,
        "terminal_file_transfer",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/properties/",
        None,
        "terminal_file_properties",
        "view",
    ),
    (
        "web-terminal/hosts/<int:host_id>/files/properties/update/",
        None,
        "terminal_file_properties_update",
        "view",
    ),
]

EXPECTED_WEBSOCKET_ROUTES = [
    (
        "ws/web-terminal/rdp/<int:host_id>/",
        None,
        "RdpTerminalConsumer",
        RdpTerminalConsumer,
    ),
    (
        "ws/web-terminal/<int:host_id>/",
        None,
        "TerminalConsumer",
        TerminalConsumer,
    ),
]


def concrete_route(route):
    samples = {"int": "1", "uuid": "00000000-0000-0000-0000-000000000001"}
    return re.sub(
        r"<(?P<converter>int|uuid):[^>]+>",
        lambda match: samples[match.group("converter")],
        route,
    )


class HttpRoutingContractTests(SimpleTestCase):
    def test_http_routes_keep_literal_patterns_names_and_callbacks(self):
        self.assertEqual(len(urls.urlpatterns), len(EXPECTED_HTTP_ROUTES))

        for pattern, expected in zip(urls.urlpatterns, EXPECTED_HTTP_ROUTES):
            route, name, callback_export, callback_name = expected
            expected_callback = getattr(views, callback_export)

            with self.subTest(route=route):
                self.assertEqual(str(pattern.pattern), route)
                self.assertEqual(pattern.name, name)
                self.assertIs(pattern.callback, expected_callback)
                self.assertEqual(pattern.callback.__name__, callback_name)

                match = pattern.resolve(concrete_route(route))
                self.assertIsNotNone(match)
                self.assertIs(match.func, expected_callback)


class WebSocketRoutingContractTests(SimpleTestCase):
    def test_websocket_routes_keep_literal_patterns_and_consumers(self):
        self.assertEqual(
            len(routing.websocket_urlpatterns), len(EXPECTED_WEBSOCKET_ROUTES)
        )

        for pattern, expected in zip(
            routing.websocket_urlpatterns, EXPECTED_WEBSOCKET_ROUTES
        ):
            route, name, callback_name, consumer_class = expected

            with self.subTest(route=route):
                self.assertEqual(str(pattern.pattern), route)
                self.assertEqual(pattern.name, name)
                self.assertEqual(pattern.callback.__name__, callback_name)
                self.assertIs(pattern.callback.consumer_class, consumer_class)
                self.assertEqual(pattern.callback.consumer_initkwargs, {})

                match = pattern.resolve(concrete_route(route))
                self.assertIsNotNone(match)
                self.assertIs(match.func.consumer_class, consumer_class)
