"""Offline safety checks for guarded OneSignal transport."""
import os
import io
import json
import unittest
import uuid
from urllib.error import HTTPError, URLError
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
        for job_id in ("../other", "a123?redirect=evil", "custom-job",
                       "cleaneye-123?redirect=evil", "cleaneye-../other", "cleaneye-"):
            with self.subTest(job_id=job_id):
                payload = build_payload(
                    {"id": job_id, "title": "채용"}, "sub-001", "app-001")
                self.assertEqual(payload["url"], "https://kllollain-max.github.io/careerpick/")

    def test_cleaneye_push_opens_supported_detail_anchor(self):
        payload = build_payload({"id": "cleaneye-14377", "title": "채용",
                                 "url": "https://invalid.example/"}, "sub-001", "app-001")
        self.assertEqual(payload["url"],
                         "https://kllollain-max.github.io/careerpick/#job=cleaneye-14377")

    def test_idempotency_uuid_is_stable_for_the_same_logical_delivery(self):
        first = build_payload(JOB, "sub-001", "app-001")["idempotency_key"]
        edited = build_payload(dict(JOB, title="수정된 제목", due="2030-01-01"),
                               "sub-001", "app-001")["idempotency_key"]
        self.assertEqual(first, edited)
        self.assertEqual(str(uuid.UUID(first)), first)
        self.assertEqual(uuid.UUID(first).version, 5)
        self.assertNotIn("sub-001", first)

    def test_distinct_delivery_scope_never_reuses_idempotency_key(self):
        payloads = [build_payload(JOB, "sub-001", "app-001"),
                    build_payload(dict(JOB, id="job-002"), "sub-001", "app-001"),
                    build_payload(JOB, "sub-002", "app-001"),
                    build_payload(JOB, "sub-001", "app-002"),
                    build_payload(JOB, "sub-001", "app-001", test=True)]
        self.assertEqual(len({payload["idempotency_key"] for payload in payloads}), 5)

    def test_transport_429_retry_keeps_identical_idempotency_key(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.read.return_value = b'{"id":"fixture-notification","recipients":1}'
        response.__enter__.return_value = response
        limited = HTTPError("https://api.onesignal.com/notifications", 429,
                            "limited", {"Retry-After": "0"}, io.BytesIO(b"{}"))
        with patch.dict(os.environ, {"CP_ONESIGNAL_APP_ID": "app-001",
                                     "CP_ONESIGNAL_REST_API_KEY": "fixture-key",
                                     "CP_ENABLE_LIVE_PUSH": "1"}, clear=True), \
                patch("scripts.onesignal_guarded_transport.urlopen", side_effect=[limited, response]) as network:
            self.assertTrue(send(JOB, "sub-001", verified_opt_in=True, live=True)["sent"])
        self.assertEqual(network.call_count, 2)
        bodies = [json.loads(call.args[0].data) for call in network.call_args_list]
        self.assertEqual(bodies[0]["idempotency_key"], bodies[1]["idempotency_key"])
        self.assertEqual(bodies[0]["include_subscription_ids"], ["sub-001"])

    def test_idempotency_does_not_enable_uncertain_delivery_replay(self):
        with patch.dict(os.environ, {"CP_ONESIGNAL_APP_ID": "app-001",
                                     "CP_ONESIGNAL_REST_API_KEY": "fixture-key",
                                     "CP_ENABLE_LIVE_PUSH": "1"}, clear=True), \
                patch("scripts.onesignal_guarded_transport.urlopen", side_effect=URLError("fixture-private")) as network:
            with self.assertRaisesRegex(RuntimeError, 'outcome uncertain; no blind retry'):
                send(JOB, "sub-001", verified_opt_in=True, live=True)
        self.assertEqual(network.call_count, 1)

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
