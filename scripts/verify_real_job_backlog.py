"""Manually verify real ALIO candidate backlog persistence without sending."""
import json
import os
from datetime import datetime, timedelta
from scripts.detect_new_job_alerts import KST
from pathlib import Path

from scripts.alert_candidate_backlog import reconcile
from scripts.private_alert_backlog_store import read_backlog, save_backlog
from scripts import private_push_delivery_queue as queue


def verify(report, *, reader=read_backlog, writer=save_backlog, queue_reader=None):
    if (not isinstance(report, dict) or report.get("dry_run") is not True
            or report.get("initial_run") is True
            or not isinstance(report.get("new_jobs"), list)
            or any(not isinstance(job, dict) for job in report["new_jobs"])):
        raise ValueError("Invalid or initial candidate report")
    try:
        checked_at = datetime.fromisoformat(str(report["checked_at"]))
        if checked_at.tzinfo is None:
            raise ValueError("missing timezone")
        age = datetime.now(KST) - checked_at.astimezone(KST)
        if not timedelta(0) <= age <= timedelta(hours=2):
            raise ValueError("stale candidate report")
    except (KeyError, ValueError, TypeError, OverflowError):
        raise ValueError("Candidate report freshness unverified; no backlog write") from None
    previous, sha = reader()
    if sha is None or not isinstance(previous, list):
        raise RuntimeError("Private candidate backlog not initialized")
    durable, _ = (queue_reader or queue.read_queue)()
    queued_ids = {entry.get("job_id") for entry in durable["tasks"].values()
                  if entry["state"] in {"pending", "reserved", "uncertain"}}
    merged = reconcile(previous, report["new_jobs"], retain_job_ids=queued_ids)
    fresh_candidates = reconcile([], report["new_jobs"])
    writer(merged, sha)
    restored, restored_sha = reader()
    if restored_sha is None or restored != merged:
        raise RuntimeError("Private backlog persistence mismatch")
    # Second reconciliation with no fresh jobs verifies retention across runs.
    next_run = reconcile(restored, [], retain_job_ids=queued_ids)
    retained = {entry["job"]["id"] for entry in next_run}
    expected = {entry["job"]["id"] for entry in merged}
    if retained != expected:
        raise RuntimeError("Private backlog next-run retention mismatch")
    return {"mode": "manual_real_job_backlog_no_send",
            "fresh_valid_candidates": len(fresh_candidates),
            "nonempty_retention_verified": bool(next_run),
            "previous_records": len(previous), "saved_records": len(merged),
            "next_run_retained": len(next_run), "verified": True, "sent": 0}


def main():
    if os.environ.get("CP_CONFIRM_REAL_BACKLOG_VERIFY") != "VERIFY_REAL_JOB_BACKLOG":
        raise SystemExit("Manual verification confirmation missing")
    path = Path(os.environ.get("CP_ALERT_REPORT", "careerpick-new-jobs.json"))
    report = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(verify(report), sort_keys=True))


if __name__ == "__main__":
    main()
