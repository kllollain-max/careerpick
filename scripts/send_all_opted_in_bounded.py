"""Guarded scheduled rollout to current opted-in OneSignal subscriptions.

Disabled unless explicitly enabled; at most three notifications per run.
No subscriber IDs or export URLs are printed or persisted.
"""
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from scripts.detect_new_job_alerts import KST, cleaneye_snapshot
from scripts.private_onesignal_export_request import request_export
from scripts.private_onesignal_export_download import read_export_ids
from scripts.onesignal_known_subscriber import lookup
from scripts.alert_preference_matcher import packed_preferences, matches
from scripts.private_delivery_store import read_private_ledger
from scripts.private_alert_backlog_store import read_backlog, save_backlog
from scripts.alert_candidate_backlog import reconcile, refresh_existing_cleaneye
from scripts.alert_source_contract import candidate_open
from scripts.rollout_batch_planner import eligible_pairs
from scripts.alert_delivery_ledger import delivery_key
from scripts.onesignal_guarded_transport import send
from scripts.onesignal_safe_retry import RejectedRequest
from scripts.private_delivery_store import reserve_private_delivery, finalize_private_delivery
from scripts import private_push_delivery_queue as queue
from scripts.private_rollout_cursor import read_cursor, save_cursor, plan_window
from scripts.push_official_preflight import verify as verify_current_job
from scripts import private_push_circuit_breaker as circuit

MAX_SENDS = 3
MAX_LOOKUPS_PER_RUN = 100
COHORT_SIZE = 20


def scan_start(run_number, subscriber_count):
    """Rotate by one cohort; avoids permanent starvation at exact multiples of 100."""
    if not isinstance(run_number, int) or run_number < 1 or subscriber_count < 1:
        raise ValueError("Invalid rollout rotation inputs")
    return ((run_number - 1) * COHORT_SIZE) % subscriber_count


def selection_diagnostics(candidates, verified, ledger, now):
    """Aggregate why opt-in subscribers have no available job; no IDs in output."""
    delivered = set(ledger.get("delivered", []))
    pending = set(ledger.get("pending", []))
    counts = {"open_candidates": 0, "verified_subscribers": len(verified),
              "preference_matched_pairs": 0, "already_delivered_pairs": 0,
              "reserved_pending_pairs": 0, "ready_pairs": 0}
    valid = []
    for job in candidates:
        if candidate_open(job, now):
            valid.append(job)
    counts["open_candidates"] = len(valid)
    for sub in verified:
        sid = sub["subscription_id"]
        for job in valid:
            if not matches(job, sub["tags"]):
                continue
            counts["preference_matched_pairs"] += 1
            key = delivery_key(str(job["id"]), sid)
            if key in delivered:
                counts["already_delivered_pairs"] += 1
            elif key in pending:
                counts["reserved_pending_pairs"] += 1
            else:
                counts["ready_pairs"] += 1
    return counts


def process_window(*args, live=True, **kwargs):
    if not live:
        return _process_window(*args, live=False, **kwargs)
    if os.environ.get("CP_ENABLE_LIVE_PUSH") != "1":
        raise RuntimeError("Live push guard disabled; queue and ledger unchanged")
    with circuit.session():
        return _process_window(*args, live=True, **kwargs)


