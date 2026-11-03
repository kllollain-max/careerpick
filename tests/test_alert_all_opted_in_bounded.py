import io
import copy
import threading
import json
from datetime import datetime
from scripts.detect_new_job_alerts import KST
import os
import unittest
from contextlib import redirect_stdout, nullcontext
from unittest.mock import patch, MagicMock

from scripts import send_all_opted_in_bounded as worker


class FakePrivateQueue:
    """Independent snapshots and a real atomic CAS, including concurrent readers."""
    def __init__(self):
        self.data = worker.queue.empty_queue()
        self.version = 0
        self.lock = threading.Lock()
        self.fail_write = None

    def read(self):
        with self.lock:
            return copy.deepcopy(self.data), str(self.version)

    def write(self, data, sha):
        with self.lock:
            if self.fail_write:
                self.fail_write(data)
            if sha != str(self.version):
                raise worker.queue.QueueConflict("synthetic conflict")
            self.data = copy.deepcopy(data)
            self.version += 1
            return {"content": {"sha": str(self.version)}}




class BoundedRolloutTests(unittest.TestCase):
    def setUp(self):
        # Legacy queue tests isolate the circuit; dedicated tests use its real CAS.
        guard = MagicMock()
        for name, value in (("session", lambda: nullcontext(guard)), ("current", lambda: guard)):
            p = patch.object(worker.circuit, name, side_effect=value)
            p.start()
            self.addCleanup(p.stop)
        official = patch.object(worker, "verify_current_job", return_value={"allowed": True})
        official.start()
        self.addCleanup(official.stop)
        self.queue_store = FakePrivateQueue()
        for name, fn in (("read_queue", self.queue_store.read), ("write_queue", self.queue_store.write)):
            patched = patch.object(worker.queue, name, side_effect=fn)
            patched.start()
            self.addCleanup(patched.stop)
        for name, result in (("reserve_private_delivery", True), ("finalize_private_delivery", None)):
            patched = patch.object(worker, name, return_value=result)
            patched.start()
            self.addCleanup(patched.stop)
        self.stored_backlog = []
        def read():
            return list(self.stored_backlog), "sha"
        def write(jobs, sha):
            self.stored_backlog = list(jobs)
            return {}
        self.backlog_read = patch.object(worker, "read_backlog", side_effect=read)
        self.backlog_write = patch.object(worker, "save_backlog", side_effect=write)
        self.backlog_read.start()
        self.backlog_write.start()
        self.addCleanup(self.backlog_read.stop)
        self.addCleanup(self.backlog_write.stop)
        # The scan checkpoint is private GitHub state; offline tests substitute
        # deterministic state so no credentials or network access are needed.
        self.cursor_read = patch.object(worker, "read_cursor", return_value=(
            {"version": 1, "next_index": 0, "export_hash": ""}, None))
        self.cursor_write = patch.object(worker, "save_cursor", return_value={})
        self.cursor_read.start()
        self.cursor_write.start()
        self.addCleanup(self.cursor_read.stop)
        self.addCleanup(self.cursor_write.stop)

    def test_backlog_readback_mismatch_blocks_export(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "jobs.json"
            report.write_text(json.dumps({"dry_run": True, "initial_run": False,
                "checked_at": datetime.now(KST).isoformat(),
                "new_jobs": [{"id": "a1", "title": "채용", "due": "2099-12-01"}]}),
                encoding="utf-8")
            with patch.dict(os.environ, {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1",
                                         "CP_ENABLE_LIVE_PUSH": "1",
                                         "CP_ALERT_REPORT": str(report)}, clear=True):
                with patch.object(worker, "read_private_ledger",
                                  return_value=({"delivered": [], "pending": []}, "sha")):
                    with patch.object(worker, "read_backlog", side_effect=[
                            ([], "sha"), ([], "newsha")]):
                        with patch.object(worker, "save_backlog", return_value={}):
                            with patch.object(worker, "request_export",
                                              side_effect=AssertionError("export must not run")):
                                with self.assertRaisesRegex(SystemExit, "readback mismatch"):
                                    worker.main()

    def test_optout_after_selection_blocks_live_send(self):
        import json
        import tempfile
        from pathlib import Path
        sid = "00000000-0000-4000-8000-000000000001"
        tags = {"cp_optin": "yes", "cp_profile": json.dumps({
            "v": 4, "region": [], "employment": ["정규직"],
            "education": [], "category": [], "keywords": ""})}
        initial = {"subscription_id": sid, "opted_in": True, "tags": tags}
        withdrawn = {"subscription_id": sid, "opted_in": False, "tags": tags}
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "jobs.json"
            report.write_text(json.dumps({"dry_run": True, "initial_run": False,
                "checked_at": datetime.now(KST).isoformat(),
                "new_jobs": [{"id": "a1", "title": "정규직 채용",
                              "emp": "정규직", "due": "2099-12-01"}]}), encoding="utf-8")
            env = {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1", "CP_ENABLE_LIVE_PUSH": "1",
                   "CP_ALERT_REPORT": str(report), "GITHUB_RUN_NUMBER": "1"}
            with patch.dict(os.environ, env, clear=True):
                with patch.object(worker, "read_private_ledger",
                                  return_value=({"delivered": [], "pending": []}, "sha")):
                    with patch.object(worker, "request_export", return_value="https://files.onesignal.com/x"):
                        with patch.object(worker, "read_export_ids", return_value=[sid]):
                            with patch.object(worker, "lookup", side_effect=[initial, withdrawn]) as lookups:
                                with patch.object(worker, "send",
                                                  side_effect=AssertionError("must never send")):
                                    with redirect_stdout(io.StringIO()) as output:
                                        worker.main()
        self.assertEqual(lookups.call_count, 2)
        self.assertIn('"selected": 1', output.getvalue())
        self.assertIn('"accepted": 0', output.getvalue())

    def test_four_consenters_are_capped_at_three_and_unserved_remain_eligible(self):
        import json
        import tempfile
        from pathlib import Path
        from scripts.alert_delivery_ledger import delivery_key
        ids = [f"00000000-0000-4000-8000-{i:012x}" for i in range(1, 5)]
        tags = {"cp_optin": "yes", "cp_profile": json.dumps({
            "v": 4, "region": [], "employment": ["정규직"],
            "education": [], "category": [], "keywords": ""})}
        job = {"id": "a1", "title": "정규직 채용", "emp": "정규직", "due": "2099-12-01"}
        accepted = []
        ledger = {"delivered": [], "pending": []}
        def subscriber(sid):
            return {"subscription_id": sid, "opted_in": True, "tags": tags}
        def deliver(job, sid, **kwargs):
            accepted.append(sid)
            ledger["delivered"].append(delivery_key(job["id"], sid))
            return {"sent": True, "notification_id": "mock-" + sid}
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "jobs.json"
            report.write_text(json.dumps({"dry_run": True, "initial_run": False,
                "checked_at": datetime.now(KST).isoformat(), "new_jobs": [job]}),
                encoding="utf-8")
            env = {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1", "CP_ENABLE_LIVE_PUSH": "1",
                   "CP_ALERT_REPORT": str(report), "GITHUB_RUN_NUMBER": "1"}
            with patch.dict(os.environ, env, clear=True):
                with patch.object(worker, "read_private_ledger",
                                  side_effect=lambda: (dict(ledger), "sha")):
                    with patch.object(worker, "request_export", return_value="https://files.onesignal.com/x"):
                        with patch.object(worker, "read_export_ids", return_value=ids):
                            with patch.object(worker, "lookup", side_effect=subscriber):
                                with patch.object(worker, "send", side_effect=deliver):
                                    with redirect_stdout(io.StringIO()) as first:
                                        worker.main()
                                    with redirect_stdout(io.StringIO()) as second:
                                        worker.main()
        self.assertEqual(len(accepted), 4)
        self.assertEqual(len(set(accepted)), 4)
        self.assertIn('"accepted": 3', first.getvalue())
        self.assertIn('"accepted": 1', second.getvalue())

    def test_rotation_covers_all_200_subscribers_across_runs(self):
        n = 200
        covered = set()
        for run in range(1, 11):
            start = worker.scan_start(run, n)
            covered.update((start + i) % n for i in range(worker.MAX_LOOKUPS_PER_RUN))
        self.assertEqual(covered, set(range(n)))

    def test_rotation_rejects_invalid_inputs(self):
        for run, n in ((0, 200), (1, 0), (-1, 100)):
            with self.assertRaises(ValueError):
                worker.scan_start(run, n)

    def test_default_disabled_without_any_network(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(worker, "request_export", side_effect=AssertionError("export called")):
                with patch.object(worker, "send", side_effect=AssertionError("send called")):
                    with redirect_stdout(io.StringIO()) as output:
                        worker.main()
        self.assertIn('"sent": 0', output.getvalue())

    def test_more_than_twenty_subscribers_does_not_block_bounded_scan(self):
        import json
        import tempfile
        from pathlib import Path
        ids = [f"00000000-0000-4000-8000-{i:012x}" for i in range(25)]
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "jobs.json"
            report.write_text(json.dumps({"dry_run": True, "initial_run": False,
                                          "checked_at": datetime.now(KST).isoformat(),
                                          "new_jobs": []}), encoding="utf-8")
            env = {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1", "CP_ENABLE_LIVE_PUSH": "1",
                   "CP_ALERT_REPORT": str(report), "GITHUB_RUN_NUMBER": "1"}
            with patch.dict(os.environ, env, clear=True):
                with patch.object(worker, "read_private_ledger",
                                  return_value=({"delivered": [], "pending": []}, "sha")):
                    with patch.object(worker, "request_export", return_value="https://files.onesignal.com/x"):
                        with patch.object(worker, "read_export_ids", return_value=ids):
                            with patch.object(worker, "lookup", return_value=None) as lookups:
                                with patch.object(worker, "send",
                                                  side_effect=AssertionError("no send expected")):
                                    with redirect_stdout(io.StringIO()) as output:
                                        worker.main()
        self.assertEqual(lookups.call_count, 25)
        self.assertIn('"accepted": 0', output.getvalue())

    def test_large_export_scans_no_more_than_100(self):
        import json
        import tempfile
        from pathlib import Path
        ids = [f"00000000-0000-4000-8000-{i:012x}" for i in range(150)]
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "jobs.json"
            report.write_text(json.dumps({"dry_run": True, "initial_run": False,
                                          "checked_at": datetime.now(KST).isoformat(),
                                          "new_jobs": []}), encoding="utf-8")
            env = {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1", "CP_ENABLE_LIVE_PUSH": "1",
                   "CP_ALERT_REPORT": str(report), "GITHUB_RUN_NUMBER": "2"}
            with patch.dict(os.environ, env, clear=True):
                with patch.object(worker, "read_private_ledger",
                                  return_value=({"delivered": [], "pending": []}, "sha")):
                    with patch.object(worker, "request_export", return_value="https://files.onesignal.com/x"):
                        with patch.object(worker, "read_export_ids", return_value=ids):
                            with patch.object(worker, "lookup", return_value=None) as lookups:
                                with redirect_stdout(io.StringIO()) as output:
                                    worker.main()
        self.assertEqual(lookups.call_count, 100)
        self.assertIn('"scanned": 100', output.getvalue())

    def test_full_scan_even_when_first_cohort_has_three_matches(self):
        import json
        import tempfile
        from pathlib import Path
        ids = [f"00000000-0000-4000-8000-{i:012x}" for i in range(40)]
        tags = {"cp_optin": "yes", "cp_profile": json.dumps({
            "v": 4, "region": [], "employment": ["정규직"],
            "education": [], "category": [], "keywords": ""})}
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "jobs.json"
            report.write_text(json.dumps({"dry_run": True, "initial_run": False,
                "checked_at": datetime.now(KST).isoformat(),
                "new_jobs": [{"id": "a1", "title": "정규직 채용", "emp": "정규직",
                              "due": "2099-12-01"}]}), encoding="utf-8")
            env = {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1", "CP_ENABLE_LIVE_PUSH": "1",
                   "CP_ALERT_REPORT": str(report), "GITHUB_RUN_NUMBER": "1"}
            def subscriber(sid):
                return {"subscription_id": sid, "opted_in": True, "tags": tags}
            with patch.dict(os.environ, env, clear=True):
                with patch.object(worker, "read_private_ledger",
                                  return_value=({"delivered": [], "pending": []}, "sha")):
                    with patch.object(worker, "request_export", return_value="https://files.onesignal.com/x"):
                        with patch.object(worker, "read_export_ids", return_value=ids):
                            with patch.object(worker, "lookup", side_effect=subscriber) as lookups:
                                with patch.object(worker, "send",
                                                  return_value={"sent": True, "notification_id": "mock-notification"}):
                                    with redirect_stdout(io.StringIO()) as output:
                                        worker.main()
        self.assertEqual(lookups.call_count, 43)
        self.assertIn('"accepted": 3', output.getvalue())

    def test_stale_report_blocks_private_export(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "jobs.json"
            report.write_text(json.dumps({"dry_run": True, "initial_run": False,
                                          "checked_at": "2020-01-01T00:00:00+09:00",
                                          "new_jobs": []}), encoding="utf-8")
            with patch.dict(os.environ, {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1",
                                         "CP_ENABLE_LIVE_PUSH": "1",
                                         "CP_ALERT_REPORT": str(report)}, clear=True):
                with patch.object(worker, "read_private_ledger",
                                  side_effect=AssertionError("ledger must not be read")):
                    with patch.object(worker, "request_export",
                                      side_effect=AssertionError("export must not run")):
                        with self.assertRaises(SystemExit):
                            worker.main()

    def test_invalid_ledger_prevents_private_export(self):
        import json
        import tempfile
        from pathlib import Path
        from datetime import datetime
        from scripts.detect_new_job_alerts import KST
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "jobs.json"
            report.write_text(json.dumps({"dry_run": True, "initial_run": False,
                                          "checked_at": datetime.now(KST).isoformat(),
                                          "new_jobs": []}), encoding="utf-8")
            env = {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1",
                   "CP_ENABLE_LIVE_PUSH": "1", "CP_ALERT_REPORT": str(report)}
            with patch.dict(os.environ, env, clear=True):
                with patch.object(worker, "read_private_ledger",
                                  return_value=({"pending": []}, "sha")):
                    with patch.object(worker, "request_export",
                                      side_effect=AssertionError("export should not run")):
                        with self.assertRaises(SystemExit):
                            worker.main()

    def test_missing_backlog_prevents_subscriber_export(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "jobs.json"
            report.write_text(json.dumps({"dry_run": True, "initial_run": False,
                "checked_at": datetime.now(KST).isoformat(), "new_jobs": []}), encoding="utf-8")
            with patch.dict(os.environ, {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1",
                                         "CP_ENABLE_LIVE_PUSH": "1",
                                         "CP_ALERT_REPORT": str(report)}, clear=True):
                with patch.object(worker, "read_private_ledger",
                                  return_value=({"delivered": [], "pending": []}, "sha")):
                    with patch.object(worker, "read_backlog", return_value=(None, None)):
                        with patch.object(worker, "request_export",
                                          side_effect=AssertionError("must not export")):
                            with self.assertRaises(SystemExit):
                                worker.main()

    def test_enabled_without_live_guard_fails_before_network(self):
        with patch.dict(os.environ, {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1"}, clear=True):
            with patch.object(worker, "request_export", side_effect=AssertionError("export called")):
                with self.assertRaises(SystemExit):
                    worker.main()


if __name__ == "__main__":
    unittest.main()
