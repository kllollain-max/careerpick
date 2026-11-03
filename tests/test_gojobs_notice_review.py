import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from scripts import review_gojobs_notices as review

NOW = datetime(2026, 11, 3, 6, tzinfo=timezone.utc)
FIXTURE = Path(__file__).resolve().parents[1] / review.EVIDENCE_PATH


class NoticeReviewTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_actual_final_results_notice_is_excluded_with_future_api_deadline(self):
        records = review.triage(self.data, as_of="2026-11-03")
        current = next(row for row in records if row["id"] == "307403")
        self.assertTrue(current["source_integrity_verified"])
        self.assertFalse(current["api_deadline_elapsed"])
        self.assertEqual(current["decision"], "excluded_non_recruitment")
        self.assertFalse(current["new_application_eligible"])
        self.assertFalse(current["official_source_verified"])
        self.assertEqual(len(records), 6)
        self.assertFalse(any(row["new_application_eligible"] for row in records))

    def test_failed_source_and_missing_detail_cannot_be_promoted_by_title(self):
        rows = {row["id"]: row for row in review.triage(self.data, as_of="2026-11-03")}
        self.assertEqual(rows["20"]["decision"], "blocked_source_integrity")
        self.assertFalse(rows["20"]["source_integrity_verified"])
        self.assertEqual(rows["42"]["reason"], "detail_unverified")
        self.assertEqual(rows["45"]["reason"], "detail_unverified")

    def test_historical_api_dates_are_not_reported_as_verified_application_closure(self):
        rows = {row["id"]: row for row in review.triage(self.data, as_of="2026-11-03")}
        for identity in ("4", "7"):
            with self.subTest(identity=identity):
                self.assertTrue(rows[identity]["source_integrity_verified"])
                self.assertTrue(rows[identity]["api_deadline_elapsed"])
                self.assertEqual(rows[identity]["classification"]["category"], "상태 미확인")
                self.assertEqual(rows[identity]["decision"], "needs_review")
                self.assertFalse(rows[identity]["application_period_verified"])

    def test_mismatched_detail_is_kept_outside_verified_candidates(self):
        result = self.data["last_page_experiment"]["report"]["result"]
        result["detail_samples"][0]["title"] = "다른 채용 공고"
        row = review.triage(self.data, as_of="2026-11-03")[-1]
        self.assertEqual(row["decision"], "blocked_source_integrity")
        self.assertFalse(row["new_application_eligible"])

    def test_untrusted_evidence_status_flags_do_not_become_official_verification(self):
        result = self.data["last_page_experiment"]["report"]["result"]
        for row in (result["samples"][0], result["detail_samples"][0]):
            row["title"] = "공무원 채용 공고"
            row["official_verified"] = True
            row["application_open_verified"] = True
        row = review.triage(self.data, as_of="2026-11-03")[-1]
        self.assertEqual(row["decision"], "needs_review")
        self.assertFalse(row["official_source_verified"])
        self.assertFalse(row["new_application_eligible"])

    def test_inconsistent_records_fail_review_without_guessing(self):
        for mutation in ("duplicate", "bad_date", "unverified"):
            data = copy.deepcopy(self.data)
            report = data["last_page_experiment"]["report"]
            result = report["result"]
            if mutation == "duplicate":
                result["samples"].append(copy.deepcopy(result["samples"][0]))
                result["list_count_returned"] = 2
            elif mutation == "bad_date":
                result["samples"][0]["deadline"] = "2026-99-99"
            else:
                report["authentication_verified"] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                review.triage(data, as_of="2026-11-03")

    def test_classifier_cannot_accidentally_promote_unverified_records(self):
        with mock.patch.object(review, "classify_notice", return_value={"recruiting": True}), self.assertRaisesRegex(ValueError, "unsafe_unverified_candidate_promotion"):
            review.triage(self.data, as_of="2026-11-03")

    def test_offline_report_preserves_source_and_input_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "alio.json").write_text('{"posts":[{"id":"a1"}]}')
            (root / "alio-detail.json").write_text('{"a1":{"title":"existing"}}')
            (root / review.EVIDENCE_PATH).parent.mkdir(parents=True)
            (root / review.EVIDENCE_PATH).write_bytes(FIXTURE.read_bytes())
            paths = [root / path for path in (*review.SOURCE_PATHS, review.EVIDENCE_PATH)]
            before = {path: path.read_bytes() for path in paths}
            result = review.review(root, now=NOW)
            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["api_requests"], 0)
            self.assertEqual(result["new_application_candidate_count"], 0)
            self.assertEqual(result["source_count_before"], result["source_count_after"])
            self.assertEqual(before, {path: path.read_bytes() for path in paths})
            self.assertTrue((root / "gojobs-notice-review-output" / "report.json").is_file())


if __name__ == "__main__":
    unittest.main()
