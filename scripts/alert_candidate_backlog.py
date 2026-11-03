"""Pure candidate-backlog reconciliation; no storage, discovery, or sends.

Callers must persist the returned state in an access-controlled store with
concurrency protection. Never put subscriber identifiers in this backlog.
"""
from datetime import datetime, timedelta
from scripts.detect_new_job_alerts import KST, parse_due

MAX_AGE = timedelta(days=7)
MAX_CANDIDATES = 2000
FIELDS = ("id", "title", "org", "url", "due", "region", "emp", "edu", "cat", "desc")


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
        if not isinstance(job, dict) or not str(job.get("id", "")).startswith("a"):
            raise ValueError("Malformed backlog job")
        if now - first_seen > MAX_AGE and str(job["id"]) not in retained:
            continue
        due = parse_due(job.get("due"))
        if due and due > now and job.get("title"):
            merged[str(job["id"])] = {"first_seen": first_seen.isoformat(),
                                      "job": {key: job.get(key) for key in FIELDS}}
    for job in fresh:
        if not isinstance(job, dict):
            raise ValueError("Malformed fresh job")
        job_id = str(job.get("id", ""))
        due = parse_due(job.get("due"))
        if not job_id.startswith("a") or not job.get("title") or due is None or due <= now:
            continue
        previous = merged.get(job_id)
        merged[job_id] = {"first_seen": previous["first_seen"] if previous else now.isoformat(),
                          "job": {key: job.get(key) for key in FIELDS}}
    if len(merged) > MAX_CANDIDATES:
        raise ValueError("Candidate backlog exceeds safety limit")
    return [merged[key] for key in sorted(merged)]
