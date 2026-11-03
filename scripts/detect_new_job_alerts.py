#!/usr/bin/env python3
"""Prepare CareerPick new-job and deadline D-1 candidates. Never sends push."""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "alio.json"
STATE = ROOT / ".notification-state.json"
KST = ZoneInfo("Asia/Seoul")

def parse_due(value):
    if not value:
        return None
    try:
        due = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return due.replace(tzinfo=KST) if due.tzinfo is None else due.astimezone(KST)
    except (ValueError, TypeError):
        return None

def compact(p):
    return {key: p.get(key) for key in ("id", "org", "title", "url", "due", "region", "emp", "edu", "cat", "desc")}

def main(*, backlog_persister=None):
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("posts"), list):
        raise RuntimeError("Invalid ALIO snapshot structure; preserving prior alert baseline")
    posts = payload["posts"]
    current = {str(p["id"]): p for p in posts if isinstance(p, dict) and p.get("id") and p.get("type") == "j" and p.get("alio")}
    # A transient empty API snapshot must never erase the previous baseline.
    # Otherwise, restored jobs would all appear "new" on the next run.
    if not current:
        raise RuntimeError("No valid ALIO jobs in snapshot; preserving prior alert baseline")
    previous_state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if not isinstance(previous_state, dict) or (
        STATE.exists() and (
            not isinstance(previous_state.get("ids"), list)
            or any(not isinstance(item, str) or not item for item in previous_state["ids"])
        )
    ):
        raise RuntimeError("Invalid alert baseline; refusing to overwrite detection history")
    initial = not STATE.exists()
    previous_ids = set(previous_state.get("ids", []))
    now = datetime.now(KST)
    tomorrow = (now + timedelta(days=1)).date()

    new_jobs = [compact(p) for key, p in current.items() if not initial and key not in previous_ids
                and (parse_due(p.get("due")) is None or parse_due(p.get("due")) > now)]
    deadline_jobs = []
    for key, p in current.items():
        due = parse_due(p.get("due"))
        # A detection is not a delivery. Keep D-1 candidates visible on
        # repeated dry runs; private per-subscriber delivery ledger deduplicates.
        if due and due.date() == tomorrow and due > now:
            deadline_jobs.append(compact(p))

    report = {"checked_at": now.isoformat(), "dry_run": True, "initial_run": initial,
              "new_count": len(new_jobs), "deadline_d1_count": len(deadline_jobs),
              "new_jobs": new_jobs, "deadline_d1_jobs": deadline_jobs,
              "note": "Candidate report only; device-specific saved-job targeting and OneSignal sending are NOT enabled."}
    # Detection and delivery run separately. Persist and read back candidates
    # BEFORE advancing the shared baseline, or the later sender sees zero new
    # jobs and loses candidates observed by this run. Any write/readback failure
    # leaves STATE unchanged, so the same candidates are detected on retry.
    if os.environ.get("CP_PERSIST_ALERT_BACKLOG") == "1":
        if initial:
            # A missing cache is not permission to broadcast historical jobs.
            report["backlog_handoff"] = {"status": "bootstrap_no_candidates", "sent": 0}
        else:
            if backlog_persister is None:
                from scripts.verify_real_job_backlog import verify
                backlog_persister = verify
            handoff = backlog_persister(report)
            if (not isinstance(handoff, dict) or handoff.get("verified") is not True
                    or type(handoff.get("sent")) is not int or handoff["sent"] != 0
                    or any(type(handoff.get(key)) is not int or handoff[key] < 0
                           for key in ("fresh_valid_candidates", "saved_records"))):
                raise RuntimeError("Private backlog handoff unverified; preserving alert baseline")
            report["backlog_handoff"] = {
                "status": "persisted_and_read_back",
                "fresh_valid_candidates": handoff["fresh_valid_candidates"],
                "saved_records": handoff["saved_records"], "sent": 0}
    Path(os.environ.get("CP_ALERT_REPORT", "/tmp/careerpick-new-jobs.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: report[key] for key in ("initial_run", "new_count", "deadline_d1_count")}
    if "backlog_handoff" in report:
        summary["backlog_handoff"] = report["backlog_handoff"]
    if os.environ.get("CP_UPDATE_ALERT_STATE") == "1":
        state = {"ids": sorted(current), "updated": now.isoformat()}
        # Do not leave a truncated baseline if the runner stops during a write.
        descriptor, temporary = tempfile.mkstemp(prefix=".notification-", dir=STATE.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, STATE)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == "__main__":
    main()
