"""Offline safety checks for guarded OneSignal transport."""
import os
import unittest
from unittest.mock import patch
from scripts.onesignal_guarded_transport import build_payload, send


JOB = {"id": "job-001", "title": "전산직", "org": "테스트기관"}


class GuardedTransportTests(unittest.TestCase):
    def test_payload_targets_only_one_subscription(self):
        payload = build_payload(JOB, "sub-001", "app-001")
        self.assertEqual(payload["include_subscription_ids"], ["sub-001"])
        self.assertEqual(payload["target_channel"], "push")
        self.assertEqual(payload["contents"]["en"], payload["contents"]["ko"])
        self.assertEqual(payload["headings"]["en"], payload["headings"]["ko"])
        self.assertNotIn("included_segments", payload)

    def test_alio_push_opens_exact_job_page(self):
        job = {"id": "a123456", "title": "채용", "org": "기관"}
        payload = build_payload(job, "sub-001", "app-001")
        self.assertEqual(payload["url"],
                         "https://kllollain-max.github.io/careerpick/jobs/a123456.html")

    def test_non_alio_or_unsafe_id_falls_back_to_homepage(self):
        for job_id in ("../other", "a123?redirect=evil", "custom-job"):
            with self.subTest(job_id=job_id):
                payload = build_payload(
                    {"id": job_id, "title": "채용"}, "sub-001", "app-001")
                self.assertEqual(payload["url"], "https://kllollain-max.github.io/careerpick/")

    def test_no_consent_blocks_even_dry_run(self):
        with patch.dict(os.environ, {"CP_ONESIGNAL_APP_ID": "app-001"}):
            with self.assertRaises(ValueError):
                send(JOB, "sub-001", verified_opt_in=False)

    def test_default_mode_never_calls_network(self):
        with patch.dict(os.environ, {"CP_ONESIGNAL_APP_ID": "app-001",
                                     "CP_ENABLE_LIVE_PUSH": "0"}, clear=True):
            with patch("scripts.onesignal_guarded_transport.urlopen") as network:
                result = send(JOB, "sub-001", verified_opt_in=True)
                self.assertFalse(result["sent"])
                network.assert_not_called()

    def test_live_requires_both_flags_and_credentials(self):
        with patch.dict(os.environ, {"CP_ONESIGNAL_APP_ID": "app-001",
                                     "CP_ENABLE_LIVE_PUSH": "1"}, clear=True):
            with self.assertRaises(ValueError):
                send(JOB, "sub-001", verified_opt_in=True, live=True)

    def test_zero_recipients_does_not_mark_send_accepted(self):
        import json
        from unittest.mock import MagicMock

        response = MagicMock()
        response.read.return_value = json.dumps({
            "id": "notification-test", "recipients": 0
        }).encode("utf-8")
        response.__enter__.return_value = response
        with patch.dict(os.environ, {
            "CP_ONESIGNAL_APP_ID": "app-001",
            "CP_ONESIGNAL_REST_API_KEY": "test-key",
            "CP_ENABLE_LIVE_PUSH": "1",
        }, clear=True):
            with patch("scripts.onesignal_guarded_transport.urlopen", return_value=response):
                result = send(JOB, "sub-001", verified_opt_in=True, live=True)
        self.assertFalse(result["sent"])
        self.assertIsNone(result["notification_id"])

    def test_positive_recipients_acceptance_is_not_device_delivery(self):
        import json
        from unittest.mock import MagicMock

        response = MagicMock()
        response.read.return_value = json.dumps({
            "id": "notification-test", "recipients": 1
        }).encode("utf-8")
        response.__enter__.return_value = response
        with patch.dict(os.environ, {
            "CP_ONESIGNAL_APP_ID": "app-001",
            "CP_ONESIGNAL_REST_API_KEY": "test-key",
            "CP_ENABLE_LIVE_PUSH": "1",
        }, clear=True):
            with patch("scripts.onesignal_guarded_transport.urlopen", return_value=response):
                result = send(JOB, "sub-001", verified_opt_in=True, live=True)
        self.assertTrue(result["sent"])
        self.assertEqual(result["notification_id"], "notification-test")

    def test_http_400_redacts_upstream_values(self):
        import io
        from urllib.error import HTTPError
        body = b'{"errors":[{"include_subscription_ids":"sensitive-sub-id","token":"secret"}]}'
        error = HTTPError("https://api.onesignal.com/notifications", 400,
                          "Bad Request", {}, io.BytesIO(body))
        with patch.dict(os.environ, {
            "CP_ONESIGNAL_APP_ID": "app-001",
            "CP_ONESIGNAL_REST_API_KEY": "test-key",
            "CP_ENABLE_LIVE_PUSH": "1",
        }, clear=True):
            with patch("scripts.onesignal_guarded_transport.urlopen", side_effect=error):
                with self.assertRaises(RuntimeError) as caught:
                    send(JOB, "sub-001", verified_opt_in=True, live=True)
        message = str(caught.exception)
        self.assertIn("HTTP 400", message)
        self.assertIn("include_subscription_ids", message)
        self.assertNotIn("sensitive-sub-id", message)
        self.assertNotIn("secret", message)

    def test_invalid_target_rejected(self):
        with self.assertRaises(ValueError):
            build_payload(JOB, "", "app-001")


if __name__ == "__main__":
    unittest.main()
