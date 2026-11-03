"""Fail-closed validation tests for OneSignal View User responses."""
import unittest
from scripts.onesignal_subscriber_validation import verified_subscriber

BASE = {"subscriptions": [{"id": "sub-1", "enabled": True, "type": "ChromePush"}],
        "properties": {"tags": {"cp_optin": "yes", "cp_profile": "{}"}}}


class SubscriberValidationTests(unittest.TestCase):
    def test_valid_web_push(self):
        self.assertEqual(verified_subscriber(BASE, "sub-1")["subscription_id"], "sub-1")

    def test_opted_out_rejected(self):
        response = {**BASE, "properties": {"tags": {"cp_optin": "no"}}}
        self.assertIsNone(verified_subscriber(response, "sub-1"))

    def test_disabled_rejected(self):
        response = {**BASE, "subscriptions": [{"id": "sub-1", "enabled": False,
                                                "type": "ChromePush"}]}
        self.assertIsNone(verified_subscriber(response, "sub-1"))

    def test_wrong_id_rejected(self):
        self.assertIsNone(verified_subscriber(BASE, "sub-2"))

    def test_email_subscription_rejected(self):
        response = {**BASE, "subscriptions": [{"id": "sub-1", "enabled": True,
                                                "type": "Email"}]}
        self.assertIsNone(verified_subscriber(response, "sub-1"))

    def test_malformed_response_rejected(self):
        self.assertIsNone(verified_subscriber({"subscriptions": "invalid"}, "sub-1"))


if __name__ == "__main__":
    unittest.main()
