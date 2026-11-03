import json
from unittest.mock import Mock, patch
from urllib.error import URLError

from django.test import SimpleTestCase

from .dashboard import EGRESS_CACHE_KEY, get_egress_network, parse_ipwhois_output


@patch("system_management.dashboard.cache")
@patch("system_management.dashboard.urlopen")
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

    def test_falls_back_after_timeout(self, mock_urlopen, mock_cache):
        mock_cache.get.return_value = None
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = self.fallback.encode()
        mock_urlopen.side_effect = [
            TimeoutError("operation timed out"),
            response,
        ]

        payload = get_egress_network()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["ip"], "203.0.113.8")
        self.assertEqual(payload["location"], "中国 江苏 南京")
        self.assertEqual(payload["isp"], "电信")
        self.assertEqual(payload["error"], "")
        self.assertEqual(mock_urlopen.call_args.args[0], "https://ipwho.is/")
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 5)

    def test_falls_back_after_http_error(self, mock_urlopen, mock_cache):
        mock_cache.get.return_value = None
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = self.fallback.encode()
        mock_urlopen.side_effect = [URLError("HTTP 403"), response]

        self.assertEqual(get_egress_network()["status"], "ok")

    def test_falls_back_after_html_or_invalid_ip_response(self, mock_urlopen, mock_cache):
        mock_cache.get.return_value = None
        for response in ("<html>blocked</html>", "IP: unavailable"):
            with self.subTest(response=response):
                primary, fallback = mocked_responses(response, self.fallback)
                mock_urlopen.side_effect = [primary, fallback]

                self.assertEqual(get_egress_network()["ip"], "203.0.113.8")

    def test_successful_primary_does_not_request_fallback(self, mock_urlopen, mock_cache):
        mock_cache.get.return_value = None
        mock_urlopen.return_value = mocked_response("IP: 203.0.113.7\n地址: 中国")

        self.assertEqual(get_egress_network()["ip"], "203.0.113.7")
        mock_urlopen.assert_called_once()

    def test_all_sources_failed_are_cached_briefly(self, mock_urlopen, mock_cache):
        mock_cache.get.return_value = None
        mock_urlopen.side_effect = TimeoutError("operation timed out")

        payload = get_egress_network()

        self.assertEqual(payload["status"], "error")
        self.assertIn("timed out", payload["error"])
        self.assertEqual(mock_cache.set.call_args.args[0], EGRESS_CACHE_KEY)
        self.assertLessEqual(mock_cache.set.call_args.args[2], 30)

    def test_cached_result_skips_network(self, mock_urlopen, mock_cache):
        mock_cache.get.return_value = {"ip": "203.0.113.8", "status": "ok"}

        self.assertEqual(get_egress_network(), mock_cache.get.return_value)
        mock_urlopen.assert_not_called()


def mocked_response(content):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = content.encode()
    return response


def mocked_responses(primary, fallback):
    return mocked_response(primary), mocked_response(fallback)


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
