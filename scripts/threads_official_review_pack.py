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

# A single independently identified employer notice, tied to the precise
# Cleaneye source snapshot. Never treat a similarly named future notice as
# the same source. No semantics, publication, or approval is implied here.
CANONICAL_REVIEW_URLS = {
    "cleaneye-80820": {
        "source_post_sha256": "8d3752df0454401d33229336de56bbfebe204a1337ee98ca1ac6a87f458528f1",
        "source_detail_sha256": "c67be70000794ee30457361c24cb0ba633e4efc2d2b145790074b1dde8b0834e",
        "url": "https://www.smrtg.co.kr/employment/stffPbanInfo.do?stffPbanNo=2026-0155",
    },
    # Employer-run Incruit applicant portal is scoped to this one Cleaneye
    # notice/snapshot. The 153-person posting has several distinct hiring
    # units; this mapping does not certify any unit count or approve a draft.
    "cleaneye-80848": {
        "source_post_sha256": "60f60ec1399d17fc1cf09cae49d3365377ee78ff20f4bb584a15398fc14c8ada",
        "source_detail_sha256": "f342ddd996f5d36479de4899f66d7e4d97355a1f6c28c252913b399a7b9a6371",
        "url": "https://recruit.incruit.com/cleanmetro/job/2610280002",
    },
    # Exact city-facility employer posting, matched to one Cleaneye 81115
    # snapshot. The attached 22-page notice and three-page job description
    # remain independent editorial review material, never auto-approval.
    # Exact Yangju city recruitment notice for one identified Yangju Culture
    # Tourism Foundation job record. Fingerprint both Cleaneye snapshots so
    # similarly titled future postings cannot inherit these source URLs.
    # City-hosted notice and annexes are review-only evidence, never approval.
    "cleaneye-81438": {
        "source_post_sha256": "46f3c0f292b99943f60fc5e292d55cd8b8ee4e20580e9697274b15a941ec3b33",
        "source_detail_sha256": "f700c5e494a4ab81c0b02fb2908ce472d7376e13f806ac72ea39300dfcc9a827",
        "url": "https://www.yangju.go.kr/www/selectBbsNttView.do?bbsNo=21&key=216&nttNo=209810",
    },
    "cleaneye-81115": {
        "source_post_sha256": "c2be94b6d942146ecb2f7abd5db2bb322c37e8add110f45d6fb3014575288305",
        "source_detail_sha256": "c74f8386011d789fa568f6d731b80d723fea7ac14f92661f57642b60316b66cb",
        "url": "https://cms.wfmc.kr/web/lay1/bbs/S1T225C230/A/3/view.do?article_seq=5841",
    },
}

# Exact attachments published with the independently located 2026-17 employer
# advert. These URLs were checked individually; none implies editorial approval.
CANONICAL_REVIEW_ANNEXES = {
    # Two exact PDF attachments published with Yangju notice 2026-2510.
    # Digest receipts cannot substitute for reading and validating the rules.
    "cleaneye-81438": [
        "https://www.yangju.go.kr/www/downloadBbsFile.do?key=216&bbsNo=21&atchmnflNo=206793",
        "https://www.yangju.go.kr/www/downloadBbsFile.do?key=216&bbsNo=21&atchmnflNo=206794",
    ],
    "cleaneye-80848": [
            "https://c.incru.it/newjobpost/2026/10_cleanmetro/%EB%B6%99%EC%9E%841.%20%EC%B1%84%EC%9A%A9%EA%B2%B0%EA%B2%A9%EC%82%AC%EC%9C%A0%20%EA%B4%80%EB%A0%A8.pdf",
            "https://c.incru.it/newjobpost/2026/10_cleanmetro/%EB%B6%99%EC%9E%842.%20%EC%84%9C%EB%A5%98%EC%A0%84%ED%98%95%20%ED%8F%89%EA%B0%80%EA%B8%B0%EC%A4%80.pdf",
            "https://c.incru.it/newjobpost/2026/10_cleanmetro/%EB%B6%99%EC%9E%843.%20%EC%84%9C%EC%9A%B8%EA%B5%90%ED%86%B5%EA%B3%B5%EC%82%AC%20%EC%9E%AC%EC%B7%A8%EC%97%85%EC%8B%AC%EC%82%AC%20%EB%B0%8F%20%EC%B7%A8%EC%97%85%EC%A0%9C%ED%95%9C%EC%8B%AC%EC%82%AC%20%EA%B4%80%EB%A0%A8.pdf"
    ],
    # These are the two exact PDFs linked from the 2026-17 employer
    # posting. Source bytes must be fetched and reviewed independently.
    "cleaneye-81115": [
        "https://cms.wfmc.kr/download.do?uuid=67d8c76c-8846-46d8-9e8f-a87d7ca79983.pdf",
        "https://cms.wfmc.kr/download.do?uuid=b96140dd-9408-4fd8-b5ac-361b21f40e53.pdf"
    ],
}


