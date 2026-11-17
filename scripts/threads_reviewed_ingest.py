#!/usr/bin/env python3
"""CAS-ingest *already independently reviewed* v5 entries into staging, never Meta.

Unreviewed handoffs are not accepted. Each entry must pass the existing
publisher validator, public-copy check, card check (when applicable), and an
independent download/digest comparison for an official source attachment.
"""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

# Support the exact direct-script entry point used by GitHub Actions.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.threads_http import read_response
from scripts.threads_auto import load, writer_inputs
from scripts.threads_queue_bridge import (ROOT, BRANCH, QUEUE, STAGING, future_slots,
    verify_entry, media_for_slot, read, request)

KST = ZoneInfo("Asia/Seoul")
MAX_OFFICIAL_BYTES = 20_000_000
# Exact original notice attachment chosen from the employer's live job board:
# https://cleanmetro.co.kr/bbs/board.php?bo_table=recruit&wr_id=430
# Signed download nonces rotate, but this canonical three-field reference
# always resolves ONLY to the employer's original PDF attachment no=11.
CLEANMETRO_2026_17_PDF = "https://cleanmetro.co.kr/bbs/download.php?bo_table=recruit&wr_id=430&no=11"


def official_url_allowed(url):
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if (parts.scheme != "https" or not host or parts.username or
                parts.password or parts.port not in (None, 443)):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        # One manually checked employer notice, not a wildcard allowlist for
        # commercial (.co.kr) recruitment sites. Keep this exact path/query:
        # other pages or attachments need their own independent review.
        if host in ("smrtg.co.kr", "www.smrtg.co.kr"):
            return (parts.path == "/employment/stffPbanInfo.do"
                    and parts.query == "stffPbanNo=2026-0155"
                    and not parts.fragment)
        # One exact employer-operated recruitment board for the separately
        # identified Cleanmetro 2026-17 notice. This is review evidence only;
        # it must never certify corrections absent or automatically approve.
        if host == "cleanmetro.co.kr":
            pinned_original = (parts.path == "/bbs/download.php"
                    and parts.query == "bo_table=recruit&wr_id=430&no=11"
                    and not parts.fragment)
            pinned_board = (parts.path == "/bbs/board.php"
                    and re.fullmatch(r"bo_table=recruit&page=1(?:&ckattempt=[1-3])?", parts.query) is not None
                    and not parts.fragment)
            return pinned_original or pinned_board
        # Independently identified employer-managed recruiting portal for
        # Cleaneye 80848. Do not accept unrelated Incruit employers or pages.
        if host == "recruit.incruit.com":
            return (parts.path == "/cleanmetro/job/2610280002"
                    and not parts.query and not parts.fragment)
        # Published advertisement for the same independently identified
        # Cleanmetro 2026-17 notice. One exact job document only: the employer
        # application portal above does not itself contain the 103-person
        # recruiting-unit table needed to substantiate the v5 post.
        # Byte digests and semantic facts are still mandatory at intake.
        if host == "lab.incruit.com":
            return (parts.path == "/jobs/2610300002976"
                    and not parts.query and not parts.fragment)
        # Only these three publicly linked PDF attachments belong to this
        # 2026-17 notice. Their exact bytes must still be downloaded, digested,
        # semantically checked, and bound to evidence before approval.
        if host == "c.incru.it":
            return (unquote(parts.path) in {
                "/newjobpost/2026/10_cleanmetro/붙임1. 채용결격사유 관련.pdf",
                "/newjobpost/2026/10_cleanmetro/붙임2. 서류전형 평가기준.pdf",
                "/newjobpost/2026/10_cleanmetro/붙임3. 서울교통공사 재취업심사 및 취업제한심사 관련.pdf",
            } and not parts.query and not parts.fragment)
        # Independently checked Wonju Facilities Corporation notice and two
        # attachments. Neither an arbitrary .kr nor a different notice/UUID
        # is trusted. The employer may add a session ID while redirecting
        # downloads: only a 32-hex session suffix on the same pinned endpoint
        # is allowed; unrelated redirects still fail closed.
        if host == "cms.wfmc.kr":
            path = unquote(parts.path)
            if path == "/web/lay1/bbs/S1T225C230/A/3/view.do":
                return parts.query == "article_seq=5841" and not parts.fragment
            if re.fullmatch(r"/download\.do(?:;jsessionid=[0-9A-Fa-f]{32})?", path):
                return (parts.query in {
                    "uuid=67d8c76c-8846-46d8-9e8f-a87d7ca79983.pdf",
                    "uuid=b96140dd-9408-4fd8-b5ac-361b21f40e53.pdf",
                } and not parts.fragment)
            return False
        # A conservative institutional-source allowlist, not a domain trust
        # assertion. Other domains need independently reviewed support first.
        return any(host == suffix or host.endswith("." + suffix)
                   for suffix in ("alio.go.kr", "go.kr", "or.kr", "ac.kr"))
    except ValueError:
        return False


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official_url_allowed(newurl):
            raise ValueError("OFFICIAL_REDIRECT_NOT_ALLOWED")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_official_digest(url):
    """Re-read actual official bytes, not the writer's claimed excerpt."""
    if not official_url_allowed(url):
        raise ValueError("OFFICIAL_SOURCE_URL_NOT_ALLOWED")
    if url == CLEANMETRO_2026_17_PDF:
        # Only exact employer-issued PDF original; NEVER accept a moving HTML
        # snapshot, guessed document digest, unchecked redirects or stale hash.
        script = ROOT / "scripts" / "threads_cleanmetro_original_pdf_digest.cjs"
        try:
            completed = subprocess.run(
                ["node", str(script)], cwd=str(ROOT), capture_output=True,
                text=True, timeout=130, check=True)
            digest = completed.stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("OFFICIAL_SOURCE_UNAVAILABLE") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("OFFICIAL_DOCUMENT_DIGEST_INVALID")
        return digest
    opener = urllib.request.build_opener(OfficialRedirect())
    req = urllib.request.Request(url, headers={"User-Agent": "CareerPickOfficialReview/1.0",
                                                "Accept": "*/*"})
    with read_response(req, timeout=25, opener=opener.open) as response:
        data = response.read(MAX_OFFICIAL_BYTES + 1)
        if len(data) > MAX_OFFICIAL_BYTES:
            raise ValueError("OFFICIAL_DOCUMENT_TOO_LARGE")
        if not data:
            raise ValueError("OFFICIAL_DOCUMENT_EMPTY")
    return hashlib.sha256(data).hexdigest()


