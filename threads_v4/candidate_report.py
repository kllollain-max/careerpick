#!/usr/bin/env python3
"""Produce a candidate review report; never mark a notice approved or post."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.threads_writer_input import build_input

def summarize(data):
    rows = data.get("candidates", [])
    if not isinstance(rows, list):
        raise ValueError("CANDIDATE_SCHEMA")
    selected = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        nid = row.get("notice_id")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        selected.append({"notice_id": nid, "organization": row.get("org") or row.get("organization"),
                         "title": row.get("title") or row.get("notice_title"),
                         "official_url": row.get("official_url") or row.get("url") or row.get("src"),
                         "application_period": row.get("application_period"),
                         "employment": row.get("employment") or row.get("employment_type"),
                         "decision": "REVIEW_REQUIRED", "official_verified": False})
    review_rows = data.get("review_candidates", [])
    if not isinstance(review_rows, list):
        raise ValueError("REVIEW_SCHEMA")
    review_index = {r.get("notice_id"): r for r in review_rows if isinstance(r, dict) and r.get("notice_id")}
    for item in selected:
        details = review_index.get(item["notice_id"], {})
        for key in ("official_url", "application_period", "employment", "organization", "title"):
            if not item.get(key):
                item[key] = details.get(key) or details.get({"official_url":"url", "organization":"org", "title":"notice_title"}.get(key, key))
    return {"schema_version": 1, "status": "REVIEW_REQUIRED" if selected else "NO_CANDIDATE",
            "candidate_count": len(selected), "candidates": selected,
            "review_candidates": review_rows, "selection_audit": data.get("selection_audit", {}),
            "approved_count": 0, "meta_posted": False}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=24)
    args = parser.parse_args()
    queue = json.loads(Path(args.queue).read_text(encoding="utf-8"))
    if queue.get("schema_version") != 1 or not isinstance(queue.get("entries"), list):
        raise ValueError("QUEUE_SCHEMA")
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    data = build_input(now, args.limit, queued_entries=queue["entries"])
    result = summarize(data)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "candidate_count": result["candidate_count"],
                      "approved_count": 0, "meta_posted": False}, ensure_ascii=False))

if __name__ == "__main__":
    main()
