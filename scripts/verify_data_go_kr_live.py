#!/usr/bin/env python3
"""Validate data.go.kr into review-only artifacts, preserving both source snapshots."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alio
from data_go_kr import APIError, Client

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("alio.json", "alio-detail.json")
DETAIL_SAMPLE_LIMIT = 3


class VerificationError(Exception):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def verify(root=ROOT, output=None, *, key=None, client_factory=Client, now=None):
    root = Path(root)
    output = Path(output) if output is not None else root / "data-go-kr-check-output"
    output.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(alio.KST)
    key = os.environ.get("DATA_GO_KR_KEY", "").strip() if key is None else key.strip()
    report = {
        "service": "data_go_kr_15125273",
        "endpoint_base": "https://apis.data.go.kr/1051000/recruitment",
        "status": "not_started",
        "checked_at": now.isoformat(timespec="seconds"),
        "key_present": bool(key),
        "list_verified": False,
        "detail_verified": False,
        "detail_scope": "sample_only",
        "detail_sample_limit": DETAIL_SAMPLE_LIMIT,
        "official_closed_verified": None,
        "source_preserved": False,
    }
    originals = {}
    client = None
    try:
        if (output / "candidate").exists():
            raise VerificationError("existing_candidate_output")
        originals = {name: (root / name).read_bytes() for name in NAMES}
        baseline = json.loads(originals["alio.json"])
        baseline_details = json.loads(originals["alio-detail.json"])
        old_posts = {p["id"]: p for p in baseline["posts"]}
        if len(old_posts) != len(baseline["posts"]) or not isinstance(baseline_details, dict):
            raise VerificationError("invalid_baseline")
        report["before"] = len(old_posts)
        report["source_updated"] = baseline.get("updated")
        if not key:
            raise VerificationError("blocked_missing_secret")
        client = client_factory(key)
        records = client.collect_list()
        report["list_verified"] = True
        report["received_unique"] = len(records)
        if not records:
            raise VerificationError("empty_list_preserved")

        live_posts, live_details, date_filtered = {}, {}, 0
        for record in records:
            identity = "a" + str(record["recrutPblntSn"])
            start = alio.ymd(record.get("pbancBgngYmd"))
            end = alio.ymd(record.get("pbancEndYmd"))
            if not start or not end or not str(record.get("instNm", "")).strip():
                raise VerificationError("invalid_notice_fields")
            post = alio.convert(record, now)
            if post is None:
                if end.replace(hour=23, minute=59, second=59) < now:
                    date_filtered += 1
                    continue
                raise VerificationError("notice_conversion_failed")
            if post["id"] != identity or identity in live_posts:
                raise VerificationError("notice_identity_mismatch")
            live_posts[identity] = post
            live_details[identity] = {
                **baseline_details.get(identity, {}), **alio.detail_of(record)
            }
        if not live_posts:
            raise VerificationError("no_active_candidate_preserved")

        sample_details = {}
        # Sample stable IDs: first, middle, and last in the returned active list.
        active_ids = list(live_posts)
        indexes = sorted({0, len(active_ids) // 2, len(active_ids) - 1})[:DETAIL_SAMPLE_LIMIT]
        for index in indexes:
            identity = active_ids[index]
            detail = client.detail(identity[1:])
            if (not str(detail.get("recrutPbancTtl", "")).strip()
                    or not str(detail.get("instNm", "")).strip()
                    or not alio.ymd(detail.get("pbancBgngYmd"))
                    or not alio.ymd(detail.get("pbancEndYmd"))
                    or not isinstance(detail.get("files"), list)
                    or not isinstance(detail.get("steps"), list)):
                raise VerificationError("invalid_detail_fields")
            sample_details[identity] = detail
            live_details[identity].update(alio.detail_of(detail))
        report["detail_verified"] = bool(sample_details)
        report["detail_verified_count"] = len(sample_details)
        report["detail_total_unverified"] = len(live_posts) - len(sample_details)
        report["detail_samples"] = [
            {"id": identity, "files_count": len(detail.get("files") or []),
             "steps_count": len(detail.get("steps") or []),
             "official_url": live_posts[identity]["url"],
             "start": alio.ymd(detail["pbancBgngYmd"]).date().isoformat(),
             "end": alio.ymd(detail["pbancEndYmd"]).date().isoformat()}
            for identity, detail in sample_details.items()
        ]

        merged_posts = {**old_posts, **live_posts}
        merged_details = {**baseline_details, **live_details}
        common = old_posts.keys() & live_posts.keys()
        posts_changed = {i for i in common if old_posts[i] != live_posts[i]}
        details_changed = {i for i in common if baseline_details.get(i, {}) != live_details[i]}
        expired = {
            i for i, p in old_posts.items()
            if p.get("due") and datetime.fromisoformat(p["due"]) < now
        }
        source_time = datetime.fromisoformat(baseline["updated"])
        newly_expired = {
            i for i in expired if datetime.fromisoformat(old_posts[i]["due"]) >= source_time
        }
        api_ids = {"a" + str(record["recrutPblntSn"]) for record in records}
        report.update(
            status="verified_candidate", after=len(merged_posts),
            active_candidate=len(live_posts),
            added=len(live_posts.keys() - old_posts.keys()),
            changed=len(posts_changed | details_changed),
            posts_changed=len(posts_changed), details_changed=len(details_changed),
            retained=len(old_posts.keys() - live_posts.keys()), removed=0,
            date_filtered_from_live_list=date_filtered,
            deadline_expired_in_baseline=len(expired),
            newly_date_expired_since_baseline=len(newly_expired),
            absent_from_active_list=len(old_posts.keys() - api_ids),
            absent_with_unexpired_deadline=len((old_posts.keys() - api_ids) - expired),
            closure_note="Date expiration and list absence are not official early-closure confirmation",
        )
        candidate = {
            "alio.json": {"updated": now.isoformat(timespec="seconds"),
                          "posts": sorted(merged_posts.values(), key=lambda p: (p.get("due") or "9999", p["id"]))},
            "alio-detail.json": merged_details,
            "detail-samples.json": sample_details,
        }
        serialized = {name: encoded(value) for name, value in candidate.items()}
        # Response text never goes to logs. Reject artifacts if any credential form appears.
        raw_key = urllib.parse.unquote(key)
        forbidden = {key, raw_key, urllib.parse.quote(raw_key, safe=""), urllib.parse.quote_plus(raw_key)}
        if any(token and token.encode() in content for token in forbidden for content in serialized.values()):
            raise VerificationError("credential_in_response_rejected")
        if not all((root / n).read_bytes() == content for n, content in originals.items()):
            raise VerificationError("source_changed_during_check")
        with tempfile.TemporaryDirectory(prefix="data-go-kr-review-") as directory:
            stage = Path(directory)
            for name, content in serialized.items():
                (stage / name).write_bytes(content)
            shutil.copytree(stage, output / "candidate")
        report["candidate_sha256"] = {n: hashlib.sha256(b).hexdigest() for n, b in serialized.items()}
    except APIError as error:
        report.update(status="blocked_or_failed_preserved", reason=str(error))
    except VerificationError as error:
        report.update(status="blocked_or_failed_preserved", reason=str(error))
    except Exception as error:
        report.update(status="blocked_or_failed_preserved", reason="unexpected_error",
                      error_type=type(error).__name__)
    finally:
        report["requests"] = dict(client.request_counts) if client else {"list": 0, "detail": 0}
        report["successful_responses"] = dict(client.success_counts) if client else {"list": 0, "detail": 0}
        report["source_sha256"] = {n: hashlib.sha256(b).hexdigest() for n, b in originals.items()}
        report["source_preserved"] = len(originals) == len(NAMES) and all(
            (root / n).read_bytes() == content for n, content in originals.items()
        )
        if not report["source_preserved"] and report["status"] == "verified_candidate":
            report.update(status="blocked_or_failed_preserved", reason="source_changed_during_check")
        (output / "report.json").write_bytes(encoded(report))
    return report


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    sys.exit(0 if result["status"] == "verified_candidate" and result["source_preserved"] else 2)