def verify_official_receipt(entry, fetch_digest=fetch_official_digest):
    """Verify the CURRENT bytes of every official document used for a post fact.

    Matching a random homepage or unrelated attachment is never enough. Title,
    recruiting-unit headcount and employment evidence must each cite an official
    source_ref with a prior reviewed digest; every distinct cited URL is fetched
    again. This checks byte identity, NOT semantic correctness: validate_entry
    still makes the full independent editorial and publisher decision.
    """
    writer = entry.get("writer")
    review = writer.get("review", {}) if isinstance(writer, dict) else {}
    if not isinstance(review, dict):
        raise ValueError("OFFICIAL_SOURCE_RECEIPT_REQUIRED")
    refs = review.get("source_refs", [])
    if not isinstance(refs, list):
        raise ValueError("OFFICIAL_SOURCE_RECEIPT_REQUIRED")
    eligible = {}
    for ref in refs:
        if not isinstance(ref, dict) or not official_url_allowed(ref.get("url")):
            continue
        legacy, reviewed = ref.get("sha256"), ref.get("document_sha256")
        if legacy is not None and reviewed is not None and legacy != reviewed:
            raise ValueError("OFFICIAL_SOURCE_DIGEST_CONFLICT")
        expected = reviewed if reviewed is not None else legacy
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("OFFICIAL_SOURCE_RECEIPT_REQUIRED")
        old = eligible.get(ref["url"])
        if old is not None and old != expected:
            raise ValueError("OFFICIAL_SOURCE_DIGEST_CONFLICT")
        eligible[ref["url"]] = expected
    if not eligible:
        raise ValueError("OFFICIAL_SOURCE_RECEIPT_REQUIRED")

    # Only review-backed, explicitly cited official documents are evidence.
    # An unrelated, unchanged institutional landing page must not allow
    # publication after the cited recruitment notice or attachment changes.
    facts = review.get("fact_evidence")
    if not isinstance(facts, list) or any(not isinstance(x, dict) for x in facts):
        raise ValueError("OFFICIAL_FACT_SOURCE_REQUIRED")
    required = {"title", "count", "employment"}
    # Subsidiary identity evidence is as material as the job/unit facts.
    if any(fact.get('field') == 'employer' for fact in facts):
        required.add('employer')
    cited = {}
    for fact in facts:
        field = fact.get("field")
        if field not in required:
            continue
        url = fact.get("source_ref")
        if not isinstance(url, str) or url not in eligible:
            raise ValueError("OFFICIAL_FACT_SOURCE_REQUIRED")
        cited.setdefault(field, set()).add(url)
    if not required.issubset(cited):
        raise ValueError("OFFICIAL_FACT_SOURCE_REQUIRED")
    urls = set().union(*(cited[field] for field in required))

    # When the application period cites a downloaded official URL, verify it
    # too. Non-URL snapshot references still require validate_entry to accept
    # their original source identity and excerpt.
    period = review.get("application_period")
    if isinstance(period, dict):
        ref = period.get("source_ref")
        if isinstance(ref, str) and ref.startswith(("http://", "https://")):
            if ref not in eligible:
                raise ValueError("OFFICIAL_PERIOD_SOURCE_REQUIRED")
            urls.add(ref)

    verified = []
    for url in sorted(urls):
        try:
            current = fetch_digest(url)
        except (ValueError, OSError, urllib.error.URLError) as exc:
            raise ValueError("OFFICIAL_SOURCE_UNAVAILABLE") from exc
        if current != eligible[url]:
            raise ValueError("OFFICIAL_SOURCE_BYTES_CHANGED")
        verified.append({"url": url, "sha256": current})
    return {**verified[0], "verified_fact_sources": verified}


