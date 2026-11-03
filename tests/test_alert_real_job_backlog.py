import unittest
from datetime import datetime, timedelta
from scripts.detect_new_job_alerts import KST
from scripts.verify_real_job_backlog import verify


class RealJobBacklogTests(unittest.TestCase):
    def test_persists_and_retains_real_candidate(self):
        from datetime import datetime
        due = (datetime.now(KST) + timedelta(days=3)).isoformat()
        report = {"dry_run": True, "initial_run": False,
                  "checked_at": datetime.now(KST).isoformat(),
                  "new_jobs": [{"id": "a123", "title": "채용", "due": due}]}
        stored = []
        def reader():
            return list(stored), "sha"
        def writer(entries, sha):
            stored[:] = entries
        result = verify(report, reader=reader, writer=writer, queue_reader=lambda: ({"version": 1, "tasks": {}}, "q"))
        self.assertTrue(result["verified"])
        self.assertTrue(result["nonempty_retention_verified"])
        self.assertEqual(result["fresh_valid_candidates"], 1)
        self.assertEqual(result["next_run_retained"], 1)
        self.assertEqual(result["sent"], 0)

    def test_empty_success_is_not_reported_as_nonempty_retention(self):
        report = {"dry_run": True, "initial_run": False,
                  "checked_at": datetime.now(KST).isoformat(), "new_jobs": []}
        result = verify(report, reader=lambda: ([], "sha"),
                        writer=lambda jobs, sha: None, queue_reader=lambda: ({"version": 1, "tasks": {}}, "q"))
        self.assertTrue(result["verified"])
        self.assertFalse(result["nonempty_retention_verified"])
        self.assertEqual(result["fresh_valid_candidates"], 0)

    def test_stale_report_does_not_access_private_store(self):
        report = {"dry_run": True, "initial_run": False,
                  "checked_at": "2020-01-01T00:00:00+09:00", "new_jobs": []}
        with self.assertRaisesRegex(ValueError, "freshness"):
            verify(report, reader=lambda: self.fail("must not read"),
                   writer=lambda jobs, sha: self.fail("must not write"))

    def test_malformed_candidate_does_not_access_private_store(self):
        report = {"dry_run": True, "initial_run": False,
                  "checked_at": datetime.now(KST).isoformat(), "new_jobs": [None]}
        with self.assertRaises(ValueError):
            verify(report, reader=lambda: self.fail("must not read"),
                   writer=lambda jobs, sha: self.fail("must not write"))

    def test_uninitialized_private_store_never_writes(self):
        with self.assertRaises(RuntimeError):
            verify({"dry_run": True, "initial_run": False,
                    "checked_at": datetime.now(KST).isoformat(), "new_jobs": []},
                   reader=lambda: (None, None),
                   writer=lambda jobs, sha: self.fail("must not write"))

    def test_initial_detection_rejected(self):
        with self.assertRaises(ValueError):
            verify({"dry_run": True, "initial_run": True, "new_jobs": []},
                   reader=lambda: self.fail("must not read"))


if __name__ == "__main__":
    unittest.main()