# Exact original employer recruitment board. This only supplies independent
# evidence for correction review, never confirmation that every other board
# contains no amendment, and never automatic editorial approval.
CANONICAL_REVIEW_BOARDS = {
    "a307417": {
        "source_post_sha256": "b3a52f04564d142583f5d90b3866c2e384d97d79414b626128f8749ea67f95c5",
        "source_detail_sha256": "50fcceca68d11f84611f382082ee5672fd350ce36bf6f34a67465b9cecedcc5e",
        "url": "https://www.knps.or.kr/front/portal/recruit/recruitDtl.do?menuNo=7070064&emplyId=EMPM020099",
        "expected_notice": "2027년 무등산국립공원 국립공원지킴이 채용 공고",
    },
    "cleaneye-80848": {
        "source_post_sha256": "60f60ec1399d17fc1cf09cae49d3365377ee78ff20f4bb584a15398fc14c8ada",
        "source_detail_sha256": "f342ddd996f5d36479de4899f66d7e4d97355a1f6c28c252913b399a7b9a6371",
        "url": "https://cleanmetro.co.kr/bbs/board.php?bo_table=recruit&page=1",
        "expected_notice": "[공고 제2026-17호]",
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
            "pdf_magic_valid": data.startswith(b"%PDF-"),
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

    # Reserve just one early evidence attempt for a later, potentially simpler
    # notice. A count of one and explicit time are review hints, never proof
    # of a recruitment unit or approval. Keep all other candidates in order.
    if 2 <= limit < len(candidates):
        # Reserve at most one existing evidence slot for the explicitly
        # reviewed, fingerprint-bound KNPS candidate; do not raise the budget.
        # This is evidence acquisition order, not publication ranking.
        pin = CANONICAL_REVIEW_BOARDS["a307417"]
        pinned_index = next((i for i, draft in enumerate(candidates)
                             if draft.get("notice_id") == "a307417"
                             and draft.get("source_post_sha256") == pin["source_post_sha256"]
                             and draft.get("source_detail_sha256") == pin["source_detail_sha256"]), None)
        if pinned_index is not None and pinned_index >= limit:
            candidates.insert(limit - 1, candidates.pop(pinned_index))
        elif pinned_index is None:
            for index in range(limit, len(candidates)):
                draft = candidates[index]
                fields = draft.get("official_detail_fields_for_review")
                evidence = str(draft.get("application_evidence_for_review") or "")
                if (isinstance(fields, dict)
                        and str(fields.get("recrutNope", "")) == "1"
                        and re.search(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)", evidence)):
                    candidates.insert(limit - 1, candidates.pop(index))
                    break

    def capture(draft):
        nid = draft['notice_id']
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
            # Capture the original byte digests for precisely pinned annexes.
            # A parsed page or PDF metadata alone cannot approve a manuscript.
            # This never writes to reviewed-staging or publisher queue.
            pinned = CANONICAL_REVIEW_URLS.get(nid)
            if (nid in CANONICAL_REVIEW_ANNEXES and pinned
                    and draft.get("source_post_sha256") == pinned["source_post_sha256"]
                    and draft.get("source_detail_sha256") == pinned["source_detail_sha256"]):
                receipts = []
                for annex_url in CANONICAL_REVIEW_ANNEXES[nid]:
                    try:
                        if not official_url_allowed(annex_url):
                            raise ValueError("ATTACHMENT_URL_NOT_ALLOWED")
                        evidence = fetch(annex_url)
                        if (not isinstance(evidence, dict)
                                or not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("sha256", "")))
                                or evidence.get("pdf_magic_valid") is not True
                                or evidence.get("url") != annex_url):
                            raise ValueError("ATTACHMENT_RAW_PDF_NOT_VERIFIED")
                        receipts.append({"url": annex_url, "status": "raw_pdf_sha256_captured",
                                         "sha256": evidence["sha256"],
                                         "size_bytes": evidence.get("size_bytes"),
                                         "checked_at": evidence.get("checked_at"),
                                         "semantic_review": "required"})
                    except (ValueError, OSError, urllib.error.URLError) as exc:
                        receipts.append({"url": annex_url, "status": "unverified",
                                         "block_reason": (str(exc) if isinstance(exc, ValueError)
                                                          else "ATTACHMENT_SOURCE_UNAVAILABLE")[:120]})
                item["attachment_receipts"] = receipts
                item["attachment_status"] = (
                    "all_raw_pdf_sha256_captured" if all(
                        r["status"] == "raw_pdf_sha256_captured" for r in receipts)
                    else "raw_pdf_receipts_incomplete")
                item["attachment_review_required"] = True
            # A board receipt is an independent reviewer input, not a
            # claim that later corrections are impossible. Any denial or
            # redirect remains a blocking, explicitly reported source failure.
            board = CANONICAL_REVIEW_BOARDS.get(nid)
            if (board and draft.get("source_post_sha256") == board["source_post_sha256"]
                    and draft.get("source_detail_sha256") == board["source_detail_sha256"]):
                receipt = {
                    "url": board["url"],
                    "status": "not_verified",
                    "correction_absence_verified": False,
                    "publisher_validate_entry": "not_run",
                }
                try:
                    if not official_url_allowed(board["url"]):
                        raise ValueError("OFFICIAL_RECRUITMENT_BOARD_URL_NOT_ALLOWED")
                    fetched = fetch(board["url"])
                    if (not isinstance(fetched, dict)
                            or fetched.get("url") != board["url"]
                            or not re.fullmatch(r"[0-9a-f]{64}", str(fetched.get("sha256", "")))):
                        raise ValueError("OFFICIAL_RECRUITMENT_BOARD_RECEIPT_INVALID")
                    excerpt = fetched.get("visible_text_excerpt") or ""
                    receipt.update(
                        status="board_bytes_fetched_for_independent_review",
                        sha256=fetched["sha256"],
                        size_bytes=fetched.get("size_bytes"),
                        checked_at=fetched.get("checked_at"),
                        target_notice_visible=board["expected_notice"] in excerpt,
                        semantic_review="required",
                    )
                except (ValueError, OSError, urllib.error.URLError) as exc:
                    receipt["block_reason"] = (
                        str(exc) if isinstance(exc, ValueError)
                        else "OFFICIAL_RECRUITMENT_BOARD_UNAVAILABLE"
                    )[:120]
                item["employer_recruitment_board_receipt"] = receipt
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
                host = urlsplit(str(independently_located_notice(draft) or "")).hostname
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
