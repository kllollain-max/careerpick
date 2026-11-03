import io
import json
import unittest
from unittest.mock import Mock

from scripts.private_onesignal_export_request import request_export

APP = "31443bc9-bef0-4519-9817-2f916a548b6a"


def opener(body, captured):
    response = Mock()
    response.read.return_value = body
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    def open_request(req, timeout):
        captured.append((req.get_method(), req.full_url, req.data))
        return response
    return open_request


class PrivateExportRequestTests(unittest.TestCase):
    def test_request_returns_only_validated_private_url(self):
        captured = []
        url = "https://files.onesignal.com/export.csv.gz"
        result = request_export(APP, "private-key", opener=opener(
            json.dumps({"csv_file_url": url}).encode(), captured))
        self.assertEqual(result, url)
        self.assertEqual(captured[0][0], "POST")
        self.assertIn("app_id=", captured[0][1])
        self.assertEqual(captured[0][2], b"{}")

    def test_missing_export_url_fails_closed(self):
        with self.assertRaises(ValueError):
            request_export(APP, "private-key", opener=opener(b"{}", []))

    def test_untrusted_export_url_fails_closed(self):
        with self.assertRaises(ValueError):
            request_export(APP, "private-key", opener=opener(
                b'{"csv_file_url":"https://evil.example/export.csv"}', []))

    def test_invalid_app_or_missing_key_never_calls_network(self):
        def forbidden(*args, **kwargs):
            self.fail("Unexpected request")
        with self.assertRaises(ValueError):
            request_export("invalid", "key", opener=forbidden)
        with self.assertRaises(ValueError):
            request_export(APP, "", opener=forbidden)


if __name__ == "__main__":
    unittest.main()