def _process_window(candidates, verified, ledger, now, *, current_ids, scanned_ids=None, live=True, scoped=False):
    """The scheduled live path, also exercised with fake private/API stores.

    Queue CAS grants task ownership; the existing ledger reservation is an
    independent permanent guard shared with older send paths. Neither a lost
    storage response nor an uncertain API response is ever automatically replayed.
    """
    if type(live) is not bool or type(scoped) is not bool:
        raise ValueError("Boolean send mode required")
    if live and os.environ.get("CP_ENABLE_LIVE_PUSH") != "1":
        raise RuntimeError("Live push guard disabled; queue and ledger unchanged")
    owner = uuid.uuid4().hex
    # Enumerate ALL matches in the bounded subscriber window before applying
    # the send cap. Raw subscriber IDs remain only in this process's memory.
    pairs = eligible_pairs(candidates, verified, {"delivered": [], "pending": []},
                           now, limit=max(1, len(candidates) * len(verified)))
    available_jobs = {str(job["id"]) for job in candidates}
    current_hashes = {queue.subscriber_hash(sid) for sid in current_ids}
    window_hashes = {queue.subscriber_hash(sid) for sid in (
        scanned_ids if scanned_ids is not None else [sub["subscription_id"] for sub in verified])}
    pair_map = {delivery_key(job["id"], sub["subscription_id"]): (job, sub)
                for job, sub in pairs}
    def prepare(data):
        data = queue.enqueue(data, pairs, ledger)
        if scoped:
            # A one-subscriber test must never quarantine or cancel other tasks.
            data = {"version": 1, "tasks": {
                key: dict(entry, state="uncertain") if key in pair_map and entry["state"] == "reserved" else entry
                for key, entry in data["tasks"].items()}}
        else:
            data = queue.quarantine_inflight(data)
        tasks = dict(data["tasks"])
        protected = set(ledger.get("delivered", [])) | set(ledger.get("pending", []))
        for key, entry in tasks.items():
            if scoped and key not in pair_map:
                continue
            if entry["state"] != "pending":
                continue
            reason = None
            if key in protected:
                tasks[key] = dict(entry, state="uncertain", reason="existing_ledger")
                continue
            if entry.get("job_id") not in available_jobs:
                reason = "candidate_unavailable"
            elif entry.get("subscriber_hash") not in current_hashes:
                reason = "subscription_removed"
            elif entry.get("subscriber_hash") in window_hashes and key not in pair_map:
                reason = "preference_changed"
            if reason:
                tasks[key] = dict(entry, state="failed", reason=reason)
        return {"version": 1, "tasks": tasks}
    if live:
        state = queue.update_queue(prepare)
    else:
        existing, _ = queue.read_queue()
        state = prepare(existing)  # simulation only; no write or reservation

    selected = [key for key in pair_map if state["tasks"].get(key, {}).get("state") == "pending"][:MAX_SENDS]
    diagnostics = selection_diagnostics(candidates, verified, ledger, now)
    diagnostics.update(selected=len(selected), send_cap_per_run=MAX_SENDS,
                       subscriber_scan_limit=MAX_LOOKUPS_PER_RUN)
    print(json.dumps({"selection_diagnostics": diagnostics}, sort_keys=True))
    if not live:
        return {"preview_only": True, "selected": len(selected), "accepted": 0,
                "eligible": sum(state["tasks"].get(key, {}).get("state") == "pending" for key in pair_map),
                "remaining_in_window": bool(selected), "queue_counts": queue.counts(state)}
    accepted = 0
    for key in selected:
        circuit.current().check()
        job, sub = pair_map[key]
        official = verify_current_job(job, datetime.now(KST))
        if not official.get("allowed"):
            print(json.dumps({"official_preflight": official["reason"]}))
            if official.get("definitive") and queue.claim(key, owner):
                queue.record_outcome(key, owner, "failed", official["reason"])
            # Unknown status is NOT cancellation or a send attempt; keep pending.
            continue
        if not queue.claim(key, owner):
            continue
        job, sub = pair_map[key]
        # Consent and job validity are checked again immediately before request.
        current = lookup(sub["subscription_id"])
        if (not current or current.get("opted_in") is not True
                or current.get("subscription_id") != sub["subscription_id"]
                or packed_preferences(current.get("tags", {})) is None
                or not candidate_open(job, datetime.now(KST))
                or not matches(job, current["tags"])):
            queue.record_outcome(key, owner, "failed", "consent_or_preference_changed")
            continue
        # Durable queue claim FIRST, legacy ledger reservation SECOND, network LAST.
        if not queue.owned(key, owner):
            continue
        if not reserve_private_delivery(job["id"], current["subscription_id"]):
            queue.record_outcome(key, owner, "uncertain", "existing_ledger")
            continue
        if not queue.owned(key, owner):
            continue
        circuit.current().check()
        try:
            response = send(job, current["subscription_id"], verified_opt_in=True, live=True, test=scoped)
        except RejectedRequest as error:
            queue.record_outcome(key, owner, "failed", error.reason)
            circuit.current().failure("api_rejected", immediate=error.reason in {"http_401", "http_403"})
            continue
        except Exception:
            # No upstream exception values/identifiers enter logs or the queue.
            queue.record_outcome(key, owner, "uncertain", "transport_uncertain")
            circuit.current().failure("transport_uncertain")
            continue
        if not isinstance(response, dict):
            queue.record_outcome(key, owner, "uncertain", "invalid_transport_response")
            circuit.current().failure("invalid_transport_response")
            continue
        message_id = response.get("notification_id")
        outcome = "accepted" if response.get("sent") is True and isinstance(message_id, str) and message_id else response.get("outcome", "uncertain")
        if outcome not in {"accepted", "failed", "uncertain"}:
            outcome = "uncertain"
        try:
            queue.record_outcome(key, owner, outcome, response.get("reason", "unconfirmed_response"),
                                 message_id=message_id or response.get("provider_message_id"))
        except Exception:
            # If this write also fails, reserved is durable and the next run
            # quarantines it. Never send again, even if the API accepted it.
            try:
                queue.record_outcome(key, owner, "uncertain", "outcome_persistence_failed",
                                     message_id=message_id)
            except Exception:
                pass
            raise RuntimeError("Queue outcome persistence failed; no automatic resend") from None
        if outcome != "accepted":
            circuit.current().failure("api_not_accepted")
        if outcome == "accepted":
            circuit.current().success()
            accepted += 1
            # Accepted queue state is already durable if legacy finalization fails.
            try:
                if finalize_private_delivery(job["id"], current["subscription_id"]) is False:
                    raise RuntimeError("Legacy finalization was not confirmed")
            except Exception:
                raise RuntimeError("Ledger sync failed; global circuit review required") from None
    state, _ = queue.read_queue()
    remaining = any(state["tasks"].get(key, {}).get("state") == "pending" for key in pair_map)
    result = {"selected": len(selected), "accepted": accepted,
              "remaining_in_window": remaining, "queue_counts": queue.counts(state)}
    print(json.dumps({"queue_counts": result["queue_counts"]}, sort_keys=True))
    return result


