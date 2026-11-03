#!/usr/bin/env python3
"""One bounded GOJOBS DESC experiment; no sort-direction or open-status claim."""
import contextlib
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gojobs
from scripts.verify_additional_apis import (
    KST, SOURCE_NAMES, contains_credential, counters, credential_forms, encoded, source_state,
)

SORT_ORDER_TESTED = "DESC"
MAX_EVIDENCE_BYTES = 262144
PROGRESS_FIELDS = {
    "verification_complete", "list_verified", "list_queries_verified", "total_count_by_filter",
    "list_count_returned", "samples", "detail_verified_count", "detail_samples",
    "source_link_counts", "observed_field_layouts", "failed_notice",
}
RESULT_FIELDS = {
    "service", "source_url", "endpoint_base", "list_endpoint", "detail_endpoint",
    "list_verified", "authentication_verified", "empty_list", "detail_status", "detail_verified",
    "detail_verified_count", "list_count_returned", "total_count_by_filter", "sample_scope",
    "full_collection", "active_status_verified", "filters", "samples", "detail_samples",
    "source_link_counts", "source_links_all_validated", "observed_field_layouts",
    "unverified_scope", "requests", "successful_responses",
}
LIST_FIELDS = {
    "id", "title", "org", "institution_type", "recruitment_type", "field_layout",
    "deadline", "registered_date", "modified_date",
}
DETAIL_FIELDS = {
    "id", "title", "institution_type", "recruitment_type", "field_layout",
    "source_links", "source_link_status", "content_present",
}


class CurrentSampleClient(gojobs.Client):
    """Reuse all strict validation, replacing only the experimental list parameter."""

    def _request(self, operation, params):
        params = dict(params)
        if operation == "list":
            params["Sort_order"] = SORT_ORDER_TESTED
        return super()._request(operation, params)


