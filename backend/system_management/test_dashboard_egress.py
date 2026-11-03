import json
import subprocess
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .dashboard import EGRESS_CACHE_KEY, get_egress_network, parse_ipwhois_output


@patch("system_management.dashboard.cache")
@patch("system_management.dashboard.subprocess.run")
class EgressNetworkTests(SimpleTestCase):
    def setUp(self):
        self.fallback = json.dumps({
            "success": True,
            "ip": "203.0.113.8",
            "country": "中国",
            "region": "江苏",
            "city": "南京",
            "connection": {"isp": "电信"},
        })

    def test_falls_back_after_timeout(self, mock_run, mock_cache):
        mock_cache.get.return_value = None
        mock_run.side_effect = [
            subprocess.TimeoutExpired("curl", 5),
            Mock(returncode=0, stdout=self.fallback),
        ]

        payload = get_egress_network()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["ip"], "203.0.113.8")
        self.assertEqual(payload["location"], "中国 江苏 南京")
        self.assertEqual(payload["isp"], "电信")
        self.assertEqual(payload["error"], "")
        self.assertEqual(mock_run.call_args.args[0][-1], "https://ipwho.is/")

    def test_falls_back_after_curl_http_error(self, mock_run, mock_cache):
        mock_cache.get.return_value = None
        mock_run.side_effect = [
            Mock(returncode=22, stdout="", stderr="HTTP 403"),
            Mock(returncode=0, stdout=self.fallback),
        ]

        self.assertEqual(get_egress_network()["status"], "ok")

    def test_falls_back_after_html_or_invalid_ip_response(self, mock_run, mock_cache):
        mock_cache.get.return_value = None
        for response in ("<html>blocked</html>", "IP: unavailable"):
            with self.subTest(response=response):
                mock_run.side_effect = [
                    Mock(returncode=0, stdout=response),
                    Mock(returncode=0, stdout=self.fallback),
                ]

                self.assertEqual(get_egress_network()["ip"], "203.0.113.8")

    def test_successful_primary_does_not_request_fallback(self, mock_run, mock_cache):
        mock_cache.get.return_value = None
        mock_run.return_value = Mock(returncode=0, stdout="IP: 203.0.113.7\n地址: 中国")

        self.assertEqual(get_egress_network()["ip"], "203.0.113.7")
        mock_run.assert_called_once()

    def test_all_sources_failed_are_cached_briefly(self, mock_run, mock_cache):
        mock_cache.get.return_value = None
        mock_run.return_value = Mock(returncode=28, stdout="", stderr="operation timed out")

        payload = get_egress_network()

        self.assertEqual(payload["status"], "error")
        self.assertIn("timed out", payload["error"])
        self.assertEqual(mock_cache.set.call_args.args[0], EGRESS_CACHE_KEY)
        self.assertLessEqual(mock_cache.set.call_args.args[2], 30)

    def test_cached_result_skips_network(self, mock_run, mock_cache):
        mock_cache.get.return_value = {"ip": "203.0.113.8", "status": "ok"}

        self.assertEqual(get_egress_network(), mock_cache.get.return_value)
        mock_run.assert_not_called()


class EgressJsonParsingTests(SimpleTestCase):
    def test_rejects_unusable_json_and_provider_errors(self):
        for raw in ("not json", "null", "[]", '{"success": false, "ip": "203.0.113.8"}'):
            with self.subTest(raw=raw):
                self.assertEqual(parse_ipwhois_output(raw)["ip"], "")

    def test_tolerates_missing_geo_fields(self):
        parsed = parse_ipwhois_output('{"ip": "2001:db8::1", "success": true}')

        self.assertEqual(parsed["ip"], "2001:db8::1")
        self.assertEqual(parsed["location"], "")
        self.assertEqual(parsed["isp"], "")
