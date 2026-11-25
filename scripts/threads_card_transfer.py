"""Export exact production card bytes to publisher-state for manual visual review.

Only an existing future submission refused specifically for missing card review
is eligible. This never approves, modifies submissions/staging/queue or posts.
The writer can inspect the artifact and copy exact blobs using the connector.
"""
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPORT = Path("threads-reviewed-ingest-report.json")
SUBMISSIONS = Path("threads-reviewed-submissions-input.json")
OUTPUT = Path("threads-card-transfer")
REASON = "CARD_VISUAL_REVIEW_REQUIRED"


def select_entry(report, submissions):
    refused = {(r.get("notice_id"), r.get("slot"))
               for r in report.get("refused", [])
               if isinstance(r, dict) and r.get("reason") == REASON}
    for e in submissions.get("entries", []):
        if not isinstance(e, dict):
            continue
        nid = e.get("notice_id")
        if (isinstance(nid, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,70}", nid)
                and (nid, e.get("scheduled_at")) in refused
                and e.get("writer", {}).get("status") == "ready"
                and not e["writer"].get("review", {}).get("v5", {}).get("card_visual_review")):
            return e
    return None


def pack(job, facts_sha, jpeg, preview):
    return {"schema_version": 1, "status": "visual_review_required",
            "automatic_approval": False, "meta_posted": False,
            "image_job": job, "facts_sha256": facts_sha,
            "assets": {
                "jpeg": {"sha256": hashlib.sha256(jpeg).hexdigest(),
                         "base64": base64.b64encode(jpeg).decode("ascii")},
                "preview": {"sha256": hashlib.sha256(preview).hexdigest(),
                            "base64": base64.b64encode(preview).decode("ascii")}}}


def main():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    submissions = json.loads(SUBMISSIONS.read_text(encoding="utf-8"))
    entry = select_entry(report, submissions)
    if "--needed" in sys.argv:
        return 0 if entry else 1
    if entry is None:
        return 0
    from PIL import Image
    from scripts.threads_queue_bridge import (ROOT, KST, BRANCH, QUEUE, STAGING,
        read, request, future_slots, next_media)
    from scripts.threads_auto import load, writer_inputs, master_public_copy
    from scripts.threads_writer_queue import validate_entry
    from scripts.threads_v5 import generate_card, STYLE
    from scripts.threads_card_review import card_facts_sha256

    token = os.environ.get("THREADS_CLAIM_TOKEN")
    if not token or os.environ.get("GITHUB_REPOSITORY") != "kllollain-max/careerpick":
        raise RuntimeError("CARD_TRANSFER_REPOSITORY_REQUIRED")
    now = datetime.now(KST)
    slot = entry["scheduled_at"]
    nid = entry["notice_id"]
    history = load(ROOT / "threads_posted.json", {"records": [], "posted_ids": []})
    if slot not in future_slots(now) or next_media(history) != "IMAGE":
        return 0
    if nid in history.get("posted_ids", []) or any(r.get("scheduled_at") == slot for r in history["records"]):
        return 0
    queue, _ = read(QUEUE, token)
    staging, _ = read(STAGING, token)
    if any(e.get("notice_id") == nid or e.get("scheduled_at") == slot
           for e in queue["entries"] + staging["entries"]):
        return 0
    claim = datetime.fromisoformat(slot).astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%MZ.json")
    try:
        request("GET", "threads-claims/" + claim, token)
        return 0
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    policy, source, details = writer_inputs(ROOT)
    selected = validate_entry(entry, datetime.fromisoformat(slot), now, history, source, details, policy)
    text, reply = master_public_copy(selected, STYLE, now=now)
    if reply or text != entry["writer"]["post_text"]:
        raise ValueError("CARD_TRANSFER_BODY_MISMATCH")
    job = selected["image_job"]
    digest = card_facts_sha256(job)
    path = f"threads/card-transfer/{nid}-{digest}.json"
    try:
        existing, _ = read(path, token)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    else:
        if (existing.get("facts_sha256") != digest or existing.get("image_job") != job
                or existing.get("automatic_approval") is not False
                or existing.get("meta_posted") is not False):
            raise ValueError("CARD_TRANSFER_EXISTING_MISMATCH")
        print("Exact card bundle already available: " + path)
        return 0
    OUTPUT.mkdir(exist_ok=True)
    jpeg = OUTPUT / (nid + ".jpg")
    png = OUTPUT / (nid + "-360.png")
    generate_card(job, jpeg)
    with Image.open(jpeg) as im:
        im.resize((360, 360), Image.Resampling.LANCZOS).save(png)
    bundle = pack(job, digest, jpeg.read_bytes(), png.read_bytes())
    raw = (json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(raw) > 900000:
        raise ValueError("CARD_TRANSFER_BUNDLE_TOO_LARGE")
    (OUTPUT / "manifest.json").write_text(json.dumps(
        {"path": path, "facts_sha256": digest, "image_job": job,
         "status": "visual_review_required", "automatic_approval": False,
         "meta_posted": False,
         "sha256": bundle["assets"]["jpeg"]["sha256"],
         "preview_sha256": bundle["assets"]["preview"]["sha256"]},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        request("PUT", path, token, {"branch": BRANCH,
            "message": "Export unapproved image review bytes [skip ci]",
            "content": base64.b64encode(raw).decode("ascii")})
    except urllib.error.HTTPError as exc:
        if exc.code not in (409, 422):
            raise
    readback, _ = read(path, token)
    if readback != bundle:
        raise ValueError("CARD_TRANSFER_READBACK_MISMATCH")
    print("Unapproved image bundle saved and read back: " + path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
