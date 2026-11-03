"""Pure, fail-closed rollout pair planner. Never sends or persists private IDs."""
from scripts.detect_new_job_alerts import parse_due
from scripts.alert_preference_matcher import matches, packed_preferences
from scripts.alert_delivery_ledger import delivery_key


def eligible_pairs(jobs, subscribers, ledger, now, limit=3):
    """Return at most limit pairs; each subscriber may receive multiple relevant jobs.

    Stable job order, explicit opt-in and ledger exclusions make interrupted
    runs resumable from the current private ledger without blind retries.
    """
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("Positive batch size required")
    if not isinstance(ledger, dict):
        raise ValueError("Ledger required")
    delivered = set(ledger.get("delivered", []))
    pending = set(ledger.get("pending", []))
    pairs, seen = [], set()
    for sub in subscribers:
        if not isinstance(sub, dict) or sub.get("opted_in") is not True:
            continue
        sid = sub.get("subscription_id")
        tags = sub.get("tags")
        if not isinstance(sid, str) or not sid or not isinstance(tags, dict):
            continue
        if packed_preferences(tags) is None:
            continue
        for job in jobs:
            if not isinstance(job, dict) or not str(job.get("id", "")).startswith("a") or not job.get("title"):
                continue
            due = parse_due(job.get("due"))
            if due is None or due <= now or not matches(job, tags):
                continue
            key = delivery_key(str(job["id"]), sid)
            if key in seen or key in pending or key in delivered:
                continue
            seen.add(key)
            pairs.append((job, sub))
            if len(pairs) >= limit:
                return pairs
    return pairs
