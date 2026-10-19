from django.test import SimpleTestCase
from django.urls import Resolver404, resolve

from web_terminal.api.file_audits import terminal_file_audits
from web_terminal.services.file_audit import record_file_audit


class TerminalFeatureRemovalTests(SimpleTestCase):
    def test_removed_gateway_endpoint_is_not_routable(self):
        with self.assertRaises(Resolver404):
            resolve("/api/web-terminal/ssh-gateway/connection-info/")

    def test_file_audit_endpoint_is_preserved(self):
        self.assertIs(resolve("/api/web-terminal/file-audits/").func, terminal_file_audits)
        self.assertTrue(callable(record_file_audit))
