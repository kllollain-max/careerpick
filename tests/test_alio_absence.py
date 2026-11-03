import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import alio
from data_go_kr import APIError
from scripts.audit_alio_absent import audit


class FakeClient:
    details = {"2": {"recrutPblntSn": 2, "ongoingYn": None, "pbancEndYmd": "20261130", "files": [], "steps": []}}
    def __init__(self, key):
        self.request_counts = {"list": 0, "detail": 0}
        self.success_counts = {"list": 0, "detail": 0}
    def collect_list(self):
        self.request_counts["list"] += 1
        self.success_counts["list"] += 1
        return [{"recrutPblntSn": 1}]
    def detail(self, sn):
        self.request_counts["detail"] += 1
        value = self.details[sn]
        if isinstance(value, Exception):
            raise value
        self.success_counts["detail"] += 1
        return value


class AbsenceAuditTest(unittest.TestCase):
    def run_case(self, detail, extra=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            posts = [{"id": "a"+str(i), "title": "공고", "org": "기관", "due": "2026-11-30T23:59:00+09:00",
                      "url": "https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx="+str(i)}
                     for i in range(1, 3+extra)]
            (root/"alio.json").write_text(json.dumps({"posts": posts}))
            (root/"alio-detail.json").write_text("{}")
            originals = {n:(root/n).read_bytes() for n in ("alio.json", "alio-detail.json")}
            class FixtureClient(FakeClient):
                details = {"2": detail}
            report = audit(root, key="private-api-credential", client_factory=FixtureClient,
                           now=datetime(2026,11,3,14,tzinfo=alio.KST))
            self.assertTrue(report["source_preserved"])
            self.assertEqual(originals, {n:(root/n).read_bytes() for n in originals})
            return report
    def test_missing_list_and_null_status_never_mean_closed(self):
        report = self.run_case(FakeClient.details["2"])
        self.assertEqual(report["confirmed_not_ongoing"], 0)
        self.assertEqual(report["unresolved"], 1)
        self.assertEqual(report["reviews"][0]["classification"], "unresolved")
    def test_no_detail_does_not_mean_closed(self):
        report = self.run_case(APIError("api_result_3"))
        self.assertEqual(report["confirmed_not_ongoing"], 0)
        self.assertEqual(report["reviews"][0]["detail_status"], "no_data")
    def test_unrecognized_individual_response_is_preserved_as_unresolved(self):
        report = self.run_case(APIError("unexpected_envelope_fields"))
        self.assertEqual(report["status"], "reviewed")
        self.assertEqual(report["confirmed_not_ongoing"], 0)
        self.assertEqual(report["reviews"][0]["detail_status"], "unverified_response")
    def test_explicit_official_status_is_distinct_from_absence(self):
        report = self.run_case({**FakeClient.details["2"], "ongoingYn": "N"})
        self.assertEqual(report["confirmed_not_ongoing"], 1)
        self.assertEqual(report["reviews"][0]["classification"], "official_not_ongoing")
    def test_official_revised_past_deadline_is_confirmed(self):
        report = self.run_case({**FakeClient.details["2"], "pbancEndYmd": "20261102"})
        self.assertEqual(report["reviews"][0]["classification"], "official_deadline_elapsed")
    def test_bounded_review_does_not_expand_detail_requests(self):
        report = self.run_case(FakeClient.details["2"], extra=10)
        self.assertEqual(report["status"], "review_limit_preserved")
        self.assertEqual(report["requests"], {"list": 1, "detail": 0})


if __name__ == "__main__":
    unittest.main()
