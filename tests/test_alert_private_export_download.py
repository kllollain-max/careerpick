import gzip
import io
import unittest
from unittest.mock import Mock, patch

from scripts.private_onesignal_export_download import (
    read_export_ids, validate_export_url, MAX_COMPRESSED_BYTES,
)

SID = "717d8568-c258-4676-8761-81aa526a1a8f"


def fake_opener(data):
    response = Mock()
    response.read.return_value = data
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return lambda request, timeout: response


class PrivateExportDownloadTests(unittest.TestCase):
    def test_valid_gzip_export(self):
        raw = ("subscription_id\\n" + SID + "\\n").replace("\\n", "\n").encode()
        ids = read_export_ids("https://files.onesignal.com/export.csv.gz",
                              opener=fake_opener(gzip.compress(raw)))
        self.assertEqual(ids, [SID])

    def test_reject_untrusted_or_insecure_urls(self):
        for url in ("http://files.onesignal.com/x",
                    "https://onesignal.com.evil.test/x",
                    "https://127.0.0.1/x",
                    "https://evil.test/x"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_export_url(url)

    def test_reject_arbitrary_cloud_bucket_even_if_https(self):
        with self.assertRaises(ValueError):
            validate_export_url("https://attacker-bucket.s3.amazonaws.com/private.csv")

    def test_explicit_configured_host_is_allowed_only_exactly(self):
        with patch.dict("os.environ", {"CP_PRIVATE_EXPORT_HOST": "trusted-bucket.s3.amazonaws.com"}):
            self.assertEqual(
                validate_export_url("https://trusted-bucket.s3.amazonaws.com/export.csv"),
                "https://trusted-bucket.s3.amazonaws.com/export.csv")
            with self.assertRaises(ValueError):
                validate_export_url("https://evil.trusted-bucket.s3.amazonaws.com/export.csv")

    def test_reject_unconfigured_cloud_host_independent_of_environment(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                validate_export_url("https://attacker-bucket.s3.amazonaws.com/private.csv")

    def test_rejected_cloud_host_diagnostic_does_not_leak_bucket(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError) as caught:
                validate_export_url("https://private-user-bucket.s3.amazonaws.com/x?token=secret")
        self.assertIn("aws-s3", str(caught.exception))
        self.assertNotIn("private-user-bucket", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_allow_onesignal_owned_subdomain_only(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                validate_export_url("https://private-export.onesignal.com/data.csv.gz"),
                "https://private-export.onesignal.com/data.csv.gz")
            for url in ("https://onesignal.com.evil.example/x",
                        "https://fakeonesignal.com/x",
                        "http://private-export.onesignal.com/x"):
                with self.subTest(url=url):
                    with self.assertRaises(ValueError):
                        validate_export_url(url)

    def test_temporary_404_then_ready(self):
        from urllib.error import HTTPError
        from unittest.mock import Mock
        raw = ("subscription_id\\n" + SID + "\\n").replace("\\n", "\n").encode()
        data = gzip.compress(raw)
        attempts = []
        def delayed(request, timeout):
            attempts.append(1)
            if len(attempts) < 3:
                raise HTTPError(request.full_url, 404, "Not Found", {}, None)
            response = Mock()
            response.read.return_value = data
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            return response
        self.assertEqual(read_export_ids("https://files.onesignal.com/export.gz",
                                         opener=delayed, sleeper=lambda seconds: None), [SID])
        self.assertEqual(len(attempts), 3)

    def test_permanent_404_fails_after_bounded_checks(self):
        from urllib.error import HTTPError
        calls = []
        def missing(request, timeout):
            calls.append(1)
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)
        with self.assertRaisesRegex(RuntimeError, "not ready"):
            read_export_ids("https://files.onesignal.com/export.gz",
                            opener=missing, sleeper=lambda seconds: None)
        self.assertEqual(len(calls), 4)

    def test_reject_oversized_compressed_payload(self):
        with self.assertRaises(ValueError):
            read_export_ids("https://files.onesignal.com/x",
                            opener=fake_opener(b"x" * (MAX_COMPRESSED_BYTES + 1)))


if __name__ == "__main__":
    unittest.main()
