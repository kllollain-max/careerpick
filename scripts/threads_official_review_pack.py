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

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.threads_reviewed_ingest import (
    OfficialRedirect, official_url_allowed, MAX_OFFICIAL_BYTES,
)

KST = ZoneInfo("Asia/Seoul")

# A single independently identified employer notice, tied to the precise
# Cleaneye source snapshot. Never treat a similarly named future notice as
# the same source. No semantics, publication, or approval is implied here.
CANONICAL_REVIEW_URLS = {
    "cleaneye-80820": {
        "source_post_sha256": "8d3752df0454401d33229336de56bbfebe204a1337ee98ca1ac6a87f458528f1",
        "source_detail_sha256": "c67be70000794ee30457361c24cb0ba633e4efc2d2b145790074b1dde8b0834e",
        "url": "https://www.smrtg.co.kr/employment/stffPbanInfo.do?stffPbanNo=2026-0155",
    },
}


def independently_located_notice(draft):
    reviewed = CANONICAL_REVIEW_URLS.get(draft.get("notice_id"))
    if (reviewed and
        draft.get("source_post_sha256") == reviewed["source_post_sha256"] and
        draft.get("source_detail_sha256") == reviewed["source_detail_sha256"]):
        return reviewed["url"]
    return draft.get("official_url_for_private_review")


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
    with opener.open(req, timeout=12) as response:
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


def build_packet(bundle, fetch=read_official, limit=8):
    if (not isinstance(bundle, dict) or bundle.get("status") != "review_required"
            or bundle.get("approved_for_queue") is not False
            or not isinstance(bundle.get("drafts"), list)):
        raise ValueError("UNREVIEWED_DRAFT_BUNDLE_REQUIRED")
    records = []
    seen = set()
    for draft in bundle["drafts"]:
        if len(records) >= limit:
            break
        if not isinstance(draft, dict) or draft.get("status") != "unreviewed":
            continue
        nid = draft.get("notice_id")
        if not isinstance(nid, str) or not nid or nid in seen:
            continue
        seen.add(nid)
        url = independently_located_notice(draft)
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
        records.append(item)
    return {"schema_version": 1, "status": "official_review_required",
            "automatic_approval": False, "approved_for_queue": False,
            "meta_posted": False, "records": records,
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
