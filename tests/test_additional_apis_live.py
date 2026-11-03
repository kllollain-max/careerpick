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


if __name__ == "__main__":
    unittest.main()
