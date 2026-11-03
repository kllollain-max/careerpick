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
