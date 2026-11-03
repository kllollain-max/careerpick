import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import alio
from data_go_kr import APIError
from scripts.verify_data_go_kr_live import verify


NOW = datetime(2026, 11, 3, 13, 0, tzinfo=alio.KST)


def notice(sn, title="채용 공고"):
    return {
        "recrutPblntSn": sn, "recrutPbancTtl": title, "instNm": "검증 기관",
        "pbancBgngYmd": "20261101", "pbancEndYmd": "20261130",
        "hireTypeNmLst": ["정규직"], "files": [], "steps": [],
    }


class FakeClient:
    def __init__(self, key):
        self.request_counts = {"list": 0, "detail": 0}
        self.success_counts = {"list": 0, "detail": 0}

    def collect_list(self):
        self.request_counts["list"] += 1
        self.success_counts["list"] += 1
        return [notice(101, "수정 공고"), notice(102)]

    def detail(self, sn):
        self.request_counts["detail"] += 1
        self.success_counts["detail"] += 1
        return {**notice(int(sn)), "files": [{"url": "https://job.alio.go.kr/test.pdf"}],
                "steps": [{"recrutStepSn": 1}]}


class LiveCandidateTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        posts = [alio.convert(notice(101), NOW)]
        (self.root / "alio.json").write_text(json.dumps({
            "updated": "2026-11-01T00:00:00+09:00", "posts": posts
        }))
        (self.root / "alio-detail.json").write_text(json.dumps({
            "a101": {**alio.detail_of(notice(101)), "retainedField": "preserve"}
        }))
        self.originals = {n: (self.root / n).read_bytes() for n in ("alio.json", "alio-detail.json")}
        self.output = self.root / "output"

    def tearDown(self):
        self.directory.cleanup()

    def assert_originals_preserved(self):
        self.assertEqual(self.originals, {n: (self.root / n).read_bytes() for n in self.originals})

    def test_success_retains_originals_and_sample_attachments(self):
        report = verify(self.root, self.output, key="test-key-not-in-response", client_factory=FakeClient, now=NOW)
        self.assertEqual(report["status"], "verified_candidate")
        self.assertEqual((report["before"], report["after"], report["added"], report["changed"]), (1, 2, 1, 1))
        self.assertEqual(report["requests"], {"list": 1, "detail": 2})
        self.assertEqual(report["detail_scope"], "sample_only")
        self.assertIsNone(report["official_closed_verified"])
        self.assertTrue(report["source_preserved"])
        sample = json.loads((self.output / "candidate/detail-samples.json").read_text())
        self.assertEqual(len(sample["a101"]["files"]), 1)
        self.assertEqual(len(sample["a101"]["steps"]), 1)
        details = json.loads((self.output / "candidate/alio-detail.json").read_text())
        self.assertEqual(details["a101"]["retainedField"], "preserve")
        self.assert_originals_preserved()

    def test_detail_failure_does_not_create_candidate(self):
        class FailedClient(FakeClient):
            def detail(self, sn):
                self.request_counts["detail"] += 1
                raise APIError("detail_identity_mismatch")
        report = verify(self.root, self.output, key="test-key-not-in-response", client_factory=FailedClient, now=NOW)
        self.assertEqual(report["status"], "blocked_or_failed_preserved")
        self.assertFalse((self.output / "candidate").exists())
        self.assertEqual(report["requests"], {"list": 1, "detail": 1})
        self.assert_originals_preserved()

    def test_missing_key_makes_no_request(self):
        def forbid_client(key):
            self.fail("Client must not be constructed without a key")
        report = verify(self.root, self.output, key="", client_factory=forbid_client, now=NOW)
        self.assertEqual(report["reason"], "blocked_missing_secret")
        self.assertEqual(report["requests"], {"list": 0, "detail": 0})
        self.assertFalse((self.output / "candidate").exists())
        self.assert_originals_preserved()

    def test_credential_echo_blocks_all_candidate_files(self):
        class EchoClient(FakeClient):
            def detail(self, sn):
                return {**super().detail(sn), "message": "do-not-export-this-key"}
        report = verify(self.root, self.output, key="do-not-export-this-key", client_factory=EchoClient, now=NOW)
        self.assertEqual(report["reason"], "credential_in_response_rejected")
        self.assertFalse((self.output / "candidate").exists())
        self.assertNotIn("do-not-export-this-key", (self.output / "report.json").read_text())
        self.assert_originals_preserved()


if __name__ == "__main__":
    unittest.main()