def _iso_date(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("invalid_evidence_date")
    return date.fromisoformat(value).isoformat()


def _safe_evidence(value, forbidden, *, complete):
    """Bound and project the existing adapter's already validated public evidence."""
    try:
        if not isinstance(value, dict) or len(encoded(value)) > MAX_EVIDENCE_BYTES:
            return None
        if contains_credential(value, forbidden):
            return None
        allowed = RESULT_FIELDS if complete else PROGRESS_FIELDS
        result = {name: value[name] for name in allowed if name in value}
        for name, fields, limit in (("samples", LIST_FIELDS, 10), ("detail_samples", DETAIL_FIELDS, 3)):
            rows = result.get(name)
            if not isinstance(rows, list) or len(rows) > limit:
                return None
            cleaned = []
            for row in rows:
                if not isinstance(row, dict):
                    return None
                item = {field: row[field] for field in fields if field in row}
                if (not isinstance(item.get("id"), str)
                        or not re.fullmatch(r"[1-9][0-9]{0,11}", item["id"])
                        or not isinstance(item.get("title"), str) or not 0 < len(item["title"]) <= 2000
                        or item.get("institution_type") != "g02"
                        or item.get("recruitment_type") not in {"e01", "e02"}):
                    return None
                if name == "samples":
                    if not isinstance(item.get("org"), str) or not 0 < len(item["org"]) <= 2000:
                        return None
                    for field in ("registered_date", "deadline", "modified_date"):
                        item[field] = _iso_date(item.get(field))
                cleaned.append(item)
            result[name] = cleaned
        records = {row["id"]: row for row in result["samples"]}
        details = result["detail_samples"]
        if (len(records) != len(result["samples"])
                or len({row["id"] for row in details}) != len(details)
                or result.get("list_count_returned") != len(records)
                or result.get("detail_verified_count") != len(details)):
            return None
        for item in details:
            expected = records.get(item["id"])
            if expected is None or any(item[field] != expected[field] for field in
                                       ("title", "institution_type", "recruitment_type")):
                return None
        totals = result.get("total_count_by_filter")
        if (not isinstance(totals, dict) or set(totals) - {"e01", "e02"}
                or any(type(count) is not int or not 0 <= count < 10**12 for count in totals.values())):
            return None
        if result.get("list_verified") is True and set(totals) != {"e01", "e02"}:
            return None
        for category, count in totals.items():
            if sum(row["recruitment_type"] == category for row in records.values()) != min(gojobs.PAGE_SIZE, count):
                return None
        failed = result.get("failed_notice")
        if failed is not None:
            if not isinstance(failed, dict) or failed.get("id") not in records:
                return None
            expected = records[failed["id"]]
            result["failed_notice"] = {
                "id": expected["id"], "expected_institution_type": expected["institution_type"],
                "expected_recruitment_type": expected["recruitment_type"],
            }
        if complete:
            if result.get("authentication_verified") is not True or result.get("list_verified") is not True:
                return None
            # Base Client has a static reporting value of "1". Correct only this
            # detached report to the value actually sent by our request override.
            result["filters"] = {"Instt_se": "g02", "Pblanc_ty": ["e01", "e02"],
                                 "pageNo": 1, "numOfRows": gojobs.PAGE_SIZE, "Sort_order": SORT_ORDER_TESTED}
        return json.loads(json.dumps(result, ensure_ascii=False))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _safe_diagnostic(value, forbidden):
    if not isinstance(value, dict):
        return None
    result = {}
    observed = value.get("observed_filters")
    if isinstance(observed, dict):
        codes = gojobs.INSTITUTION_CODES | gojobs.RECRUITMENT_CODES
        result["observed_filters"] = {
            name: observed.get(name) if isinstance(observed.get(name), str) and observed[name] in codes else "unknown"
            for name in ("type01", "type02")
        }
    comparison = value.get("detail_list_classification")
    if isinstance(comparison, dict):
        safe = {}
        for prefix in ("expected", "observed"):
            for field, codes in (("institution_type", gojobs.INSTITUTION_CODES),
                                 ("recruitment_type", gojobs.RECRUITMENT_CODES)):
                name = prefix + "_" + field
                item = comparison.get(name)
                safe[name] = item if isinstance(item, str) and item in codes else "unknown"
        if type(comparison.get("title_matches")) is bool:
            safe["title_matches"] = comparison["title_matches"]
        result["detail_list_classification"] = safe
    return result if result and len(encoded(result)) <= 4096 and not contains_credential(result, forbidden) else None


def date_observations(evidence, check_date):
    samples, details = evidence["samples"], evidence["detail_samples"]
    observations = {"as_of_date": check_date.isoformat(), "sample_basis": "validated_list_rows",
                    "comparison_basis": "calendar_date_only",
                    "authoritative_open_status_verified": False, "latest_order_verified": False}
    for field in ("registered_date", "deadline"):
        values = sorted(row[field] for row in samples if row.get(field) is not None)
        observations[field] = {
            "provided_count": len(values), "missing_count": len(samples) - len(values),
            "min": values[0] if values else None, "max": values[-1] if values else None,
            "year_counts": dict(sorted(Counter(value[:4] for value in values).items())),
        }
    observations["rows"] = [
        {"id": row["id"], "recruitment_type": row["recruitment_type"],
         "registered_date": row["registered_date"], "deadline": row["deadline"],
         "check_date_on_or_before_deadline": None if row["deadline"] is None else check_date.isoformat() <= row["deadline"]}
        for row in samples
    ]
    observations["deadline_on_or_after_check_date_ids"] = [
        row["id"] for row in observations["rows"] if row["check_date_on_or_before_deadline"] is True
    ]
    totals = evidence["total_count_by_filter"]
    observations["filter_observations"] = {
        category: {"query_verified": category in totals, "total_count": totals.get(category),
                   "sample_count": sum(row["recruitment_type"] == category for row in samples),
                   "detail_verified_count": sum(row["recruitment_type"] == category for row in details),
                   "records_observed": any(row["recruitment_type"] == category for row in samples)}
        for category in ("e01", "e02")
    }
    return observations


def verify(root=ROOT, *, key=None, client_factory=CurrentSampleClient, now=None):
    root = Path(root).resolve()
    output = root / "gojobs-current-sample-output"
    target = output / "report.json"
    if output.is_symlink() or target.is_symlink():
        raise ValueError("unsafe_report_target")
    if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
        raise ValueError("unsafe_report_target")
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    now = now.astimezone(KST)
    key = os.environ.get("GOJOBS_KEY", "").strip() if key is None else key.strip()
    forbidden = credential_forms([key])
    report = {"checked_at": now.isoformat(timespec="seconds"), "scope": "isolated_gojobs_desc_parameter_probe",
              "service": "gojobs", "secret_name": "GOJOBS_KEY", "key_present": bool(key),
              "status": "not_started", "authentication_verified": False,
              "sort_order_tested": SORT_ORDER_TESTED, "official_sort_mapping_verified": False,
              "sort_interpretation": "experimental_parameter_value", "latest_order_verified": False,
              "source_preserved": False, "production_data_writes": 0,
              "scheduled_collection_enabled": False, "deployment_performed": False, "mpm_requests": 0}
    sha = os.environ.get("GITHUB_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        report["code_sha"] = sha
    originals, client, evidence = {}, None, None
    try:
        originals, report["source_count_before"] = source_state(root)
        if not key:
            report.update(status="blocked", reason="missing_secret")
        else:
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    client = client_factory(key)
                    result = client.verify()
                evidence = _safe_evidence(result, forbidden, complete=True)
                if evidence is None:
                    report.update(status="failed", reason="invalid_or_unsafe_verification_report")
                else:
                    report.update(status="verified", authentication_verified=True, result=evidence)
            except Exception as error:
                code = getattr(error, "safe_code", "unexpected_error")
                if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code):
                    code = "unexpected_error"
                if contains_credential(code, forbidden):
                    code = "credential_in_response_rejected"
                report.update(status="failed", reason=code)
                diagnostic = _safe_diagnostic(getattr(client, "last_response_diagnostic", None), forbidden)
                if diagnostic is not None:
                    report["response_diagnostic"] = diagnostic
                evidence = _safe_evidence(getattr(client, "verification_progress", None), forbidden, complete=False)
                if evidence is not None:
                    report["verification_progress"] = evidence
        report["requests"] = counters(client, "request_counts")
        report["successful_responses"] = counters(client, "success_counts")
        if any(report["successful_responses"].values()):
            report["authentication_verified"] = True
            report["authentication_basis"] = "one_or_more_validated_api_responses"
        if (report["requests"].get("list", 0) > 2 or report["requests"].get("detail", 0) > 3
                or "schedule" in report["requests"]):
            report.update(status="failed", reason="unexpected_request_scope")
        if evidence is not None:
            report["date_observations"] = date_observations(evidence, now.date())
    except Exception:
        report.update(status="failed", reason="source_or_probe_validation_failed")
    try:
        after, report["source_count_after"] = source_state(root)
        report["source_preserved"] = len(originals) == len(SOURCE_NAMES) and after == originals
    except Exception:
        report["source_preserved"] = False
    report["source_sha256"] = {name: hashlib.sha256(body).hexdigest() for name, body in originals.items()}
    if not report["source_preserved"]:
        report.update(status="failed", reason="source_changed_or_unreadable")
    if contains_credential(report, forbidden):
        report = {"status": "failed", "reason": "credential_in_report_rejected",
                  "source_preserved": report["source_preserved"]}
    output.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded(report))
    return report


def main():
    try:
        report = verify()
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["status"] == "verified" and report["source_preserved"] else 2
    except Exception:
        print('{"status":"failed","reason":"report_write_failed"}')
        return 2


if __name__ == "__main__":
    sys.exit(main())