def plan(queue, staged, submitted, history, policy, source, details, now,
         fetch_digest=fetch_official_digest, claimed_slots=()):
    """Fail closed per submission; never alter queue or any existing staging."""
    for data, label in ((queue, "QUEUE"), (staged, "STAGING"),
                        (submitted, "SUBMISSION")):
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or not isinstance(data.get("entries"), list)
                or any(not isinstance(x, dict) for x in data["entries"])):
            raise ValueError(label + "_SCHEMA")
    if not isinstance(history, dict) or not isinstance(history.get("records"), list) or not isinstance(history.get("posted_ids"), list):
        raise ValueError("HISTORY_SCHEMA")
    occupied = {e.get("scheduled_at") for e in queue["entries"] + staged["entries"]}
    used = {e.get("notice_id") for e in queue["entries"] + staged["entries"]}
    used.update(str(x) for x in history["posted_ids"])
    for record in history["records"]:
        if not isinstance(record, dict):
            raise ValueError("HISTORY_SCHEMA")
        if record.get("job_id"):
            used.add(str(record["job_id"]))
        used.update(str(x) for x in record.get("job_ids", []) if x)
    result = {**staged, "entries": list(staged["entries"])}
    accepted, refused = [], []
    accepted_prior = []  # Only verified new candidates advance future media.
    for entry in submitted["entries"]:
        nid = entry.get("notice_id")
        slot = entry.get("scheduled_at")
        try:
            if not isinstance(nid, str) or not nid.strip() or nid in used:
                raise ValueError("NOTICE_ALREADY_USED_OR_INVALID")
            if not isinstance(slot, str) or slot not in future_slots(now):
                raise ValueError("SLOT_NOT_FUTURE")
            if slot in occupied or slot in claimed_slots:
                raise ValueError("SLOT_ALREADY_OCCUPIED_OR_CLAIMED")
            if any(r.get("scheduled_at") == slot for r in history["records"]):
                raise ValueError("SLOT_ALREADY_STARTED")
            # Never admit an unreviewed candidate, even if its body looks ready.
            if not isinstance(entry.get("writer"), dict) or entry["writer"].get("status") != "ready":
                raise ValueError("NOT_A_REVIEWED_ENTRY")
            receipt = verify_official_receipt(entry, fetch_digest=fetch_digest)
            media = media_for_slot(history, queue["entries"] + accepted_prior,
                                   slot, now, policy, source, details)
            verify_entry(entry, now, history, policy, source, details,
                         expected_media=media)
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            refused.append({"notice_id": nid, "slot": slot, "reason": str(exc)[:140]})
            continue
        result["entries"].append(entry)
        accepted_prior.append(entry)
        accepted.append({"notice_id": nid, "slot": slot, "official_receipt": receipt})
        occupied.add(slot)
        used.add(nid)
    return result, accepted, refused


