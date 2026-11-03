#!/usr/bin/env python3
"""Read reachable Git blobs and report credential findings without their values."""
import argparse
import html
import json
import os
import re
import subprocess
import urllib.parse
from pathlib import Path

KEY_NAMES = ("ALIO_KEY", "DATA_GO_KR_KEY", "GOJOBS_KEY", "MPM_EXAM_KEY")
MAX_BLOB_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_REPORTED_FINDINGS = 1000
PATTERNS = {
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,255}|github_pat_[A-Za-z0-9_]{40,255})\b"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----[\s\S]{40,20000}?-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "hardcoded_api_credential": re.compile(
        rb"(?im)\b(?:ALIO_KEY|DATA_GO_KR_KEY|GOJOBS_KEY|MPM_EXAM_KEY|serviceKey|api_key|client_secret|access_token)\b['\"]?[\t ]*[:=][\t ]*['\"]([A-Za-z0-9%/+_=.-]{16,})['\"]"
    ),
}


class AuditError(Exception):
    pass


def git(repo, *args, input=None):
    result = subprocess.run(["git", "-C", str(repo), *args], input=input,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise AuditError("git_read_failed")
    return result.stdout


def forms(value):
    if not isinstance(value, str) or len(value.strip()) < 16:
        return set()
    raw = value.strip()
    decoded = urllib.parse.unquote(raw)
    values = {raw, decoded}
    for text in (raw, decoded):
        values.update((urllib.parse.quote(text, safe=""), urllib.parse.quote_plus(text), html.escape(text)))
    return {text.encode("utf-8").lower() for text in values if text}


def generic_categories(payload):
    categories = set()
    for category, pattern in PATTERNS.items():
        for match in pattern.finditer(payload):
            candidate = match.group(1) if category == "hardcoded_api_credential" else match.group(0)
            upper = candidate.upper()
            # Explicit example/test labels and AWS's documented example are not credentials.
            if category != "private_key" and (upper.startswith((b"TEST_", b"FAKE_", b"DUMMY_", b"EXAMPLE_", b"SENSITIVE_"))
                    or upper.endswith(b"EXAMPLE") or len(set(candidate)) == 1):
                continue
            categories.add(category)
            break
    return categories


def safe_path(path, secrets):
    encoded = path.encode("utf-8", errors="replace")
    lowered = encoded.lower()
    if any(value in lowered for values in secrets.values() for value in values) or generic_categories(encoded):
        return "[redacted-path]"
    return "".join(char if char.isprintable() else "?" for char in path)[:512]


def audit(repo, credentials):
    repo = Path(repo).resolve()
    secrets = {name: forms(credentials.get(name, "")) for name in KEY_NAMES}
    report = {
        "schema_version": 1,
        "scope": "all_reachable_git_blob_history",
        "key_present": {name: bool(secrets[name]) for name in KEY_NAMES},
        "registered_credential_coverage_complete": all(secrets.values()),
        "history_scan_complete": False,
        "commits_scanned": 0, "blobs_scanned": 0, "bytes_scanned": 0,
        "finding_count": 0, "findings": [], "status": "not_started",
        "limits": ["Registered credential values and high-signal token/private-key patterns only; not a guarantee that every unknown secret type is absent."]
    }
    process = None
    try:
        head = git(repo, "rev-parse", "HEAD").decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", head):
            raise AuditError("invalid_git_head")
        report["head_sha"] = head
        report["commits_scanned"] = int(git(repo, "rev-list", "--count", "--all"))
        objects = {}
        for line in git(repo, "rev-list", "--objects", "--all").decode("utf-8", errors="replace").splitlines():
            object_id, _, path = line.partition(" ")
            if not re.fullmatch(r"[0-9a-f]{40,64}", object_id):
                raise AuditError("invalid_git_object")
            objects.setdefault(object_id, path)
        if not objects:
            raise AuditError("empty_git_history")
        inventory = git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                        input=("\n".join(objects) + "\n").encode("ascii")).decode("ascii").splitlines()
        if len(inventory) != len(objects):
            raise AuditError("incomplete_git_inventory")
        blobs = []
        for line in inventory:
            fields = line.split()
            if len(fields) != 3 or fields[0] not in objects or not fields[2].isdigit():
                raise AuditError("invalid_git_inventory")
            if fields[1] == "blob":
                size = int(fields[2])
                if size > MAX_BLOB_BYTES:
                    raise AuditError("blob_exceeds_scan_limit")
                blobs.append((fields[0], size))
        if sum(size for _, size in blobs) > MAX_TOTAL_BYTES:
            raise AuditError("history_exceeds_scan_limit")
        process = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        for object_id, expected_size in blobs:
            process.stdin.write((object_id + "\n").encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii").strip().split()
            if header != [object_id, "blob", str(expected_size)]:
                raise AuditError("git_blob_header_mismatch")
            payload = process.stdout.read(expected_size)
            if len(payload) != expected_size or process.stdout.read(1) != b"\n":
                raise AuditError("incomplete_git_blob")
            report["blobs_scanned"] += 1
            report["bytes_scanned"] += len(payload)
            lowered = payload.lower()
            categories = generic_categories(payload)
            for name, values in secrets.items():
                if any(value in lowered for value in values):
                    categories.add("registered_secret_" + name)
            for category in sorted(categories):
                report["finding_count"] += 1
                if len(report["findings"]) < MAX_REPORTED_FINDINGS:
                    report["findings"].append({"blob_sha": object_id, "path": safe_path(objects[object_id], secrets), "category": category})
        process.stdin.close()
        if process.wait(timeout=10):
            raise AuditError("git_blob_reader_failed")
        process.stdout.close()
        process = None
        report["history_scan_complete"] = True
        report["findings_truncated"] = report["finding_count"] > len(report["findings"])
        report["status"] = "passed" if report["registered_credential_coverage_complete"] and not report["finding_count"] else "blocked"
        if not report["registered_credential_coverage_complete"]:
            report["reason"] = "registered_credentials_missing_or_short"
    except Exception as error:
        report.update(status="failed", reason=str(error) if isinstance(error, AuditError) else "audit_internal_error")
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
    # Final guard: an unusual path or external Git response must never leak a known value.
    serialized = json.dumps(report, ensure_ascii=False).encode("utf-8").lower()
    if any(value in serialized for values in secrets.values() for value in values):
        return {"status": "failed", "reason": "unsafe_report_rejected", "history_scan_complete": False}
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", default="public-history-audit-output/report.json")
    args = parser.parse_args()
    report = audit(args.repo, {name: os.environ.get(name, "") for name in KEY_NAMES})
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
