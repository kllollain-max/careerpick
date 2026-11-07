"""Existing-ID refresh before pruning; fake stores only and no sends."""
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from scripts import send_all_opted_in_bounded as worker
from scripts import verify_real_job_backlog as handoff
from scripts.alert_candidate_backlog import MAX_AGE, reconcile, refresh_existing_cleaneye
from scripts.alert_delivery_ledger import delivery_key
from scripts.alert_source_contract import candidate_open
from scripts.detect_new_job_alerts import compact
from test_alert_cleaneye_detection import Clock, NOW, cleaneye_job


def stored_job(*, ended=False, first_seen=None):
    job = cleaneye_job()
    if ended:
        job["due"] = "2026-11-06T23:59:59+09:00"
        job["cleaneyeDetail"]["접수마감일 원문"] = "2026-11-06"
    return {"first_seen": first_seen or (NOW - timedelta(days=2)).isoformat(),
            "job": compact(job)}


def verified_snapshot():
    # The extra source ID is historical and must never enter the backlog.
    posts = {job["id"]: dict(job, sourceUpdated=NOW.isoformat())
             for job in (cleaneye_job(), cleaneye_job("9999"))}
    return posts, posts, "verified"


def candidate_report():
    return {"dry_run": True, "initial_run": False,
            "checked_at": NOW.isoformat(), "new_jobs": []}