def run(path, apply=False):
    submitted = json.loads(Path(path).read_text(encoding="utf-8"))
    if submitted.get("automatic_approval") is True or submitted.get("meta_posted") is True:
        raise ValueError("UNREVIEWED_OR_POSTED_INPUT")
    token = os.environ.get("THREADS_CLAIM_TOKEN")
    if not token or os.environ.get("GITHUB_REPOSITORY") != "kllollain-max/careerpick":
        raise RuntimeError("GITHUB_CLAIM_ACCESS_REQUIRED")
    history = load(ROOT / "threads_posted.json", {"records": [], "posted_ids": []})
    policy, source, details = writer_inputs(ROOT)
    now = datetime.now(KST)
    report = {"status": "reviewed_staging_preflight", "time": now.isoformat(),
              "staging_updated": False, "queue_updated": False,
              "meta_posted": False, "accepted": [], "refused": []}
    for attempt in range(3):
        queue, _ = read(QUEUE, token)
        try:
            staged, sha = read(STAGING, token)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            staged, sha = {"schema_version": 1, "entries": []}, None
        # Reject a slot already claimed by a publisher, even if it does not
        # yet have a complete posted-history receipt.
        claimed = set()
        for entry in submitted.get("entries", []):
            slot = entry.get("scheduled_at") if isinstance(entry, dict) else None
            try:
                at = datetime.fromisoformat(slot)
                if at.utcoffset() is None or slot not in future_slots(now):
                    continue
                key = at.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%MZ.json")
                try:
                    request("GET", "threads-claims/" + key, token)
                    claimed.add(slot)
                except urllib.error.HTTPError as exc:
                    if exc.code != 404:
                        raise
            except (ValueError, TypeError):
                continue
        merged, accepted, refused = plan(queue, staged, submitted, history, policy,
                                         source, details, now, claimed_slots=claimed)
        report.update(accepted=accepted, refused=refused,
                      accepted_count=len(accepted), reviewed_input_count=len(submitted["entries"]))
        if not apply or not accepted:
            break
        payload = {"branch": BRANCH, "message": "Stage independently reviewed CareerPick Threads v5 entries [skip ci]",
                   "content": base64.b64encode((json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode()).decode()}
        if sha:
            payload["sha"] = sha
        try:
            request("PUT", STAGING, token, payload)
        except urllib.error.HTTPError as exc:
            if exc.code in (409, 422) and attempt < 2:
                time.sleep(1)
                continue
            raise
        readback, _ = read(STAGING, token)
        if readback != merged:
            raise RuntimeError("STAGING_READBACK_MISMATCH")
        report["staging_updated"] = True
        break
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Complete independently reviewed v5 entry bundle")
    parser.add_argument("--apply", action="store_true", help="CAS-write only to staging after all checks")
    parser.add_argument("--output", default="threads-reviewed-ingest-report.json")
    args = parser.parse_args()
    report = run(args.input, args.apply)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": report.get("accepted_count", 0),
                      "refused": len(report["refused"]),
                      "staging_updated": report["staging_updated"],
                      "meta_posted": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
