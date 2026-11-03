#!/usr/bin/env python3
"""Read two new APIs into a report without changing CareerPick snapshots."""
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
KST = timezone(timedelta(hours=9))
SOURCE_NAMES = ("alio.json", "alio-detail.json")
SERVICES = {"gojobs": "GOJOBS_KEY", "mpm_exam": "MPM_EXAM_KEY"}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def credential_forms(keys):
    forms = set()
    for value in keys:
        if not isinstance(value, str) or not value.strip():
            continue
        raw = value.strip()
        decoded = urllib.parse.unquote(raw)
        forms.update((raw, decoded, urllib.parse.quote(decoded, safe=""),
                      urllib.parse.quote_plus(decoded),
                      urllib.parse.quote(raw, safe="")))
    return {value.encode("utf-8") for value in forms if value}


def contains_credential(value, forbidden):
    # Test both JSON encodings, including escaped non-ASCII response text.
    variants = (encoded(value), json.dumps(value, ensure_ascii=True).encode("utf-8"))
    return any(secret in content for secret in forbidden for content in variants)


def source_state(root):
    originals = {name: (root / name).read_bytes() for name in SOURCE_NAMES}
    cards = json.loads(originals["alio.json"])
    details = json.loads(originals["alio-detail.json"])
    rows = cards["posts"]
    if not isinstance(rows, list) or not isinstance(details, dict):
        raise ValueError("invalid_source_shape")
    identities = [row["id"] for row in rows]
    if (any(not isinstance(item, str) for item in identities)
            or len(set(identities)) != len(identities)):
        raise ValueError("invalid_source_identity")
    return originals, len(rows)


def counters(client, name):
    value = getattr(client, name, {}) if client else {}
    if not isinstance(value, dict):
        return {}
    return {key: count for key, count in value.items()
            if key in {"list", "detail", "schedule"}
            and isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 100}


def default_factories():
    from gojobs import Client as JobsClient
    from mpm_exam import Client as ExamClient
    return {"gojobs": JobsClient, "mpm_exam": ExamClient}


def verify(root=ROOT, output=None, *, keys=None, factories=None, now=None):
    root = Path(root).resolve()
    output = Path(output).resolve() if output is not None else root / "additional-api-check-output"
    # Refuse source/output path overlap; only a new report file is written.
    if output in {root / name for name in SOURCE_NAMES}:
        raise ValueError("invalid_output_directory")
    now = now or datetime.now(KST)
    keys = ({name: os.environ.get(secret, "").strip()
             for name, secret in SERVICES.items()} if keys is None else dict(keys))
    forbidden = credential_forms(keys.values())
    report = {
        "checked_at": now.astimezone(KST).isoformat(timespec="seconds"),
        "scope": "isolated_registration_check",
        "status": "not_started",
        "services": {},
        "source_preserved": False,
        "production_data_writes": 0,
        "scheduled_collection_enabled": False,
        "deployment_performed": False,
    }
    sha = os.environ.get("GITHUB_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        report["code_sha"] = sha
    originals = {}
    try:
        originals, report["source_count_before"] = source_state(root)
        factories = factories if factories is not None else default_factories()
        for name, secret_name in SERVICES.items():
            key = keys.get(name, "")
            state = {"secret_name": secret_name, "key_present": bool(key),
                     "status": "not_started", "authentication_verified": False}
            client = None
            try:
                if not key:
                    state.update(status="blocked", reason="missing_secret")
                else:
                    # Adapters must not log; suppress accidental dependency output too.
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        client = factories[name](key)
                        result = client.verify()
                    if not isinstance(result, dict):
                        state.update(status="failed", reason="invalid_verification_report")
                    elif contains_credential(result, forbidden):
                        state.update(status="failed", reason="credential_in_response_rejected")
                    else:
                        state.update(status="verified", authentication_verified=True, result=result)
            except Exception as error:
                # Never serialize exception strings, request objects or raw response bodies.
                safe_code = getattr(error, "safe_code", "unexpected_error")
                if not isinstance(safe_code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", safe_code):
                    safe_code = "unexpected_error"
                if contains_credential(safe_code, forbidden):
                    safe_code = "credential_in_response_rejected"
                state.update(status="failed", reason=safe_code)
                diagnostic = getattr(client, "last_response_diagnostic", None)
                if isinstance(diagnostic, dict):
                    allowed = {"field_types", "observed_filters", "http_status", "result_code",
                               "detail_list_classification"}
                    diagnostic = {k: v for k, v in diagnostic.items() if k in allowed}
                    if diagnostic and len(encoded(diagnostic)) <= 4096 and not contains_credential(diagnostic, forbidden):
                        state["response_diagnostic"] = diagnostic
                progress = getattr(client, "verification_progress", None)
                if isinstance(progress, dict):
                    allowed = {"verification_complete", "list_verified", "list_queries_verified",
                               "total_count_by_filter", "list_count_returned", "samples",
                               "detail_verified_count", "detail_samples", "source_link_counts",
                               "observed_field_layouts", "failed_notice"}
                    progress = {k: v for k, v in progress.items() if k in allowed}
                    if len(encoded(progress)) > 65536:
                        # Keep bounded identity/counter evidence even when a
                        # validated public title or source URL is unusually long.
                        progress = {k: v for k, v in progress.items()
                                    if k not in {"samples", "detail_samples"}}
                        state["verification_progress_truncated"] = True
                    if (progress and len(encoded(progress)) <= 65536
                            and not contains_credential(progress, forbidden)):
                        state["verification_progress"] = progress
            state["requests"] = counters(client, "request_counts")
            state["successful_responses"] = counters(client, "success_counts")
            # A later record failure does not undo an earlier authenticated,
            # validated response. Keep overall failure separate from this fact.
            if any(state["successful_responses"].values()):
                state["authentication_verified"] = True
                state["authentication_basis"] = "one_or_more_validated_api_responses"
            report["services"][name] = state
        report["status"] = ("verified" if all(
            value["status"] == "verified" for value in report["services"].values())
            else "partial_or_blocked")
    except Exception:
        report.update(status="failed", reason="source_or_runner_validation_failed")
    try:
        after, after_count = source_state(root)
        report["source_count_after"] = after_count
        report["source_preserved"] = len(originals) == len(SOURCE_NAMES) and after == originals
    except Exception:
        report["source_preserved"] = False
    report["source_sha256"] = {name: hashlib.sha256(body).hexdigest()
                               for name, body in originals.items()}
    if not report["source_preserved"]:
        report.update(status="failed", reason="source_changed_or_unreadable")
    if contains_credential(report, forbidden):
        report = {"status": "failed", "reason": "credential_in_report_rejected",
                  "source_preserved": report["source_preserved"]}
    output.mkdir(parents=True, exist_ok=True)
    target = output / "report.json"
    if target.is_symlink():
        raise ValueError("unsafe_report_target")
    target.write_bytes(encoded(report))
    return report


if __name__ == "__main__":
    try:
        result = verify()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        sys.exit(0 if result["status"] == "verified" and result["source_preserved"] else 2)
    except Exception:
        print('{"status":"failed","reason":"report_write_failed"}')
        sys.exit(2)
