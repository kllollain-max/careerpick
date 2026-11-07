"""Pure candidate-backlog reconciliation; no storage, discovery, or sends.

Callers must persist the returned state in an access-controlled store with
concurrency protection. Never put subscriber identifiers in this backlog.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from scripts.detect_new_job_alerts import KST
from scripts.alert_source_contract import CLEANEYE_JOB_FIELDS, candidate_open, supported_job_id

MAX_AGE = timedelta(days=7)
MAX_CANDIDATES = 2000
FIELDS = ("id", "title", "org", "url", "due", "region", "emp", "edu", "cat", "desc")


def _compact(job):
    fields = FIELDS + (CLEANEYE_JOB_FIELDS if job.get("cleaneye") is True else ())
    return deepcopy({key: job.get(key) for key in fields})


def refresh_existing_cleaneye(existing, current_cleaneye, *, now):
    """Refresh only known IDs before old deadlines can prune the backlog.

    The caller supplies eligible posts from a currently verified source snapshot.
    An absent/stale source supplies an empty mapping, retaining the stored rows.
    This pure step preserves first_seen and never discovers new source IDs;
    reconciliation still applies the ordinary age, retention, and validity rules.
    """
    if not isinstance(existing, list) or not isinstance(current_cleaneye, dict):
        raise ValueError("Candidate list and verified source mapping required")
    if len(existing) > MAX_CANDIDATES:
        raise ValueError("Candidate backlog exceeds safety limit")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone-aware time required")
    refreshed = []
    for entry in existing:
        updated = deepcopy(entry)
        job = entry.get("job") if isinstance(entry, dict) else None
        job_id = job.get("id") if isinstance(job, dict) else None
        if supported_job_id(job_id) and job_id.startswith("cleaneye-"):
            fresh = current_cleaneye.get(job_id)
            if (isinstance(fresh, dict) and fresh.get("id") == job_id
                    and candidate_open(fresh, now)):
                updated["job"] = _compact(fresh)
        refreshed.append(updated)
    return refreshed


def reconcile(existing, fresh, *, now=None, retain_job_ids=None):
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware time required")
    if not isinstance(existing, list) or not isinstance(fresh, list):
        raise ValueError("Candidate lists required")
    if len(existing) > MAX_CANDIDATES or len(fresh) > MAX_CANDIDATES:
        raise ValueError("Candidate backlog exceeds safety limit")
    retained = set(retain_job_ids or ())
    merged = {}
    for entry in existing:
        if not isinstance(entry, dict):
            raise ValueError("Malformed backlog record")
        job = entry.get("job")
        try:
            first_seen = datetime.fromisoformat(entry["first_seen"])
        except (KeyError, ValueError, TypeError):
            raise ValueError("Malformed backlog timestamp") from None
        if first_seen.tzinfo is None or first_seen > now:
            continue
        if not isinstance(job, dict) or not supported_job_id(job.get("id")):
            raise ValueError("Malformed backlog job")
        if now - first_seen > MAX_AGE and str(job["id"]) not in retained:
            continue
        if candidate_open(job, now):
            merged[job["id"]] = {"first_seen": first_seen.isoformat(), "job": _compact(job)}
    for job in fresh:
        if not isinstance(job, dict):
            raise ValueError("Malformed fresh job")
        job_id = job.get("id")
        if not supported_job_id(job_id):
            continue
        if not candidate_open(job, now):
            # An explicit source correction must not leave an earlier open
            # Cleaneye version eligible. Existing ALIO reconciliation stays as is.
            if job_id.startswith("cleaneye-"):
                merged.pop(job_id, None)
            continue
        previous = merged.get(job_id)
        merged[job_id] = {"first_seen": previous["first_seen"] if previous else now.isoformat(),
                          "job": _compact(job)}
    if len(merged) > MAX_CANDIDATES:
        raise ValueError("Candidate backlog exceeds safety limit")
    return [merged[key] for key in sorted(merged)]

