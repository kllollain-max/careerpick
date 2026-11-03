import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import mpm_exam
from scripts import build_additional_api_candidate as candidate

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 3, 7, tzinfo=timezone.utc)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in (candidate.EXAM_PATH, candidate.MANIFEST_PATH, candidate.EVIDENCE_PATH):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        (self.root / "alio.json").write_text('{"posts":[{"id":"a1"}]}', encoding="utf-8")
        (self.root / "alio-detail.json").write_text('{"a1":{"title":"preserved"}}', encoding="utf-8")
        (self.root / "civil-service-exams.html").write_text('<html lang="ko">calendar</html>', encoding="utf-8")
        self.before = {name: (self.root / name).read_bytes() for name in candidate.PRESERVED}
        self.output = self.root / candidate.OUTPUT_NAME

    def snapshot(self):
        return json.loads((self.root / candidate.EXAM_PATH).read_text())

    def assert_preserved(self):
        self.assertEqual(self.before, {name: (self.root / name).read_bytes() for name in candidate.PRESERVED})

    def test_offline_candidate_has_complete_rows_and_preserves_source_timestamp_and_bytes(self):
        with mock.patch.object(mpm_exam, "Client", side_effect=AssertionError("offline must not create a client")):
            report = candidate.build(self.root, now=NOW)
        self.assert_preserved()
        result = json.loads((self.output / candidate.EXAM_PATH).read_text())
        self.assertEqual(result["count"], 28)
        self.assertEqual(len(result["records"]), 28)
        self.assertEqual(result["retrieved_at"], self.snapshot()["retrieved_at"])
        self.assertEqual(report["mpm_exam"]["distinct_exam_names"], 10)
        self.assertEqual(report["mpm_exam"]["structural_validation"]["date_cells_verified"], 107)
        self.assertEqual(
            report["mpm_exam"]["structural_validation"]["null_place_announcement_cells"],
            sum(row["시험장소공고일"] is None for row in self.snapshot()["records"]),
        )
        self.assertFalse(report["mpm_exam"]["authentication_retested"])
        self.assertEqual(report["api_requests"], {"gojobs": 0, "mpm_exam": 0})
        self.assertIn("2026-11-05~2026-11-06", [row["시험일"] for row in result["records"]])
        source_rows = json.loads((self.output / "mpm-source-records.json").read_text())["records"]
        self.assertEqual(source_rows, mpm_exam.validate_records(
            self.snapshot()["records"], expected_count=self.snapshot()["count"]
        )["records"])
        self.assertEqual(report["source_count_before"], report["source_count_after"])
        self.assertEqual(len([p for p in self.output.rglob("*") if p.is_file()]), 7)

    def test_all_adapter_date_formats_become_page_compatible_without_inventing_ranges(self):
        row = self.snapshot()["records"][0]
        row["시험일"] = "2026년 11월 5일~2026년 11월 6일"
        row["원서접수기간"] = "11.1.~11.3."
        row["합격자발표일"] = "2026.12.11."
        row["시험장소공고일"] = "미정"
        normalized = candidate.display_records([row])[0]
        self.assertEqual(normalized["시험일"], "2026-11-05~2026-11-06")
        self.assertEqual(normalized["원서접수기간"], "2026-11-01~2026-11-03")
        self.assertEqual(normalized["합격자발표일"], "2026-12-11")
        self.assertEqual(normalized["시험장소공고일"], "")
        self.assertEqual(row["시험일"], "2026년 11월 5일~2026년 11월 6일")
        for value in ("2026-11-01,2026-11-03,2026-11-05", "2026.5.1,2026.5.3", "2026-11-01/2026-11-03"):
            row["시험일"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "unsupported_schedule_range"):
                candidate.display_records([row])

    def test_gojobs_review_never_promotes_the_six_unverified_notices(self):
        report = candidate.build(self.root, now=NOW)
        data = json.loads((self.output / "gojobs-candidate.json").read_text())
        self.assertEqual(data["candidates"], [])
        self.assertEqual(len(data["review_records"]), 6)
        self.assertFalse(any(row["new_application_eligible"] for row in data["review_records"]))
        self.assertEqual(report["gojobs"]["decisions"], {"blocked_source_integrity": 1, "excluded_non_recruitment": 1, "needs_review": 4})

    def test_explicit_live_mode_uses_one_collect_call_and_all_validated_rows(self):
        rows = self.snapshot()["records"]
        calls = []
        class Client:
            request_counts = {"list": 1}
            def __init__(self, key):
                calls.append("client")
            def collect(self):
                calls.append("collect")
                return {"records": copy.deepcopy(rows), "verification": {"authentication_verified": True, "list_verified": True, "dataset_year": 2026, "total_rows": len(rows)}}
            def verify(self):
                raise AssertionError("must not verify then refetch")
        report = candidate.build(self.root, live_exam=True, now=NOW, key="synthetic-candidate-test-key", client_factory=Client)
        self.assertEqual(calls, ["client", "collect"])
        self.assertEqual(report["api_requests"], {"gojobs": 0, "mpm_exam": 1})
        self.assertEqual(report["mpm_exam"]["retrieved_at"], "2026-11-03T16:00:00+09:00")
        self.assertTrue(report["mpm_exam"]["authentication_retested"])
        self.assertEqual(report["mpm_exam"]["records"], 28)
        self.assert_preserved()

    def test_live_failure_does_not_publish_partial_or_stale_output(self):
        client = mock.Mock()
        client.collect.side_effect = mpm_exam.APIError("incomplete_dataset")
        with self.assertRaises(mpm_exam.APIError):
            candidate.build(self.root, live_exam=True, now=NOW, key="synthetic-candidate-test-key", client_factory=lambda _: client)
        self.assertFalse(self.output.exists())
        self.assert_preserved()

    def test_invalid_dates_or_incomplete_snapshot_cannot_generate_candidate(self):
        original = self.before[candidate.EXAM_PATH]
        for kind in ("missing_row", "invalid_date", "future_timestamp"):
            data = json.loads(original)
            if kind == "missing_row":
                data["records"].pop()
            elif kind == "invalid_date":
                data["records"][0]["시험일"] = "2026-02-30"
            else:
                data["retrieved_at"] = "2027-01-01T00:00:00Z"
            (self.root / candidate.EXAM_PATH).write_text(json.dumps(data))
            with self.subTest(kind=kind), self.assertRaises((ValueError, mpm_exam.APIError)):
                candidate.build(self.root, now=NOW)
            self.assertFalse(self.output.exists())

    def test_year_manifest_must_match_the_pinned_dataset(self):
        path = self.root / candidate.MANIFEST_PATH
        data = json.loads(path.read_text())
        data["years"][0]["path"] = "data/civil-service/2027.json"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "unverified_year_manifest"):
            candidate.build(self.root, now=NOW)
        self.assertFalse(self.output.exists())

    def test_forged_candidate_promotion_and_source_title_markup_are_not_trusted(self):
        with mock.patch.object(candidate, "triage", return_value=[{"new_application_eligible": True}]), self.assertRaisesRegex(ValueError, "unverified_gojobs_candidate"):
            candidate.build(self.root, now=NOW)
        report = candidate.build(self.root, now=NOW)
        notices = [{"id": "1", "title": '<img src=x onerror="alert(1)">', "api_deadline": None, "decision": "needs_review"}]
        rendered = candidate.preview(report, notices)
        self.assertIn("&lt;img", rendered)
        self.assertNotIn("<img", rendered)

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "previous.txt"
        sentinel.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "candidate_output_already_exists"):
            candidate.build(self.root, now=NOW)
        self.assertEqual(sentinel.read_text(), "preserve")
        self.assert_preserved()

    def test_live_response_cannot_export_a_credential(self):
        rows = self.snapshot()["records"]
        secret = "synthetic-candidate-test-key"
        rows[0]["시험명"] = secret
        client = mock.Mock(request_counts={"list": 1})
        client.collect.return_value = {"records": rows, "verification": {"authentication_verified": True, "list_verified": True, "dataset_year": 2026, "total_rows": len(rows)}}
        with self.assertRaisesRegex(ValueError, "credential_in_candidate_rejected"):
            candidate.build(self.root, live_exam=True, now=NOW, key=secret, client_factory=lambda _: client)
        self.assertFalse(self.output.exists())
        self.assert_preserved()


if __name__ == "__main__":
    unittest.main()
