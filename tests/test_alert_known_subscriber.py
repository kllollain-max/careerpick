"""Network-isolated tests for OneSignal known-subscription lookup."""
import io
import json
import os
import unittest
from unittest.mock import patch
from scripts.onesignal_known_subscriber import lookup


class Response:
    def __init__(self, payload):
        self.stream = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stream.close()

    def read(self, limit):
        return self.stream.read(limit)


class KnownSubscriberTests(unittest.TestCase):
    def test_authorized_single_lookup(self):
        response = {"subscriptions": [{"id": "11111111-1111-4111-8111-111111111111", "enabled": True,
                                       "type": "ChromePush"}],
                    "properties": {"tags": {"cp_optin": "yes"}}}
        requests = []
        payloads = [{"identity": {"onesignal_id": "user-123"}}, response]
        def opener(request, timeout):
            requests.append(request)
            return Response(payloads[len(requests) - 1])
        with patch.dict(os.environ, {"CP_ONESIGNAL_APP_ID": "app-123",
                                     "CP_ONESIGNAL_REST_API_KEY": "fake-test-key"}):
            subscriber = lookup("11111111-1111-4111-8111-111111111111", opener=opener)
        self.assertEqual(subscriber["subscription_id"], "11111111-1111-4111-8111-111111111111")
        self.assertEqual(len(requests), 2)
        self.assertIn("/subscriptions/11111111-1111-4111-8111-111111111111/user/identity",
                      requests[0].full_url)
        self.assertIn("/users/by/onesignal_id/user-123", requests[1].full_url)
        self.assertTrue(all(req.get_method() == "GET" for req in requests))

    def test_missing_credentials_prevents_network(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                lookup("11111111-1111-4111-8111-111111111111", opener=lambda *a, **kw: self.fail("network used"))

    def test_bad_id_prevents_network(self):
        with self.assertRaises(ValueError):
            lookup("../users", opener=lambda *a, **kw: self.fail("network used"))


if __name__ == "__main__":
    unittest.main()
