#!/usr/bin/env python3
"""Prepare a reviewable public-API candidate without replacing website data.

The default uses preserved evidence only. --live-exam explicitly reads the
pinned MPM dataset once through its verified collector; it never reads GOJOBS.
Use a fresh checkout/output directory for each candidate so failed work cannot
leave an older candidate looking like a successful result of the new run.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mpm_exam
from scripts.review_gojobs_notices import EVIDENCE_PATH, triage

KST = timezone(timedelta(hours=9))
EXAM_PATH = "data/civil-service/2026.json"
MANIFEST_PATH = "data/civil-service/years.json"
OUTPUT_NAME = "additional-api-candidate-output"
PRESERVED = ("alio.json", "alio-detail.json", EXAM_PATH, MANIFEST_PATH, EVIDENCE_PATH)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("invalid_source_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid_source_timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError("source_timezone_required")
    return parsed


def display_records(records):
    """Translate only already validated dates to the existing page's format."""
    result = []
    for source in records:
        row = dict(source)
        for field in mpm_exam.DATE_FIELDS:
            dates, _ = mpm_exam._date_tokens(row[field])
            if len(dates) > 2:
                raise ValueError("unsupported_schedule_range")
            if len(dates) == 2:
                parts = re.split(r"[~∼～–—]", row[field])
                if (len(parts) != 2 or "," in row[field]
                        or any(len(mpm_exam._date_tokens(part)[0]) != 1 for part in parts)):
                    raise ValueError("unsupported_schedule_range")
            row[field] = "~".join(dates)
        result.append(row)
    return result


def preview(report, notices):
    esc = lambda value: html.escape(str(value), quote=True)
    labels = {"excluded_non_recruitment": "신규 모집 대상 제외", "blocked_source_integrity": "원본 분류 불일치", "needs_review": "추가 확인 필요"}
    rows = "".join(
        "<tr><td>" + esc(row["id"]) + "</td><td>" + esc(row["title"]) + "</td><td>" +
        esc(row["api_deadline"] or "미확인") + "</td><td>" + esc(labels[row["decision"]]) + "</td></tr>"
        for row in notices)
    source_time = timestamp(report["mpm_exam"]["retrieved_at"]).astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    mode = "보존된 자료로 만든 검토본" if report["mode"] == "offline" else "수동 API 조회로 만든 검토본"
    return ("<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>공공 API 연결 검토 | 커리어픽</title><style>body{margin:0;background:#f5f7fb;color:#18253d;font:16px/1.7 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:24px 16px}section{background:white;border:1px solid #dfe5ee;border-radius:14px;padding:20px;margin:18px 0}h1{font-size:1.8rem}h2{font-size:1.2rem}a{color:#2448b9}.muted{color:#526174}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.95rem}th,td{border-bottom:1px solid #e5e9f1;padding:12px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th:first-child{min-width:54px}th:nth-child(3){min-width:88px}th:last-child{min-width:92px}p{overflow-wrap:anywhere}@media(max-width:600px){section{padding:14px}h1{font-size:1.45rem}.table-wrap{overflow:visible}table,tbody,tr,td{display:block}thead{display:none}tr{padding:14px 0;border-bottom:1px solid #e5e9f1}td{border:0;padding:3px 0;font-size:.9rem;min-width:0}td:nth-child(2){margin:7px 0;font-size:1rem;font-weight:600;line-height:1.6}td:first-child::before{content:\"공고 ID: \";color:#526174}td:nth-child(3)::before{content:\"API 마감일: \";color:#526174}td:last-child::before{content:\"처리: \";color:#526174}}</style><main>"
        "<h1>공공 API 연결 검토</h1><p class=\"muted\">" + mode + " · 운영 반영 전 확인용</p>"
        "<section><h2>국가공무원 시험일정</h2><p><strong>" + str(report["mpm_exam"]["records"]) +
        "개 시험단계 · " + str(report["mpm_exam"]["distinct_exam_names"]) + "개 시험</strong></p><p>자료 조회 기준: " +
        esc(source_time) + "</p><p>접수 상태는 저장된 연간 일정으로 계산합니다. 변경 공고와 실제 접수 가능 여부는 공식 채용시스템에서 확인하세요.</p>"
        "<p><a href=\"civil-service-exams.html\">시험일정 화면 열기</a></p></section>"
        "<section><h2>나라일터 공고 검토</h2><p>검토 " + str(len(notices)) +
        "건 · 신규 지원 가능 자동 인정 <strong>0건</strong></p><p>이번 표본에서 공식 원문과 현재 접수 기간을 모두 확인한 공고는 없습니다. 전체 지자체의 진행 채용이 없다는 뜻은 아닙니다.</p>"
        "<div class=\"table-wrap\"><table><thead><tr><th>공고 ID</th><th>제목</th><th>API 마감일</th><th>처리</th></tr></thead><tbody>" +
        rows + "</tbody></table></div></section><p class=\"muted\">기존 공고 " + str(report["source_count_before"]) +
        "건과 원본 일정은 유지됩니다. 이 검토본을 만든 시각이 원본 자료를 새로 조회한 시각은 아닙니다.</p></main></html>\n")


