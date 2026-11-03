import unittest
from datetime import datetime, timedelta
from scripts.alert_candidate_backlog import reconcile, MAX_CANDIDATES
from scripts.detect_new_job_alerts import KST

NOW = datetime(2026, 10, 27, 16, 0, tzinfo=KST)


def job(identifier, due="2026-10-30"):
    return {"id": identifier, "title": "채용", "due": due, "emp": "정규직"}


class CandidateBacklogTests(unittest.TestCase):
    def test_unsent_candidates_survive_next_empty_detection(self):
        first = reconcile([], [job("a1")], now=NOW)
        second = reconcile(first, [], now=NOW + timedelta(hours=6))
        self.assertEqual([x["job"]["id"] for x in second], ["a1"])

    def test_expired_and_old_candidates_removed(self):
        old = [{"first_seen": (NOW - timedelta(days=8)).isoformat(),
                "job": job("a1")}]
        self.assertEqual(reconcile(old, [job("a2", "2020-01-01")], now=NOW), [])

    def test_duplicate_updates_preserve_original_timestamp(self):
        first = reconcile([], [job("a1")], now=NOW)
        updated = reconcile(first, [job("a1")], now=NOW + timedelta(hours=1))
        self.assertEqual(updated[0]["first_seen"], first[0]["first_seen"])
        self.assertEqual(len(updated), 1)

    def test_malformed_backlog_fails_closed(self):
        with self.assertRaises(ValueError):
            reconcile([{"job": job("a1"), "first_seen": "bad"}], [], now=NOW)

    def test_capacity_bound(self):
        with self.assertRaises(ValueError):
            reconcile([], [job("a1")] * (MAX_CANDIDATES + 1), now=NOW)


if __name__ == "__main__":
    unittest.main()