def _main():
    if os.environ.get("CP_ENABLE_ALL_OPTED_IN_ROLLOUT") != "1":
        print(json.dumps({"mode": "disabled", "sent": 0}))
        return
    if os.environ.get("CP_ENABLE_LIVE_PUSH") != "1":
        raise SystemExit("Live push authorization missing")
    report = json.loads(Path(os.environ.get("CP_ALERT_REPORT", "careerpick-new-jobs.json")).read_text(encoding="utf-8"))
    if (not isinstance(report, dict) or report.get("dry_run") is not True
            or report.get("initial_run") is True or not isinstance(report.get("new_jobs"), list)
            or any(not isinstance(job, dict) for job in report["new_jobs"])):
        raise SystemExit("Invalid candidate report")
    try:
        checked_at = datetime.fromisoformat(str(report["checked_at"]))
        if checked_at.tzinfo is None:
            raise ValueError("timezone missing")
        age = datetime.now(KST) - checked_at.astimezone(KST)
        if not timedelta(0) <= age <= timedelta(hours=2):
            raise ValueError("stale or future report")
    except (KeyError, ValueError, TypeError, OverflowError):
        raise SystemExit("Candidate report freshness unverified; no sends") from None
    ledger, sha = read_private_ledger()
    if (sha is None or not isinstance(ledger, dict)
            or not isinstance(ledger.get("delivered"), list)
            or not isinstance(ledger.get("pending", []), list)):
        raise SystemExit("Private delivery ledger unavailable or invalid")
    # Persist the candidate backlog before subscriber discovery or delivery.
    # If private storage is absent or conflicts, fail closed without sending.
    previous, backlog_sha = read_backlog()
    if backlog_sha is None:
        raise SystemExit("Private candidate backlog is not initialized; no sends")
    durable, _ = queue.read_queue()
    retained = {entry.get("job_id") for entry in durable["tasks"].values()
                if entry["state"] in {"pending", "reserved", "uncertain"}}
    backlog_now = datetime.now(KST)
    _, current_cleaneye, _ = cleaneye_snapshot(backlog_now)
    previous = refresh_existing_cleaneye(previous, current_cleaneye, now=backlog_now)
    backlog = reconcile(previous, report["new_jobs"], now=backlog_now, retain_job_ids=retained)
    save_backlog(backlog, backlog_sha)
    restored, restored_sha = read_backlog()
    if restored_sha is None or restored != backlog:
        raise SystemExit("Private backlog readback mismatch; no sends")
    candidates = [entry["job"] for entry in restored]
    url = request_export(os.environ.get("CP_ONESIGNAL_APP_ID", ""),
                         os.environ.get("CP_ONESIGNAL_REST_API_KEY", ""))
    ids = read_export_ids(url)
    unique_ids = sorted(set(ids))
    if not unique_ids:
        process_window(candidates, [], ledger, datetime.now(KST), current_ids=[], scanned_ids=[])
        print(json.dumps({"mode": "bounded_rollout", "exported": 0, "accepted": 0}))
        return
    # Checkpointed scan: advancing only after the selected delivery batch
    # has completed means crashes re-examine the window safely via the ledger.
    checkpoint, checkpoint_sha = read_cursor()
    window, next_index, export_hash = plan_window(unique_ids, checkpoint, MAX_LOOKUPS_PER_RUN)
    verified = []
    scanned = 0
    for sid in window:
        sub = lookup(sid)
        scanned += 1
        if (sub and sub.get("opted_in") is True and sub.get("subscription_id") == sid
                and packed_preferences(sub.get("tags", {})) is not None):
            verified.append(sub)
    result = process_window(candidates, verified, ledger, datetime.now(KST),
                            current_ids=unique_ids, scanned_ids=window)
    if not result["remaining_in_window"]:
        save_cursor(next_index, export_hash, checkpoint_sha)
    print(json.dumps({"cursor_advanced": not result["remaining_in_window"],
                      "remaining_in_window": result["remaining_in_window"]}))
    selected, accepted = result["selected"], result["accepted"]
    print(json.dumps({"mode": "bounded_rollout", "exported": len(ids),
                      "verified": len(verified), "scanned": scanned,
                      "scan_limit": MAX_LOOKUPS_PER_RUN, "selected": selected,
                      "accepted": accepted, "cap": MAX_SENDS}))


def main():
    if (os.environ.get("CP_ENABLE_ALL_OPTED_IN_ROLLOUT") != "1"
            or os.environ.get("CP_ENABLE_LIVE_PUSH") != "1"):
        return _main()
    with circuit.session():
        return _main()


if __name__ == "__main__":
    main()

