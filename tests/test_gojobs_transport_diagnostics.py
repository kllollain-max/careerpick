"""Regression checks for credential-safe GOJOBS transport diagnostics."""
import socket
import ssl
import unittest
import urllib.error
from unittest.mock import Mock

import gojobs


class TransportDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.client = gojobs.Client("dummy-test-key")
        self.client._opener = Mock()

    def assert_transport_code(self, exception, expected):
        self.client._opener.open.side_effect = exception
        with self.assertRaises(gojobs.APIError) as caught:
            self.client._request("list", {"pageNo": 1})
        self.assertEqual(caught.exception.safe_code, expected)
        self.assertNotIn("dummy-test-key", str(caught.exception))

    def test_timeout(self):
        self.assert_transport_code(urllib.error.URLError(socket.timeout("secret value")), "transport_timeout")

    def test_dns(self):
        self.assert_transport_code(urllib.error.URLError(socket.gaierror(-2, "secret value")), "transport_dns_error")

    def test_tls(self):
        self.assert_transport_code(urllib.error.URLError(ssl.SSLError("secret value")), "transport_tls_error")

    def test_connection(self):
        self.assert_transport_code(urllib.error.URLError(ConnectionRefusedError("secret value")), "transport_connection_error")

    def test_other_url_error(self):
        self.assert_transport_code(urllib.error.URLError("secret value"), "transport_error")

    def test_direct_timeout(self):
        self.assert_transport_code(socket.timeout("secret value"), "transport_timeout")


if __name__ == "__main__":
    unittest.main()
