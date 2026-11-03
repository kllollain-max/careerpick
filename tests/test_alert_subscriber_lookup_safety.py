"""Offline checks for strict OneSignal subscriber lookup safety."""
import os
import unittest
from unittest.mock import patch
from urllib.error import URLError

from scripts.onesignal_known_subscriber import lookup


class SubscriberLookupSafetyTests(unittest.TestCase):
    def test_invalid_uuid_never_calls_network(self):
        with self.assertRaises(ValueError):
            lookup("1234", opener=lambda *a, **k: self.fail("network used"))

    def test_network_failure_does_not_expose_credentials(self):
        def fail(req, timeout):
            raise URLError("secret-api-token")
        with patch.dict(os.environ, {
            "CP_ONESIGNAL_APP_ID": "31443bc9-bef0-4519-9817-2f916a548b6a",
            "CP_ONESIGNAL_REST_API_KEY": "secret-api-token",
        }):
            with self.assertRaises(RuntimeError) as caught:
                lookup("11111111-1111-4111-8111-111111111111", opener=fail)
        self.assertNotIn("secret-api-token", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
