import io
import unittest
from urllib.error import HTTPError, URLError
from scripts.onesignal_safe_retry import post, delay


class Response:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return b'{"id":"synthetic-id","recipients":1}'


class RetryTests(unittest.TestCase):
    def test_429_retry_after(self):
        calls = []
        def opener(request, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise HTTPError("https://api.onesignal.com", 429, "rate", {"Retry-After":"2"}, io.BytesIO(b""))
            return Response()
        sleeps = []
        result = post(object(), opener=opener, sleeper=sleeps.append)
        self.assertEqual(result["recipients"], 1)
        self.assertEqual(len(calls), 2)
        self.assertGreaterEqual(sleeps[0], 2)

    def test_server_error_never_replayed(self):
        for code in (500, 502, 503, 504):
            count = []
            def opener(request, timeout):
                count.append(1)
                raise HTTPError("https://api.onesignal.com", code, "server", {}, io.BytesIO(b""))
            with self.assertRaisesRegex(RuntimeError, "uncertain"):
                post(object(), opener=opener, sleeper=lambda n: None)
            self.assertEqual(len(count), 1)

    def test_lost_response_never_replayed(self):
        count = []
        def opener(request, timeout):
            count.append(1)
            raise URLError("mock disconnect")
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            post(object(), opener=opener, sleeper=lambda n: None)
        self.assertEqual(len(count), 1)

    def test_retry_budget(self):
        calls = []
        def opener(request, timeout):
            calls.append(1)
            raise HTTPError("https://api.onesignal.com", 429, "rate", {}, io.BytesIO(b""))
        with self.assertRaisesRegex(RuntimeError, "exhausted"):
            post(object(), opener=opener, sleeper=lambda n: None, retries=2)
        self.assertEqual(len(calls), 3)

    def test_invalid_budget(self):
        with self.assertRaises(ValueError):
            post(object(), retries=4)

class IdempotencyTests(unittest.TestCase):
    def test_request_key_is_uuid_and_reused_for_rate_limit_retry(self):
        import json
        import uuid
        from urllib.request import Request
        from scripts.onesignal_guarded_transport import build_payload
        job = {"id": "a123", "title": "synthetic", "due": "2099-12-31"}
        one = build_payload(job, "synthetic-sub", "synthetic-app")
        other = build_payload(job, "synthetic-sub", "synthetic-app")
        self.assertEqual(uuid.UUID(one["idempotency_key"]).version, 4)
        self.assertNotEqual(one["idempotency_key"], other["idempotency_key"])
        request = Request("https://api.onesignal.com/notifications", data=json.dumps(one).encode())
        seen = []
        def opener(req, timeout):
            seen.append(json.loads(req.data)["idempotency_key"])
            if len(seen) == 1:
                raise HTTPError(req.full_url, 429, "rate", {}, io.BytesIO(b""))
            return Response()
        post(request, opener=opener, sleeper=lambda _: None)
        self.assertEqual(seen, [one["idempotency_key"], one["idempotency_key"]])
