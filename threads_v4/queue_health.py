#!/usr/bin/env python3
"""CareerPick v4 queue readiness monitor. Read-only and fail-closed."""
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
SLOTS = (8, 12, 16, 20)

def expected_slots(now, hours=48):
    now = now.astimezone(KST)
    slots = []
    for day in range(4):
        date = (now + timedelta(days=day)).date()
        for hour in SLOTS:
            slot = datetime(date.year, date.month, date.day, hour, tzinfo=KST)
            if now < slot <= now + timedelta(hours=hours):
                slots.append(slot.isoformat())
    return slots

def inspect(queue, staging, history, now):
    if any(x.get("schema_version") != 1 or not isinstance(x.get("entries"), list) for x in (queue, staging)):
        raise ValueError("QUEUE_SCHEMA_INVALID")
    if not isinstance(history.get("records"), list):
        raise ValueError("HISTORY_SCHEMA_INVALID")
    posted = set(map(str, history.get("posted_ids", [])))
    for record in history["records"]:
        posted.update(str(x) for x in [record.get("job_id"), *(record.get("job_ids") or [])] if x)
    slots = expected_slots(now)
    ready, duplicate, invalid = [], [], []
    occupied = set()
    for entry in queue["entries"]:
        if not isinstance(entry, dict):
            invalid.append("NON_OBJECT_ENTRY")
            continue
        slot, nid = entry.get("scheduled_at"), entry.get("notice_id")
        if slot not in slots:
            continue
        if not nid or nid in posted or nid in occupied or slot in {r["slot"] for r in ready}:
            duplicate.append({"notice_id": nid, "slot": slot})
            continue
        if not isinstance(entry.get("writer"), dict) or entry["writer"].get("status") != "ready" or not isinstance(entry["writer"].get("post_text"), str) or not entry["writer"]["post_text"].strip():
            invalid.append({"notice_id": nid, "reason": "NOT_REVIEWED"})
            continue
        if not isinstance(entry.get("writer_review"), dict) or entry["writer_review"].get("status") != "approved":
            invalid.append({"notice_id": nid, "reason": "INDEPENDENT_REVIEW_MISSING"})
            continue
        occupied.add(nid)
        ready.append({"notice_id": nid, "slot": slot})
    missing = [slot for slot in slots if slot not in {r["slot"] for r in ready}]
    return {"status": "READY" if not missing and not duplicate and not invalid else "SUPPLY_REQUIRED",
            "ready_count": len(ready), "staged_count": len(staging["entries"]),
            "missing_slots": missing, "duplicates": duplicate, "invalid": invalid,
            "published_count": len(posted), "meta_posted": False}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--queue", required=True)
    p.add_argument("--staging", required=True)
    p.add_argument("--history", required=True)
    p.add_argument("--now")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(KST)
    if now.tzinfo is None:
        p.error("--now must include timezone")
    docs = [json.loads(Path(x).read_text(encoding="utf-8")) for x in (args.queue, args.staging, args.history)]
    result = inspect(*docs, now)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "READY" else 2

if __name__ == "__main__":
    raise SystemExit(main())
