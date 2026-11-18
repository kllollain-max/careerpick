#!/usr/bin/env python3
"""Read-only, fail-closed official PDF + applicant source inspection for a307061.
No ingestion, Meta POST, system writes, or review timestamp updates.
"""
import hashlib
import json
import os
import pathlib
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

import fitz
import requests
from bs4 import BeautifulSoup

OUT = pathlib.Path("official-reviewed-evidence/a307061")
OUT.mkdir(parents=True, exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; CareerPickOfficialReview/1.0)"})
PORTAL = "https://recruit.posid.or.kr/RLISTV.inbus?idx=1&seq=R26010&type=0"
GOJOBS = "https://www.gojobs.go.kr/apmView.do?empmnsn=308740"
ALIO = "https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx=307061"
ATTACHMENTS = [
    ("gojobs", "https://www.gojobs.go.kr/downFile.do?" + urlencode({
        "filenm": "2026년 10차 공개채용 공고문.pdf",
        "saveGbn": "employ/우체국금융개발원",
        "uuid": "1083414160359152",
    })),
    ("alio", "https://www.alio.go.kr/download/download.json?fileNo=3087571"),
]
report = {
    "notice_id": "a307061",
    "review_attempted_at_utc": datetime.now(timezone.utc).isoformat(),
    "sources": [],
    "attachments": [],
    "unit_from_official_gojobs": False,
    "deadline_from_employer_portal": False,
    "attachment_semantic_review": False,
    "approved": False,
    "cas_registered": False,
    "meta_posted": False,
}
def save():
    (OUT / "receipt.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

for name, url in (("employer_portal", PORTAL), ("gojobs_official", GOJOBS), ("alio_official", ALIO)):
    item = {"name": name, "url": url}
    try:
        resp = SESSION.get(url, timeout=25)
        resp.raise_for_status()
        text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
        item.update({"status": resp.status_code, "bytes": len(resp.content),
            "sha256": hashlib.sha256(resp.content).hexdigest(),
            "visible_text_chars": len(text)})
        (OUT / (name + ".txt")).write_text(text, encoding="utf-8")
        if name == "employer_portal":
            report["deadline_from_employer_portal"] = bool(
                "2026-11-30" in text and "18:00" in text and "2026년 10차" in text)
        if name == "gojobs_official":
            report["unit_from_official_gojobs"] = bool(
                "보험고객상담" in text and "20명" in text and
                "예금고객상담" in text and "15명" in text and
                "대구" in text and "16명" in text)
    except Exception as exc:
        item["error"] = type(exc).__name__ + ": " + str(exc)[:250]
    report["sources"].append(item)

for name, url in ATTACHMENTS:
    item = {"name": name, "url": url}
    try:
        resp = SESSION.get(url, timeout=35)
        item["status"] = resp.status_code
        item["content_type"] = resp.headers.get("Content-Type", "")
        if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
            item["error"] = "NOT_A_VALID_PDF_RESPONSE"
        else:
            pdf_bytes = resp.content
            item["bytes"] = len(pdf_bytes)
            item["sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
            pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
            full_text = "\n".join(p.get_text(sort=True) for p in pdf)
            item["pages"] = len(pdf)
            item["text_chars"] = len(full_text)
            item["selection_contexts"] = [
                full_text[max(0, m.start()-160):min(len(full_text), m.end()+240)]
                for m in list(re.finditer(r"보험고객상담|예금고객상담|11[.]30|11월 30일", full_text))[:18]
            ]
            item["semantic_unit_and_deadline_verified"] = bool(
                "보험고객상담" in full_text and
                re.search(r"20\s*명", full_text) and
                re.search(r"11\s*[.월]\s*30", full_text))
            (OUT / (name + "-official.pdf")).write_bytes(pdf_bytes)
            (OUT / (name + "-extracted.txt")).write_text(full_text, encoding="utf-8")
            report["attachment_semantic_review"] |= item["semantic_unit_and_deadline_verified"]
            pdf.close()
    except Exception as exc:
        item["error"] = type(exc).__name__ + ": " + str(exc)[:250]
    report["attachments"].append(item)

report["independent_read_checks_passed"] = all((
    report["unit_from_official_gojobs"], report["deadline_from_employer_portal"],
    report["attachment_semantic_review"]))
report["next_step"] = ("Validate exact source, employer correction/cancellation and candidate v5 "
    "against latest operational queue, main posted records, official 24h freshness and CAS. "
    "Do not approve from this receipt alone.")
save()
print("OFFICIAL_A307061_RECEIPT=" + json.dumps(report, ensure_ascii=False))
if not report["independent_read_checks_passed"]:
    raise SystemExit("HOLD: official attachment or primary source semantic review incomplete; no ingest, no publish")
