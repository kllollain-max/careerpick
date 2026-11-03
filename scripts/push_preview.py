#!/usr/bin/env python3
"""CareerPick push candidate preview. No external calls or subscriber data access.

This first stage deliberately does NOT send notifications: client-side preference
tags require an audited server-side matching strategy before production sends.
"""
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
BASE = "https://kllollain-max.github.io/careerpick"
MAX_PREVIEW = 30

def parse_date(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=KST)
    except ValueError:
        return None

def candidates(posts, now):
    found = []
    for p in posts:
        if not isinstance(p, dict) or not p.get("alio"):
            continue
        job_id = str(p.get("id", ""))
        if not (job_id.startswith("a") and job_id[1:].isdigit()):
            continue
        due = parse_date(p.get("due"))
        if not due or due < now:
            continue
        pub = parse_date(p.get("pub"))
        title = str(p.get("title", "")).strip()
        if not title:
            continue
        entry = {
            "id": job_id,
            "title": title[:100],
            "org": str(p.get("org", ""))[:80],
            "region": str(p.get("region", ""))[:40],
            "emp": p.get("emp", []),
            "edu": p.get("edu", []),
            "cat": str(p.get("cat", ""))[:80],
            "desc": str(p.get("desc", ""))[:160],
            "due": due.isoformat(),
            "url": f"{BASE}/jobs/{job_id}.html",
        }
        if pub and now - timedelta(hours=26) <= pub <= now:
            found.append(dict(entry, kind="new", event_id=f"new:{job_id}"))
        if due.astimezone(KST).date() == (now.astimezone(KST) + timedelta(days=1)).date():
            found.append(dict(entry, kind="deadline_d1", event_id=f"d1:{job_id}:{due.date()}"))
    return found

def matching_preference_tags(job, prefs):
    """Simulate the site's AND-across-fields / OR-within-field matching.

    This is an offline correctness check, not a OneSignal delivery selector.
    Empty preference fields impose no restriction. Keywords match any term.
    """
    for field, job_field in (("region", "region"), ("emp", "emp"), ("edu", "edu"), ("cat", "cat")):
        wanted = prefs.get(field, [])
        if not wanted:
            continue
        raw = job.get(job_field, [])
        available = raw if isinstance(raw, list) else [raw]
        if field == "region":
            # The homepage uses detailed work-region data and nationwide rules.
            # Without that data, reject uncertain matches rather than over-send.
            if not any(x in str(raw) for x in wanted):
                return False
        elif field == "edu":
            if not any(x in available or (x == "고졸 가능" and "학력무관" in available) for x in wanted):
                return False
        elif field == "emp":
            if not any(x in available or (x == "무기계약직" and "무기계약" in available) for x in wanted):
                return False
        elif not any(x in available for x in wanted):
            return False
    keywords = [w.casefold() for w in re.split(r"[,\\s]+", str(prefs.get("kw", ""))) if w]
    searchable = " ".join(str(job.get(k, "")) for k in ("title", "org", "cat", "desc")).casefold()
    return not keywords or any(w in searchable for w in keywords)


def preview_profile_matches(events, profile):
    """Return only events matching an explicit local test profile.

    This function is for validation only. It does not enumerate subscribers,
    access OneSignal or send notifications.
    """
    return [event for event in events if matching_preference_tags(event, profile)]


def matched_job_tags(job):
    """Not safe to use as OneSignal filters without subscriber-specific evaluation.

    Indexed v2 tags help future targeting but cannot faithfully implement
    arbitrary keyword substring search or nuanced region matching.
    """
    return None


def event_deduplicate(events, sent_ids):
    """Remove previously processed events, without mutating the ledger."""
    seen = set(sent_ids)
    result = []
    for item in events:
        event_id = item["event_id"]
        if event_id not in seen:
            result.append(item)
            seen.add(event_id)
    return result


def load_ledger(path):
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sent_event_ids", []), list):
        raise ValueError("Invalid push ledger format")
    return set(str(x) for x in data["sent_event_ids"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="alio.json")
    ap.add_argument("--output", default="/tmp/careerpick-push-preview.json")
    ap.add_argument("--ledger", default="push_sent.json")
    ap.add_argument("--test-profile", help="Optional local JSON profile for offline match verification")
    args = ap.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    now = datetime.now(KST)
    found = event_deduplicate(candidates(data.get("posts", []), now), load_ledger(Path(args.ledger)))
    if args.test_profile:
        profile = json.loads(Path(args.test_profile).read_text(encoding="utf-8"))
        if not isinstance(profile, dict):
            raise ValueError("Test profile must be a JSON object")
        found = preview_profile_matches(found, profile)
    result = {
        "generated_at": now.isoformat(),
        "mode": "preview_only",
        "test_profile_applied": bool(args.test_profile),
        "total_candidates": len(found),
        "candidates": found[:MAX_PREVIEW],
        "send_enabled": False,
        "targeting_verified": False,
        "deduplication": "preview-only: excludes event IDs in the read-only ledger",
        "reason": "Client-side multi-select tags are pipe-delimited and cannot safely be targeted using OneSignal equals filters. No notifications sent."
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Push preview only: {len(found)} candidates, {min(len(found),MAX_PREVIEW)} shown. No notifications sent.")
    for kind in ("new", "deadline_d1"):
        print(f"  {kind}: {sum(x['kind'] == kind for x in found)}")

if __name__ == "__main__":
    main()