class CleaneyeBacklogRefreshTests(unittest.TestCase):
    def test_extended_deadline_keeps_first_seen_and_delivery_identity_without_backfill(self):
        previous = [stored_job(ended=True)]
        original = copy.deepcopy(previous)
        self.assertFalse(candidate_open(previous[0]["job"], NOW))
        fresh = verified_snapshot()[1]
        refreshed = refresh_existing_cleaneye(previous, fresh, now=NOW)
        result = reconcile(refreshed, [], now=NOW)
        self.assertEqual(previous, original)
        self.assertEqual([entry["job"]["id"] for entry in result], ["cleaneye-9001"])
        self.assertEqual(result[0]["first_seen"], original[0]["first_seen"])
        self.assertEqual(result[0]["job"]["due"], fresh["cleaneye-9001"]["due"])
        self.assertEqual(result[0]["job"]["sourceUpdated"], NOW.isoformat())
        self.assertEqual(delivery_key(result[0]["job"]["id"], "synthetic-subscriber"),
                         delivery_key(original[0]["job"]["id"], "synthetic-subscriber"))
        result[0]["job"]["cleaneyeDetail"]["기관명"] = "mutated local fixture"
        self.assertEqual(fresh["cleaneye-9001"]["cleaneyeDetail"]["기관명"], "테스트공단")

    def test_empty_snapshot_retains_rows_but_does_not_revive_expired_jobs(self):
        previous = [stored_job()]
        self.assertEqual(refresh_existing_cleaneye(previous, {}, now=NOW), previous)
        self.assertEqual(reconcile(refresh_existing_cleaneye([stored_job(ended=True)], {}, now=NOW),
                                   [], now=NOW, retain_job_ids={"cleaneye-9001"}), [])

    def test_refresh_does_not_reset_age_or_override_queue_retention(self):
        previous = [stored_job(ended=True, first_seen=(NOW - MAX_AGE - timedelta(seconds=1)).isoformat())]
        refreshed = refresh_existing_cleaneye(previous, verified_snapshot()[1], now=NOW)
        self.assertEqual(reconcile(refreshed, [], now=NOW), [])
        kept = reconcile(refreshed, [], now=NOW, retain_job_ids={"cleaneye-9001"})
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["first_seen"], previous[0]["first_seen"])

    def test_mismatched_or_ineligible_mapping_cannot_replace_existing_row(self):
        previous = [stored_job()]
        for fresh in (cleaneye_job("9999"), dict(cleaneye_job(), receptionState="verification_pending")):
            with self.subTest(fresh=fresh["id"]):
                self.assertEqual(refresh_existing_cleaneye(previous, {"cleaneye-9001": fresh}, now=NOW),
                                 previous)

    def run_handoff(self, previous, snapshot):
        stored = copy.deepcopy(previous)
        def reader():
            return copy.deepcopy(stored), "synthetic-backlog-version"
        def writer(entries, version):
            self.assertEqual(version, "synthetic-backlog-version")
            stored[:] = copy.deepcopy(entries)
        durable = {"version": 1, "tasks": {"synthetic-pair": {
            "state": "pending", "job_id": "cleaneye-9001"}}}
        with patch.object(handoff, "datetime", Clock), \
                patch.object(handoff, "cleaneye_snapshot", return_value=snapshot):
            result = handoff.verify(candidate_report(), reader=reader, writer=writer,
                                    queue_reader=lambda: (copy.deepcopy(durable), "synthetic-queue-version"))
        return stored, result

    def test_detector_handoff_refreshes_before_pruning_and_verified_readback(self):
        previous = [stored_job(ended=True)]
        stored, result = self.run_handoff(previous, verified_snapshot())
        self.assertEqual([entry["job"]["id"] for entry in stored], ["cleaneye-9001"])
        self.assertEqual(stored[0]["first_seen"], previous[0]["first_seen"])
        self.assertEqual(stored[0]["job"]["due"], cleaneye_job()["due"])
        self.assertEqual((result["fresh_valid_candidates"], result["saved_records"],
                          result["next_run_retained"], result["sent"]), (0, 1, 1, 0))

    def test_detector_handoff_preserves_existing_open_job_when_source_unavailable(self):
        for status in ("not_available", "unverified"):
            with self.subTest(status=status):
                previous = [stored_job()]
                stored, result = self.run_handoff(previous, (None, {}, status))
                self.assertEqual(stored, previous)
                self.assertTrue(result["verified"])

    def run_worker(self, previous, snapshot):
        stored = copy.deepcopy(previous)
        ledger = {"delivered": ["synthetic-delivered-hash"], "pending": ["synthetic-reserved-hash"]}
        original_ledger = copy.deepcopy(ledger)
        durable = {"version": 1, "tasks": {"synthetic-pair": {
            "state": "pending", "job_id": "cleaneye-9001"}}}
        def reader():
            return copy.deepcopy(stored), "synthetic-backlog-version"
        def writer(entries, version):
            self.assertEqual(version, "synthetic-backlog-version")
            stored[:] = copy.deepcopy(entries)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(candidate_report()), encoding="utf-8")
            env = {"CP_ENABLE_ALL_OPTED_IN_ROLLOUT": "1", "CP_ENABLE_LIVE_PUSH": "1",
                   "CP_ALERT_REPORT": str(path)}
            with patch.dict(os.environ, env, clear=True), patch.object(worker, "datetime", Clock), \
                    patch.object(worker, "read_private_ledger", return_value=(ledger, "synthetic-ledger-version")), \
                    patch.object(worker, "read_backlog", side_effect=reader), \
                    patch.object(worker, "save_backlog", side_effect=writer), \
                    patch.object(worker.queue, "read_queue", return_value=(durable, "synthetic-queue-version")), \
                    patch.object(worker, "cleaneye_snapshot", return_value=snapshot), \
                    patch.object(worker, "request_export", return_value="synthetic-export-url"), \
                    patch.object(worker, "read_export_ids", return_value=[]), \
                    patch.object(worker, "process_window", return_value={}) as process, \
                    patch.object(worker, "send", side_effect=AssertionError("No sends in refresh tests")), \
                    redirect_stdout(io.StringIO()):
                worker._main()
                process.assert_called_once()
                candidates = process.call_args.args[0]
        self.assertEqual(ledger, original_ledger)
        return stored, candidates

    def test_worker_persists_extension_before_pruning_and_candidate_selection(self):
        previous = [stored_job(ended=True)]
        stored, candidates = self.run_worker(previous, verified_snapshot())
        self.assertEqual([job["id"] for job in candidates], ["cleaneye-9001"])
        self.assertEqual(stored[0]["first_seen"], previous[0]["first_seen"])
        self.assertEqual(candidates[0]["due"], cleaneye_job()["due"])
        self.assertEqual(stored[0]["job"], candidates[0])

    def test_worker_retains_original_when_feed_is_stale_or_missing(self):
        for status in ("not_available", "unverified"):
            with self.subTest(status=status):
                previous = [stored_job()]
                stored, candidates = self.run_worker(previous, (None, {}, status))
                self.assertEqual(stored, previous)
                self.assertEqual(candidates, [previous[0]["job"]])


if __name__ == "__main__":
    unittest.main()
