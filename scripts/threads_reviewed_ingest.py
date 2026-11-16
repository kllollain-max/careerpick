#!/usr/bin/env python3
"""CAS-ingest *already independently reviewed* v5 entries into staging, never Meta.

Unreviewed handoffs are not accepted. Each entry must pass the existing
publisher validator, public-copy check, card check (when applicable), and an
independent download/digest comparison for an official source attachment.
"""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from scripts.threads_auto import load, writer_inputs
from scripts.threads_queue_bridge import (ROOT, BRANCH, QUEUE, STAGING, future_slots,
    verify_entry, read, request)

KST = ZoneInfo("Asia/Seoul")
MAX_OFFICIAL_BYTES = 20_000_000


def official_url_allowed(url):
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if (parts.scheme != "https" or not host or parts.username or
                parts.password or parts.port not in (None, 443)):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        # A conservative institutional-source allowlist, not a domain trust
        # assertion. Other domains need independently reviewed support first.
        return any(host == suffix or host.endswith("." + suffix)
                   for suffix in ("alio.go.kr", "go.kr", "or.kr", "ac.kr"))
    except ValueError:
        return False


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official_url_allowed(newurl):
            raise ValueError("OFFICIAL_REDIRECT_NOT_ALLOWED")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_official_digest(url):
    """Re-read actual official bytes, not the writer's claimed excerpt."""
    if not official_url_allowed(url):
        raise ValueError("OFFICIAL_SOURCE_URL_NOT_ALLOWED")
    opener = urllib.request.build_opener(OfficialRedirect())
    req = urllib.request.Request(url, headers={"User-Agent": "CareerPickOfficialReview/1.0",
                                                "Accept": "*/*"})
    with opener.open(req, timeout=25) as response:
        data = response.read(MAX_OFFICIAL_BYTES + 1)
        if len(data) > MAX_OFFICIAL_BYTES:
            raise ValueError("OFFICIAL_DOCUMENT_TOO_LARGE")
        if not data:
            raise ValueError("OFFICIAL_DOCUMENT_EMPTY")
    return hashlib.sha256(data).hexdigest()


def verify_official_receipt(entry, fetch_digest=fetch_official_digest):
    """Require a previously reviewed primary official document to match NOW.

    Raw-byte identity is necessary, NOT sufficient for semantic review: the
    existing validate_entry/v5 review must independently accept every fact.
    """
    review = entry.get("writer", {}).get("review", {})
    refs = review.get("source_refs", [])
    if not isinstance(refs, list):
        raise ValueError("OFFICIAL_SOURCE_RECEIPT_REQUIRED")
    eligible = [r for r in refs if isinstance(r, dict) and
                official_url_allowed(r.get("url")) and
                isinstance(r.get("sha256"), str) and
                re.fullmatch(r"[0-9a-f]{64}", r["sha256"])]
    if not eligible:
        raise ValueError("OFFICIAL_SOURCE_RECEIPT_REQUIRED")
    errors = []
    for ref in eligible:
        try:
            if fetch_digest(ref["url"]) == ref["sha256"]:
                return {"url": ref["url"], "sha256": ref["sha256"]}
            errors.append("OFFICIAL_SOURCE_BYTES_CHANGED")
        except (ValueError, OSError, urllib.error.URLError):
            errors.append("OFFICIAL_SOURCE_UNAVAILABLE")
    raise ValueError("OFFICIAL_SOURCE_BYTES_CHANGED" if
                     "OFFICIAL_SOURCE_BYTES_CHANGED" in errors else
                     "OFFICIAL_SOURCE_UNAVAILABLE")


