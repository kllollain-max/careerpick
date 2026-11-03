#!/usr/bin/env python3
"""Review unexpired archived notices absent from the current official list."""
import hashlib
import json
import os
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alio
from data_go_kr import APIError, Client
from scripts.verify_data_go_kr_live import encoded

ROOT = Path(__file__).resolve().parents[1]
MAX_DETAIL_REVIEWS = 10
SOURCES = ("alio.json", "alio-detail.json")


def audit(root=ROOT, output=None, *, key=None, client_factory=Client, now=None):
    root = Path(root)
    output = Path(output) if output else root / "alio-absence-review"
    output.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(alio.KST)
    key = os.environ.get("DATA_GO_KR_KEY", "").strip() if key is None else key.strip()
    originals = {n: (root / n).read_bytes() for n in SOURCES}
    posts = {p["id"]: p for p in json.loads(originals["alio.json"])["posts"]}
    report = {"status": "not_started", "checked_at": now.isoformat(timespec="seconds"),
              "key_present": bool(key), "source_count": len(posts), "reviews": [],
              "classification_rule": "Missing-list membership, missing detail, or null ongoingYn alone never proves closure"}
    details, client = {}, None
    try:
        if not key:
            raise APIError("missing_key")
        client = client_factory(key)
        live = client.collect_list()
        live_ids = {"a" + str(p["recrutPblntSn"]) for p in live}
        absent = posts.keys() - live_ids
        expired = {i for i in absent if posts[i].get("due")
                   and datetime.fromisoformat(posts[i]["due"]) < now}
        targets = sorted(absent - expired)
        report.update(live_unique=len(live_ids), absent_total=len(absent),
                      absent_date_expired=len(expired), absent_unexpired=len(targets), target_ids=targets)
        if len(targets) > MAX_DETAIL_REVIEWS:
            report.update(status="review_limit_preserved", reason="more_than_10_unexpired_absences")
        else:
            for identity in targets:
                old = posts[identity]
                review = {"id": identity, "title": old["title"], "org": old.get("org"),
                          "stored_deadline": old.get("due"), "official_url": old["url"],
                          "classification": "unresolved", "official_ongoing": None}
                try:
                    detail = client.detail(identity[1:])
                except APIError as error:
                    if error.safe_code == "api_result_3":
                        review["detail_status"] = "no_data"
                    elif error.safe_code in {"unexpected_envelope_fields", "invalid_detail_shape",
                                             "invalid_envelope", "detail_identity_mismatch", "invalid_notice_id"}:
                        review["detail_status"] = "unverified_response"
                        review["api_error"] = error.safe_code
                        if getattr(client, "last_response_diagnostic", None):
                            review["response_diagnostic"] = client.last_response_diagnostic
                    else:
                        raise
                else:
                    details[identity] = detail
                    end = alio.ymd(detail.get("pbancEndYmd"))
                    if end is None:
                        raise APIError("invalid_detail_shape")
                    ongoing = detail.get("ongoingYn")
                    ongoing = ongoing if ongoing in ("Y", "N") else None
                    review.update(detail_status="available", official_deadline=end.date().isoformat(),
                                  official_ongoing=ongoing,
                                  files_count=len(detail.get("files") or []),
                                  steps_count=len(detail.get("steps") or []))
                    if end.replace(hour=23, minute=59, second=59) < now:
                        review["classification"] = "official_deadline_elapsed"
                    elif ongoing == "N":
                        review["classification"] = "official_not_ongoing"
                    elif ongoing == "Y":
                        review["classification"] = "official_ongoing_list_discrepancy"
                report["reviews"].append(review)
            report["status"] = "reviewed"
        report["confirmed_not_ongoing"] = sum(r["classification"] in (
            "official_deadline_elapsed", "official_not_ongoing") for r in report["reviews"])
        report["unresolved"] = sum(r["classification"] == "unresolved" for r in report["reviews"])
    except APIError as error:
        report.update(status="failed_preserved", reason=error.safe_code)
    except Exception as error:
        report.update(status="failed_preserved", reason="unexpected_error", error_type=type(error).__name__)
    report["requests"] = dict(client.request_counts) if client else {"list": 0, "detail": 0}
    report["successful_responses"] = dict(client.success_counts) if client else {"list": 0, "detail": 0}
    if report["status"] == "failed_preserved" and client and getattr(client, "last_response_diagnostic", None):
        report["response_diagnostic"] = client.last_response_diagnostic
    report["source_preserved"] = all((root / n).read_bytes() == b for n, b in originals.items())
    report["source_sha256"] = {n: hashlib.sha256(b).hexdigest() for n, b in originals.items()}
    if not report["source_preserved"]:
        report.update(status="failed_preserved", reason="source_changed_during_review")
    raw_key = urllib.parse.unquote(key)
    forbidden = {key, raw_key, urllib.parse.quote(raw_key, safe=""), urllib.parse.quote_plus(raw_key)}
    content = encoded({"report": report, "details": details})
    if any(t and t.encode() in content for t in forbidden):
        report = {"status": "failed_preserved", "reason": "credential_in_response_rejected",
                  "source_preserved": report["source_preserved"]}
        details = {}
    if report["status"] == "reviewed":
        (output / "detail-evidence.json").write_bytes(encoded(details))
    (output / "report.json").write_bytes(encoded(report))
    return report


if __name__ == "__main__":
    report = audit()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    sys.exit(0 if report["status"] == "reviewed" and report["source_preserved"] else 2)
