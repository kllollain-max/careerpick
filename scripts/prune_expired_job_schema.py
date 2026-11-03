#!/usr/bin/env python3
"""Remove expired JobPosting JSON-LD from archived CareerPick job pages.

ALIO no longer includes many expired jobs in alio.json, so the normal page
builder does not regenerate those archived HTML files. Keep the pages and
canonical URLs intact; remove only expired standalone JobPosting scripts.
No network calls, credentials, or user data.
"""
import argparse
import json
import re
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
JSON_LD = re.compile(
    r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script\s*>',
    re.IGNORECASE | re.DOTALL,
)


def deadline_utc(value):
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            dt = datetime.combine(datetime.fromisoformat(raw).date(), time.max, KST)
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def prune_html(html, now):
    """Return (HTML, removed_count); leave unknown/mixed schema untouched."""
    removed = 0

    def replace(match):
        nonlocal removed
        try:
            schema = json.loads(match.group(1))
        except (ValueError, TypeError):
            return match.group(0)
        if not isinstance(schema, dict):
            return match.group(0)
        kind = schema.get("@type")
        if kind != "JobPosting" and not (isinstance(kind, list) and "JobPosting" in kind):
            return match.group(0)
        due = deadline_utc(schema.get("validThrough"))
        if due is None or due >= now:
            return match.group(0)
        removed += 1
        return ""

    return JSON_LD.sub(replace, html), removed


def run(jobs_dir, *, check=False, now=None):
    now = now or datetime.now(timezone.utc)
    scanned = stale = 0
    for path in sorted(jobs_dir.glob("a[0-9]*.html")):
        if not re.fullmatch(r"a\d+\.html", path.name):
            continue
        scanned += 1
        before = path.read_text(encoding="utf-8")
        after, removed = prune_html(before, now)
        if removed:
            stale += 1
            if not check:
                path.write_text(after, encoding="utf-8")
    print(f"Archived JobPosting audit: {scanned} pages, {stale} expired schema page(s) {'found' if check else 'cleaned'}")
    return stale


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if expired JobPosting remains")
    parser.add_argument("--jobs-dir", type=Path, default=ROOT / "jobs")
    args = parser.parse_args()
    if not args.jobs_dir.is_dir():
        raise SystemExit("Jobs directory missing")
    stale = run(args.jobs_dir, check=args.check)
    if args.check and stale:
        raise SystemExit(f"{stale} expired JobPosting schema page(s) remain")


if __name__ == "__main__":
    main()
