"""One exact GSIPA employer notice, never an arbitrary .kr allowlist."""
import hashlib
import unittest
from unittest.mock import patch
from scripts.threads_reviewed_ingest import (
    GSIPA_81201_PDF, GSIPA_81201_NOTICE,
    official_url_allowed, fetch_official_digest,
)


class FakeHTTP:
    status = 200
    def __init__(self, data):
        self.data = data
    def read(self, limit=-1):
        return self.data[:limit] if limit >= 0 else self.data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
    def open(self, req, timeout):
        self.calls.append(req.full_url)
        if req.full_url == GSIPA_81201_NOTICE:
            return FakeHTTP(b'<html>official notice</html>')
        if req.full_url == GSIPA_81201_PDF:
            return FakeHTTP(self.payload)
        raise AssertionError('Unexpected URL: '+req.full_url)


class GSIPAExactSourceTest(unittest.TestCase):
    def test_exact_urls_only(self):
        self.assertTrue(official_url_allowed(GSIPA_81201_NOTICE))
        self.assertTrue(official_url_allowed(GSIPA_81201_PDF))
        self.assertFalse(official_url_allowed('https://www.gsipa.kr/board/bbs/download.php?bo_table=recruit&wr_id=249&no=0'))
        self.assertFalse(official_url_allowed('https://www.gsipa.kr/board/bbs/download.php?bo_table=recruit&no=1&wr_id=248'))
        self.assertFalse(official_url_allowed('http://www.gsipa.kr/board/bbs/download.php?bo_table=recruit&no=0&wr_id=248'))
        self.assertFalse(official_url_allowed('https://www.gsipa.kr.evil.example/board/bbs/download.php?bo_table=recruit&no=0&wr_id=248'))

    def test_reads_notice_before_attachment(self):
        pdf = b'%PDF-1.7' + b'\n' + b'a' * 900
        sess = FakeSession(pdf)
        with patch('scripts.threads_reviewed_ingest.urllib.request.build_opener', return_value=sess):
            got = fetch_official_digest(GSIPA_81201_PDF)
        self.assertEqual(got, hashlib.sha256(pdf).hexdigest())
        self.assertEqual(sess.calls, [GSIPA_81201_NOTICE, GSIPA_81201_PDF])

    def test_html_gate_must_fail_closed(self):
        sess = FakeSession(b'<html>access denied</html>')
        with patch('scripts.threads_reviewed_ingest.urllib.request.build_opener', return_value=sess):
            with self.assertRaisesRegex(ValueError, 'OFFICIAL_SOURCE_NOT_PDF'):
                fetch_official_digest(GSIPA_81201_PDF)


if __name__ == '__main__':
    unittest.main()
