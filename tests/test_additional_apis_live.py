import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from scripts.verify_additional_apis import verify

KEY1 = "SENSITIVE_G0J0BS_123456789/+=END"
KEY2 = "SENSITIVE_EXAM_123456789/+=END"


class Good:
    def __init__(self, key):
        self.key = key
        self.request_counts = {"list": 1, "detail": 1}
        self.success_counts = {"list": 1, "detail": 1}

    def verify(self):
        return {"list_verified": True, "rows": 3}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "alio.json").write_text('{"posts":[{"id":"a1"}],"updated":"2026-11-03"}')
        (self.root / "alio-detail.json").write_text('{"a1":{"title":"existing"}}')
        self.before = {name: (self.root / name).read_bytes() for name in ("alio.json", "alio-detail.json")}

    def tearDown(self):
        self.tmp.cleanup()

    def run_case(self, **kwargs):
        return verify(self.root, keys=kwargs.pop("keys", {"gojobs": KEY1, "mpm_exam": KEY2}),
                      factories=kwargs.pop("factories", {"gojobs": Good, "mpm_exam": Good}), **kwargs)

    def test_success_keeps_source_bytes_and_counts(self):
        report = self.run_case()
        self.assertEqual(report["status"], "verified")
        self.assertTrue(report["source_preserved"])
        self.assertEqual(report["source_count_before"], report["source_count_after"])
        self.assertEqual(self.before, {name: (self.root / name).read_bytes() for name in self.before})
        self.assertEqual(report["production_data_writes"], 0)

    def test_missing_secret_does_not_block_other_service(self):
        report = self.run_case(keys={"gojobs": "", "mpm_exam": KEY2})
        self.assertEqual(report["services"]["gojobs"]["reason"], "missing_secret")
        self.assertEqual(report["services"]["mpm_exam"]["status"], "verified")
        self.assertEqual(report["services"]["gojobs"]["requests"], {})
        self.assertEqual(report["status"], "partial_or_blocked")

    def test_arbitrary_failure_does_not_leak_key_or_stop_other_api(self):
        class Broken(Good):
            def verify(self):
                raise RuntimeError("secret url " + self.key)
        report = self.run_case(factories={"gojobs": Broken, "mpm_exam": Good})
        self.assertEqual(report["services"]["gojobs"]["reason"], "unexpected_error")
        self.assertEqual(report["services"]["mpm_exam"]["status"], "verified")
        self.assertNotIn(KEY1, json.dumps(report))

    def test_cross_service_and_encoded_credential_echo_is_rejected(self):
        for value in (KEY1, KEY2, urllib.parse.quote(KEY1, safe=""), urllib.parse.quote_plus(KEY2)):
            class Echo(Good):
                def verify(self):
                    return {"title": value}
            report = self.run_case(factories={"gojobs": Echo, "mpm_exam": Good})
            self.assertEqual(report["services"]["gojobs"]["reason"], "credential_in_response_rejected")
            self.assertNotIn(value, json.dumps(report))
            self.assertNotIn(value, (self.root / "additional-api-check-output" / "report.json").read_text())

    def test_source_mutation_invalidates_otherwise_successful_check(self):
        root = self.root
        class Mutating(Good):
            def verify(self):
                (root / "alio.json").write_text('{"posts":[]}')
                return {"list_verified": True}
        report = self.run_case(factories={"gojobs": Mutating, "mpm_exam": Good})
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["source_preserved"])

    def test_only_safe_response_type_diagnostics_can_be_reported(self):
        class Types(Good):
            def verify(self):
                self.last_response_diagnostic = {"field_types": {"선발예정인원": ["int"]},
                                                 "raw_body": KEY1}
                raise RuntimeError(KEY1)
        report = self.run_case(factories={"gojobs": Types, "mpm_exam": Good})
        diagnostic = report["services"]["gojobs"]["response_diagnostic"]
        self.assertEqual(diagnostic, {"field_types": {"선발예정인원": ["int"]}})
        self.assertNotIn(KEY1, json.dumps(report))
        class Unsafe(Types):
            def verify(self):
                self.last_response_diagnostic = {"field_types": {"field": KEY2}}
                raise RuntimeError(KEY1)
        report = self.run_case(factories={"gojobs": Unsafe, "mpm_exam": Good})
        self.assertNotIn("response_diagnostic", report["services"]["gojobs"])

    def test_duplicate_baseline_blocks_all_requests(self):
        (self.root / "alio.json").write_text('{"posts":[{"id":"a1"},{"id":"a1"}]}')
        class MustNotRun(Good):
            def __init__(self, key):
                raise AssertionError("must not initialize")
        report = self.run_case(factories={"gojobs": MustNotRun, "mpm_exam": MustNotRun})
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["services"], {})

    def test_record_failure_preserves_authentication_and_verified_progress(self):
        class Partial(Good):
            def verify(self):
                self.request_counts = {"list": 2, "detail": 3}
                self.success_counts = {"list": 2, "detail": 2}
                self.verification_progress = {
                    "verification_complete": False,
                    "list_verified": True,
                    "list_queries_verified": 2,
                    "detail_verified_count": 2,
                    "detail_samples": [{"id": "101"}, {"id": "201"}],
                    "failed_notice": {"id": "102", "expected_institution_type": "g02",
                                      "expected_recruitment_type": "e01"},
                }
                self.last_response_diagnostic = {"detail_list_classification": {
                    "expected_institution_type": "g02", "observed_institution_type": "g01",
                    "title_matches": True}}
                error = RuntimeError("not serialized")
                error.safe_code = "invalid_classification_pair"
                raise error
        report = self.run_case(factories={"gojobs": Partial, "mpm_exam": Good})
        state = report["services"]["gojobs"]
        self.assertEqual(report["status"], "partial_or_blocked")
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["authentication_verified"])
        self.assertEqual(state["reason"], "invalid_classification_pair")
        self.assertEqual(state["verification_progress"]["failed_notice"]["id"], "102")
        self.assertEqual(state["verification_progress"]["detail_verified_count"], 2)
        self.assertEqual(state["verification_progress"]["detail_samples"], [{"id": "101"}, {"id": "201"}])
        self.assertEqual(state["response_diagnostic"]["detail_list_classification"]["observed_institution_type"], "g01")
        self.assertTrue(report["source_preserved"])

    def test_no_validated_response_does_not_claim_authentication(self):
        class Rejected(Good):
            def verify(self):
                self.request_counts = {"list": 1, "detail": 0}
                self.success_counts = {"list": 0, "detail": 0}
                error = RuntimeError("not serialized")
                error.safe_code = "service_key_not_registered"
                raise error
        report = self.run_case(factories={"gojobs": Rejected, "mpm_exam": Good})
        state = report["services"]["gojobs"]
        self.assertFalse(state["authentication_verified"])
        self.assertNotIn("authentication_basis", state)
        self.assertEqual(state["status"], "failed")

    def test_partial_progress_cannot_expose_either_credential(self):
        for leaked in (KEY1, KEY2, urllib.parse.quote(KEY2, safe="")):
            class EchoProgress(Good):
                def verify(self):
                    self.verification_progress = {"samples": [{"title": leaked}]}
                    raise RuntimeError("not serialized")
            report = self.run_case(factories={"gojobs": EchoProgress, "mpm_exam": Good})
            self.assertNotIn("verification_progress", report["services"]["gojobs"])
            self.assertNotIn(leaked, json.dumps(report))
            self.assertTrue(report["source_preserved"])

    def test_unapproved_or_oversized_progress_is_omitted(self):
        class SafeSubset(Good):
            def verify(self):
                self.verification_progress = {"detail_verified_count": 1, "raw_body": KEY1}
                raise RuntimeError("not serialized")
        report = self.run_case(factories={"gojobs": SafeSubset, "mpm_exam": Good})
        self.assertEqual(report["services"]["gojobs"]["verification_progress"],
                         {"detail_verified_count": 1})
        class TooLarge(Good):
            def verify(self):
                self.verification_progress = {"samples": [{"title": "x" * 65536}],
                                              "detail_verified_count": 2,
                                              "failed_notice": {"id": "102"}}
                raise RuntimeError("not serialized")
        report = self.run_case(factories={"gojobs": TooLarge, "mpm_exam": Good})
        state = report["services"]["gojobs"]
        self.assertTrue(state["verification_progress_truncated"])
        self.assertEqual(state["verification_progress"],
                         {"detail_verified_count": 2, "failed_notice": {"id": "102"}})


if __name__ == "__main__":
    unittest.main()