def plan(queue, staged, submitted, history, policy, source, details, now,
         fetch_digest=fetch_official_digest, claimed_slots=()):
    """Fail closed per submission; never alter queue or any existing staging."""
    for data, label in ((queue, "QUEUE"), (staged, "STAGING"),
                        (submitted, "SUBMISSION")):
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or not isinstance(data.get("entries"), list)
                or any(not isinstance(x, dict) for x in data["entries"])):
            raise ValueError(label + "_SCHEMA")
    if not isinstance(history, dict) or not isinstance(history.get("records"), list) or not isinstance(history.get("posted_ids"), list):
        raise ValueError("HISTORY_SCHEMA")
    occupied = {e.get("scheduled_at") for e in queue["entries"] + staged["entries"]}
    used = {e.get("notice_id") for e in queue["entries"] + staged["entries"]}
    used.update(str(x) for x in history["posted_ids"])
    for record in history["records"]:
        if not isinstance(record, dict):
            raise ValueError("HISTORY_SCHEMA")
        if record.get("job_id"):
            used.add(str(record["job_id"]))
        used.update(str(x) for x in record.get("job_ids", []) if x)
    result = {**staged, "entries": list(staged["entries"])}
    accepted, refused = [], []
    for entry in submitted["entries"]:
        nid = entry.get("notice_id")
        slot = entry.get("scheduled_at")
        try:
            if not isinstance(nid, str) or not nid.strip() or nid in used:
                raise ValueError("NOTICE_ALREADY_USED_OR_INVALID")
            if not isinstance(slot, str) or slot not in future_slots(now):
                raise ValueError("SLOT_NOT_FUTURE")
            if slot in occupied or slot in claimed_slots:
                raise ValueError("SLOT_ALREADY_OCCUPIED_OR_CLAIMED")
            if any(r.get("scheduled_at") == slot for r in history["records"]):
                raise ValueError("SLOT_ALREADY_STARTED")
            # Never admit an unreviewed candidate, even if its body looks ready.
            if entry.get("writer", {}).get("status") != "ready":
                raise ValueError("NOT_A_REVIEWED_ENTRY")
            receipt = verify_official_receipt(entry, fetch_digest=fetch_digest)
            verify_entry(entry, now, history, policy, source, details)
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            refused.append({"notice_id": nid, "slot": slot, "reason": str(exc)[:140]})
            continue
        result["entries"].append(entry)
        accepted.append({"notice_id": nid, "slot": slot, "official_receipt": receipt})
        occupied.add(slot)
        used.add(nid)
    return result, accepted, refused


def run(path, apply=False):
    submitted = json.loads(Path(path).read_text(encoding="utf-8"))
    if submitted.get("automatic_approval") is True or submitted.get("meta_posted") is True:
        raise ValueError("UNREVIEWED_OR_POSTED_INPUT")
    token = os.environ.get("THREADS_CLAIM_TOKEN")
    if not token or os.environ.get("GITHUB_REPOSITORY") != "kllollain-max/careerpick":
        raise RuntimeError("GITHUB_CLAIM_ACCESS_REQUIRED")
    history = load(ROOT / "threads_posted.json", {"records": [], "posted_ids": []})
    policy, source, details = writer_inputs(ROOT)
    now = datetime.now(KST)
    report = {"status": "reviewed_staging_preflight", "time": now.isoformat(),
              "staging_updated": False, "queue_updated": False,
              "meta_posted": False, "accepted": [], "refused": []}
    for attempt in range(3):
        queue, _ = read(QUEUE, token)
        try:
            staged, sha = read(STAGING, token)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            staged, sha = {"schema_version": 1, "entries": []}, None
        # Reject a slot already claimed by a publisher, even if it does not
        # yet have a complete posted-history receipt.
        claimed = set()
        for entry in submitted.get("entries", []):
            slot = entry.get("scheduled_at") if isinstance(entry, dict) else None
            try:
                at = datetime.fromisoformat(slot)
                if at.utcoffset() is None or slot not in future_slots(now):
                    continue
                key = at.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%MZ.json")
                try:
                    request("GET", "threads-claims/" + key, token)
                    claimed.add(slot)
                except urllib.error.HTTPError as exc:
                    if exc.code != 404:
                        raise
            except (ValueError, TypeError):
                continue
        merged, accepted, refused = plan(queue, staged, submitted, history, policy,
                                         source, details, now, claimed_slots=claimed)
        report.update(accepted=accepted, refused=refused,
                      accepted_count=len(accepted), reviewed_input_count=len(submitted["entries"]))
        if not apply or not accepted:
            break
        payload = {"branch": BRANCH, "message": "Stage independently reviewed CareerPick Threads v5 entries [skip ci]",
                   "content": base64.b64encode((json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode()).decode()}
        if sha:
            payload["sha"] = sha
        try:
            request("PUT", STAGING, token, payload)
        except urllib.error.HTTPError as exc:
            if exc.code in (409, 422) and attempt < 2:
                time.sleep(1)
                continue
            raise
        readback, _ = read(STAGING, token)
        if readback != merged:
            raise RuntimeError("STAGING_READBACK_MISMATCH")
        report["staging_updated"] = True
        break
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Complete independently reviewed v5 entry bundle")
    parser.add_argument("--apply", action="store_true", help="CAS-write only to staging after all checks")
    parser.add_argument("--output", default="threads-reviewed-ingest-report.json")
    args = parser.parse_args()
    report = run(args.input, args.apply)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": report.get("accepted_count", 0),
                      "refused": len(report["refused"]),
                      "staging_updated": report["staging_updated"],
                      "meta_posted": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
