"""Regression checks for aggregate, privacy-safe rollout diagnostics."""
import unittest
from datetime import datetime, timedelta
from scripts.detect_new_job_alerts import KST
from scripts.alert_delivery_ledger import delivery_key
from scripts.send_all_opted_in_bounded import selection_diagnostics


class RolloutDiagnosticsTests(unittest.TestCase):
    def test_empty_candidates(self):
        self.assertEqual(selection_diagnostics([], [], {"delivered": [], "pending": []},
                                                datetime.now(KST))["ready_pairs"], 0)

    def test_matching_and_deduplication(self):
        now = datetime.now(KST)
        job = {"id": "a100", "title": "Developer", "due": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
               "region": "서울", "emp": "정규직", "edu": "무관", "cat": "IT"}
        tags = {"cp_optin": "yes",
                "cp_profile": '{"v":4,"region":["서울"],"employment":[],"education":[],"category":[],"keywords":""}'}
        sub = {"subscription_id": "internal-test-only", "opted_in": True, "tags": tags}
        result = selection_diagnostics([job], [sub], {"delivered": [], "pending": []}, now)
        self.assertEqual(result["ready_pairs"], 1)
        key = delivery_key(job["id"], sub["subscription_id"])
        pending = selection_diagnostics([job], [sub], {"delivered": [], "pending": [key]}, now)
        self.assertEqual(pending["reserved_pending_pairs"], 1)
        self.assertEqual(pending["ready_pairs"], 0)
        delivered = selection_diagnostics([job], [sub], {"delivered": [key], "pending": []}, now)
        self.assertEqual(delivered["already_delivered_pairs"], 1)
        self.assertEqual(delivered["ready_pairs"], 0)
        self.assertNotIn("internal-test-only", str(result))


if __name__ == "__main__":
    unittest.main()