def build(root=ROOT, *, live_exam=False, now=None, key=None, client_factory=None):
    root = Path(root).resolve()
    if type(live_exam) is not bool:
        raise ValueError("invalid_mode")
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    now = now.astimezone(KST)
    output = root / OUTPUT_NAME
    if output.exists() or output.is_symlink():
        raise ValueError("candidate_output_already_exists")
    originals = {name: (root / name).read_bytes() for name in PRESERVED}
    before_count = len(json.loads(originals["alio.json"])["posts"])
    snapshot = json.loads(originals[EXAM_PATH])
    manifest = json.loads(originals[MANIFEST_PATH])
    if (snapshot.get("source") != mpm_exam.DATASET_NAME or snapshot.get("source_url") != mpm_exam.SOURCE_URL
            or manifest.get("latest_year") != 2026 or not isinstance(manifest.get("years"), list)
            or len(manifest["years"]) != 1 or manifest["years"][0].get("year") != 2026
            or manifest["years"][0].get("path") != EXAM_PATH
            or manifest["years"][0].get("records") != snapshot.get("count")):
        raise ValueError("unverified_year_manifest")
    if timestamp(snapshot.get("retrieved_at")) > now:
        raise ValueError("future_source_timestamp")
    # Check the preserved source even when preparing a fresh API candidate.
    previous = mpm_exam.validate_records(snapshot.get("records"), expected_count=snapshot.get("count"))
    verification, request_count = None, 0
    if live_exam:
        secret = os.environ.get("MPM_EXAM_KEY", "") if key is None else key
        client = (client_factory or mpm_exam.Client)(secret)
        collected = client.collect()
        verification = collected["verification"]
        if (verification.get("authentication_verified") is not True
                or verification.get("list_verified") is not True
                or verification.get("dataset_year") != 2026):
            raise ValueError("unverified_exam_candidate")
        validated = mpm_exam.validate_records(collected["records"], expected_count=verification.get("total_rows"))
        request_count = client.request_counts["list"]
        if type(request_count) is not int or not 1 <= request_count <= mpm_exam.MAX_PAGES:
            raise ValueError("invalid_request_count")
        retrieved_at = now.isoformat(timespec="seconds")
    else:
        validated, retrieved_at = previous, snapshot["retrieved_at"]
    records, meta = validated["records"], validated["meta"]
    if len(originals[EVIDENCE_PATH]) > 524288:
        raise ValueError("evidence_too_large")
    notices = triage(json.loads(originals[EVIDENCE_PATH]), as_of=now.date().isoformat())
    if any(row["new_application_eligible"] is not False for row in notices):
        raise ValueError("unverified_gojobs_candidate")
    candidate = {"source": mpm_exam.DATASET_NAME, "source_url": mpm_exam.SOURCE_URL,
                 "retrieved_at": retrieved_at, "count": len(records), "records": display_records(records)}
    manifest["years"][0]["records"] = len(records)
    report = {
        "scope": "additional_api_candidate_preparation", "status": "verified",
        "prepared_at": now.isoformat(timespec="seconds"), "mode": "live_exam" if live_exam else "offline",
        "api_requests": {"gojobs": 0, "mpm_exam": request_count},
        "mpm_exam": {"retrieved_at": retrieved_at, "records": len(records),
                     "distinct_exam_names": meta["distinct_exam_names"], "structural_validation": meta,
                     "authentication_retested": live_exam, "live_verification": verification,
                     "official_amendment_notices_checked": False, "next_year_verified": False},
        "gojobs": {"observations": len(notices), "new_application_candidates": 0,
                   "decisions": dict(sorted(Counter(row["decision"] for row in notices).items())),
                   "official_source_and_application_period_verified": False},
        "source_count_before": before_count, "source_count_after": before_count,
        "source_preserved": True, "preserved_paths": list(PRESERVED),
        "source_sha256": {name: hashlib.sha256(body).hexdigest() for name, body in originals.items()},
        "production_data_writes": 0, "deployment_performed": False, "scheduled_collection_enabled": False,
    }
    sha = os.environ.get("GITHUB_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        report["code_sha"] = sha
    files = {
        EXAM_PATH: encoded(candidate), MANIFEST_PATH: encoded(manifest),
        "mpm-source-records.json": encoded({"retrieved_at": retrieved_at, "records": records,
            "scope": "validated_source_values_before_display_date_normalization"}),
        "gojobs-candidate.json": encoded({"candidates": [], "review_records": notices}),
        "report.json": encoded(report), "index.html": preview(report, notices).encode("utf-8"),
        "civil-service-exams.html": (root / "civil-service-exams.html").read_bytes(),
    }
    if live_exam:
        forms = mpm_exam._key_forms(secret.strip()) | mpm_exam._key_forms(urllib.parse.unquote(secret.strip()))
        if any(form.encode("utf-8") in content for form in forms for content in files.values()):
            raise ValueError("credential_in_candidate_rejected")
    if any((root / name).read_bytes() != body for name, body in originals.items()):
        raise ValueError("source_changed_during_preparation")
    staging = Path(tempfile.mkdtemp(prefix=".api-candidate-", dir=root))
    try:
        for relative, content in files.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-exam", action="store_true", help="Read the pinned MPM API into a review candidate; no publication")
    args = parser.parse_args()
    try:
        print(json.dumps(build(live_exam=args.live_exam), ensure_ascii=False, sort_keys=True))
    except Exception:
        print('{"status":"failed","reason":"candidate_preparation_failed"}')
        sys.exit(2)
