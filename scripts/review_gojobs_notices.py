#!/usr/bin/env python3
"""Offline review of preserved GOJOBS evidence; no API access or publication."""
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gojobs_notice_safety import classify_notice

KST = timezone(timedelta(hours=9))
EVIDENCE_PATH = "docs/evidence/gojobs-current-sample-20261103.json"
SOURCE_PATHS = ("alio.json", "alio-detail.json")
NON_RECRUITMENT = {"합격자 발표", "등록 안내", "시험 안내", "취소 공고", "접수 종료"}


def _date(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("invalid_evidence_date")
    return date.fromisoformat(value)


def _identity(row):
    value = row.get("id") if isinstance(row, dict) else None
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,11}", value):
        raise ValueError("invalid_evidence_identity")
    return value


def triage(evidence, *, as_of):
    """Keep source integrity, notice purpose and application eligibility separate."""
    check_date = _date(as_of)
    if check_date is None or not isinstance(evidence, dict):
        raise ValueError("invalid_evidence")
    observations = []
    for name in ("desc_experiment", "last_page_experiment"):
        event = evidence[name]
        report = event["report"]
        if (report.get("authentication_verified") is not True
                or report.get("source_preserved") is not True
                or not re.fullmatch(r"[0-9a-f]{40}", event.get("code_sha", ""))):
            raise ValueError("unverified_evidence")
        progress = report.get("result") if report.get("status") == "verified" else report.get("verification_progress")
        if not isinstance(progress, dict) or progress.get("list_verified") is not True:
            raise ValueError("unverified_list_evidence")
        rows, details = progress.get("samples"), progress.get("detail_samples")
        if (not isinstance(rows, list) or len(rows) > 10
                or not isinstance(details, list) or len(details) > 3):
            raise ValueError("invalid_evidence_scope")
        ids = [_identity(row) for row in rows]
        detail_ids = [_identity(row) for row in details]
        if (len(set(ids)) != len(ids) or len(set(detail_ids)) != len(detail_ids)
                or set(detail_ids) - set(ids)
                or progress.get("list_count_returned") != len(rows)
                or progress.get("detail_verified_count") != len(details)):
            raise ValueError("inconsistent_evidence")
        by_id = dict(zip(detail_ids, details))
        failure = progress.get("failed_notice")
        failed_id = _identity(failure) if failure is not None else None
        if failed_id is not None and failed_id not in ids:
            raise ValueError("unmatched_evidence_failure")
        for row in rows:
            identity = row["id"]
            title, org = row.get("title"), row.get("org")
            if (not isinstance(title, str) or not 0 < len(title) <= 2000
                    or not isinstance(org, str) or not 0 < len(org) <= 2000
                    or row.get("institution_type") != "g02"
                    or row.get("recruitment_type") not in {"e01", "e02"}):
                raise ValueError("invalid_list_evidence")
            deadline = _date(row.get("deadline"))
            registered = _date(row.get("registered_date"))
            detail = by_id.get(identity)
            detail_matches = detail is not None and all(
                detail.get(field) == row.get(field)
                for field in ("id", "title", "institution_type", "recruitment_type"))
            source_integrity = failed_id != identity and detail_matches
            classification = classify_notice(
                title, official_verified=False, application_open_verified=False,
                application_closed_verified=False, official_text=None,
                as_of=as_of, deadline=row.get("deadline"))
            if classification.get("recruiting") is not False:
                raise ValueError("unsafe_unverified_candidate_promotion")
            if identity == failed_id or (detail is not None and not detail_matches):
                decision, reason = "blocked_source_integrity", "source_integrity_failed"
            elif detail is None:
                decision, reason = "needs_review", "detail_unverified"
            elif classification.get("category") in NON_RECRUITMENT:
                decision, reason = "excluded_non_recruitment", classification["reason"]
            else:
                decision, reason = "needs_review", "official_source_and_application_period_unverified"
            observations.append({
                "source": "gojobs", "id": identity, "title": title, "organization": org,
                "evidence_section": name, "evidence_code_sha": event["code_sha"],
                "registered_date": registered.isoformat() if registered else None,
                "api_deadline": deadline.isoformat() if deadline else None,
                "api_deadline_elapsed": deadline < check_date if deadline else None,
                "source_integrity_verified": source_integrity,
                "classification": classification, "decision": decision, "reason": reason,
                "official_source_verified": False, "application_period_verified": False,
                "new_application_eligible": False,
            })
    return observations


def review(root=ROOT, *, now=None):
    root = Path(root).resolve()
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    now = now.astimezone(KST)
    evidence_path = root / EVIDENCE_PATH
    original = {name: (root / name).read_bytes() for name in SOURCE_PATHS}
    original_count = len(json.loads(original["alio.json"])["posts"])
    evidence_bytes = evidence_path.read_bytes()
    if len(evidence_bytes) > 524288:
        raise ValueError("evidence_too_large")
    records = triage(json.loads(evidence_bytes), as_of=now.date().isoformat())
    after = {name: (root / name).read_bytes() for name in SOURCE_PATHS}
    report = {
        "checked_at": now.isoformat(timespec="seconds"), "scope": "offline_gojobs_notice_review",
        "status": "verified" if after == original and evidence_path.read_bytes() == evidence_bytes else "failed",
        "evidence_path": EVIDENCE_PATH, "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "api_requests": 0, "api_authentication_retested": False,
        "observation_count": len(records), "unique_notice_count": len({r["id"] for r in records}),
        "decisions": dict(sorted(Counter(r["decision"] for r in records).items())),
        "categories": dict(sorted(Counter(r["classification"]["category"] for r in records).items())),
        "new_application_candidate_count": 0, "records": records,
        "source_count_before": original_count, "source_count_after": len(json.loads(after["alio.json"])["posts"]),
        "source_preserved": after == original, "evidence_preserved": evidence_path.read_bytes() == evidence_bytes,
        "source_sha256": {name: hashlib.sha256(body).hexdigest() for name, body in original.items()},
        "production_data_writes": 0, "deployment_performed": False, "scheduled_collection_enabled": False,
    }
    sha = os.environ.get("GITHUB_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        report["code_sha"] = sha
    output = root / "gojobs-notice-review-output"
    target = output / "report.json"
    if output.is_symlink() or target.is_symlink() or (target.exists() and target.stat().st_nlink != 1):
        raise ValueError("unsafe_report_target")
    output.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    try:
        result = review()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        sys.exit(0 if result["status"] == "verified" and result["source_preserved"] else 2)
    except Exception:
        print('{"status":"failed","reason":"offline_review_validation_failed"}')
        sys.exit(2)
