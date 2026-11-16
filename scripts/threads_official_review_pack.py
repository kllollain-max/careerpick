#!/usr/bin/env python3
"""Capture live official-source evidence for shortlisted Threads drafts.

A current SHA-256/HTML excerpt is a reviewer aid, not semantic approval.
No Meta calls, staging writes, or automatic v5 approval occur here.
"""
import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.threads_http import read_response
from scripts.threads_reviewed_ingest import (
    OfficialRedirect, official_url_allowed, MAX_OFFICIAL_BYTES,
)

KST = ZoneInfo("Asia/Seoul")


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.text = []
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.hidden:
            self.hidden -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if not self.hidden:
            self.text.append(data)


def normalized(text):
    return " ".join(str(text or "").split())


def read_official(url, opener=None):
    """Download the exact official URL, including vetted redirect targets."""
    if not official_url_allowed(url):
        raise ValueError("OFFICIAL_URL_NOT_ALLOWED")
    opener = opener or urllib.request.build_opener(OfficialRedirect())
    req = urllib.request.Request(url, headers={
        "User-Agent": "CareerPickIndependentOfficialReview/1.0", "Accept": "*/*"})
    with read_response(req, timeout=12, opener=opener.open) as response:
        final = response.geturl()
        if not official_url_allowed(final):
            raise ValueError("OFFICIAL_FINAL_URL_NOT_ALLOWED")
        content_type = response.headers.get("Content-Type", "").lower()
        data = response.read(MAX_OFFICIAL_BYTES + 1)
    if not data or len(data) > MAX_OFFICIAL_BYTES:
        raise ValueError("OFFICIAL_BYTES_EMPTY_OR_TOO_LARGE")
    info = {"url": url, "final_url": final, "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data), "content_type": content_type,
            "checked_at": datetime.now(KST).isoformat(),
            "text_available": False, "official_page_title": None,
            "visible_text_excerpt": None}
    if "html" in content_type:
        # The excerpt is deliberately non-authoritative. Korean institutional
        # sites may use EUC-KR/CP949 or client-rendered notice content.
        match = re.search(r"charset\s*=\s*['\"]?([A-Za-z0-9_-]+)", content_type)
        encodings = [match.group(1)] if match else []
        encodings.extend(("utf-8", "cp949"))
        html = None
        for encoding in dict.fromkeys(encodings):
            try:
                html = data.decode(encoding)
                break
            except (UnicodeError, LookupError):
                continue
        if html is not None:
            parser = VisibleText()
            parser.feed(html)
            visible = normalized(" ".join(parser.text))
            info.update(text_available=True,
                        official_page_title=normalized(" ".join(parser.title))[:300],
                        visible_text_excerpt=visible[:3000])
    return info


def build_packet(bundle, fetch=read_official, limit=8, max_attempts=24):
    if (not isinstance(bundle, dict) or bundle.get("status") != "review_required"
            or bundle.get("approved_for_queue") is not False
            or not isinstance(bundle.get("drafts"), list)):
        raise ValueError("UNREVIEWED_DRAFT_BUNDLE_REQUIRED")
    if type(limit) is not int or not 1 <= limit <= 8:
        raise ValueError("EVIDENCE_LIMIT_INVALID")
    if type(max_attempts) is not int or not limit <= max_attempts <= 24:
        raise ValueError("EVIDENCE_ATTEMPT_LIMIT_INVALID")
    records = []
    seen = set()
    candidates = []
    alternatives = bundle.get("official_source_alternatives", [])
    if not isinstance(alternatives, list):
        raise ValueError("OFFICIAL_ALTERNATIVES_INVALID")
    for draft in (bundle["drafts"] + alternatives)[:100]:
        if not isinstance(draft, dict) or draft.get("status") != "unreviewed":
            continue
        nid = draft.get("notice_id")
        if not isinstance(nid, str) or not nid or nid in seen:
            continue
        seen.add(nid)
        candidates.append(draft)

    def capture(draft):
        nid = draft["notice_id"]
        url = draft.get("official_url_for_private_review")
        item = {"notice_id": nid, "suggested_slot": draft.get("suggested_slot"),
                "official_url": url, "evidence_status": "not_verified",
                "semantic_review": "required", "publisher_validate_entry": "not_run"}
        try:
            if not official_url_allowed(url):
                raise ValueError("OFFICIAL_URL_NOT_ALLOWED")
            source = fetch(url)
            if not isinstance(source, dict) or not re.fullmatch(
                r"[0-9a-f]{64}", str(source.get("sha256", ""))):
                raise ValueError("OFFICIAL_EVIDENCE_INVALID")
            excerpt = source.get("visible_text_excerpt")
            title = normalized(draft.get("draft_text", ""))
            # Do not infer recruiting unit count or approval from loose matches.
            item.update(evidence_status="bytes_fetched_for_review", source=source,
                        text_requires_independent_review=True,
                        notice_body_has_text=bool(excerpt),
                        draft_text_has_notice=bool(title))
        except (ValueError, OSError, urllib.error.URLError) as error:
            item["block_reason"] = (str(error) if isinstance(error, ValueError)
                                    else "OFFICIAL_SOURCE_UNAVAILABLE")[:120]
        return item

    # A provider outage must not starve all later official sources. Preserve
    # ranking within each bounded batch, try alternatives until eight receipts
    # exist, and cap concurrency and total attempts (no recursive work).
    unavailable_hosts = set()
    deferred = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        while candidates and len(records) < max_attempts:
            if sum(r["evidence_status"] == "bytes_fetched_for_review" for r in records) >= limit:
                break
            batch = []
            while candidates and len(batch) < min(4, max_attempts - len(records)):
                draft = candidates.pop(0)
                host = urlsplit(str(draft.get("official_url_for_private_review") or "")).hostname
                if host in unavailable_hosts:
                    deferred.append(draft["notice_id"])
                else:
                    batch.append(draft)
            results = list(executor.map(capture, batch))
            records.extend(results)
            for result in results:
                host = urlsplit(str(result.get("official_url") or "")).hostname
                failures = [r for r in records if urlsplit(str(r.get("official_url") or "")).hostname == host]
                if host and len(failures) >= 4 and all(r.get("block_reason") == "OFFICIAL_SOURCE_UNAVAILABLE" for r in failures):
                    unavailable_hosts.add(host)
    return {"schema_version": 1, "status": "official_review_required",
            "automatic_approval": False, "approved_for_queue": False,
            "meta_posted": False, "records": records,
            "attempted": len(records), "max_attempts": max_attempts,
            "unavailable_hosts": sorted(unavailable_hosts), "deferred_notice_ids": deferred,
            "checked": sum(r["evidence_status"] == "bytes_fetched_for_review" for r in records),
            "required_next_step": "Independently read notice and attachments, cite each fact, run validate_entry and v5 checks before submission"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="threads-unreviewed-drafts.json")
    parser.add_argument("--output", default="threads-official-evidence.json")
    args = parser.parse_args()
    bundle = json.loads(Path(args.input).read_text(encoding="utf-8"))
    packet = build_packet(bundle)
    Path(args.output).write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Official-source bytes gathered for review: {packet['checked']}/{len(packet['records'])}; approved: 0; posted: 0")


if __name__ == "__main__":
    main()
