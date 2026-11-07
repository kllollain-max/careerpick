"""Re-read one Cleaneye notice through the approved API before a push.

Use the same bounded client and normalizer as collection. A province code is
resolved from the official code service each time, never guessed from workplace.
Unknown/mismatching responses defer the task without claiming cancellation.
"""
import os
import re

import cleaneye
from scripts.collect_cleaneye import normalize
from scripts.cleaneye_source_adapter import eligible_cleaneye_post


# All fields used in the message or preference matching must still be current.
MATCH_FIELDS = ("id", "title", "org", "url", "src", "start", "due", "dueHasTime",
                "region", "emp", "edu", "cat", "desc", "text", "sourceStatus")


def fetch_current(job, now, *, client_factory=cleaneye.Client):
    job_id = str(job.get("id", ""))
    if not re.fullmatch(r"cleaneye-[0-9]+", job_id):
        raise ValueError("cleaneye_identity_unverified")
    key = os.environ.get("CLEANEYE_KEY") or os.environ.get("DATA_GO_KR_KEY") or ""
    client = client_factory(key)
    mapping = client.collect_region_codes(ac_year=now.year)
    region = job.get("sourceRegion")
    codes = [code for code, name in mapping.items() if name == region]
    if not isinstance(region, str) or not region or len(codes) != 1:
        raise ValueError("cleaneye_region_unverified")
    payload = client.list_region(codes[0])
    rows = [row for row in payload["result"] if row.get("NO") == job_id[9:]]
    if len(rows) != 1:
        raise ValueError("cleaneye_notice_unavailable")
    return normalize(rows[0], now)


def verify(job, now, *, fetcher=fetch_current):
    try:
        fresh = fetcher(job, now)
        if fresh.get("receptionState") in {"cancelled", "expired"}:
            return {"allowed": False, "definitive": True,
                    "reason": "cleaneye_official_cancelled_or_closed"}
        feed = {"source": "cleaneye", "collectionStatus": "verified",
                "updated": now.isoformat(), "posts": [fresh]}
        if not eligible_cleaneye_post(fresh, feed, now):
            return {"allowed": False, "definitive": False,
                    "reason": "cleaneye_official_unverified"}
        if any(fresh.get(key) != job.get(key) for key in MATCH_FIELDS):
            return {"allowed": False, "definitive": False,
                    "reason": "cleaneye_source_changed_refresh_required"}
        return {"allowed": True, "definitive": True,
                "reason": "cleaneye_open_verified"}
    except Exception:
        # Never expose a key, provider response, or a request URL in public logs.
        return {"allowed": False, "definitive": False,
                "reason": "cleaneye_official_unverified"}
