#!/usr/bin/env python3
"""Stage a complete Cleaneye collection without changing any source snapshot.

The API's region is the institution's region; WORK_PLACE is the workplace.
PUB_DATE is the application start, not the publication date, and UPD_DATE is
only the source modification date.  Unknown source codes stay unknown.
"""

import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cleaneye

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
SOURCE = "클린아이 잡플러스"
OFFICIAL_HOSTS = {"job.cleaneye.go.kr", "www.job.cleaneye.go.kr"}
DETAIL_FIELDS = {
    "ENT_NAME": "기관명", "ENT_TITLE": "채용제목", "ENT_GB": "기관형태",
    "ENT_KIND": "기관분류", "SIDO_CD": "기관 시도명", "STATUS": "채용상태 원문",
    "EMPYEAR": "채용연도", "ENT_RECRUIT": "모집분야", "EMPLOY_NUM": "채용인원",
    "EMPLOY_GB": "채용구분", "JOB_TYPE": "고용형태 원문", "RE_MAN_YN": "대체인력유무",
    "POSITION": "직위", "YEARINCOME": "연봉", "OFFICE_HOURS": "근무시간",
    "WORK_PLACE": "근무지", "DUTY_DETAIL": "직무세부내용", "RETIREMENT": "정년",
    "JUDGE_METHOD": "심사방법", "LOCAL_YN": "지역제한", "LOCAL_NAME": "지역명칭",
    "LOCAL_REASON": "지역제한사유", "ENT_LICENSE1": "자격증1", "ENT_LICENSE2": "자격증2",
    "ENT_LICENSE3": "자격증3", "ENT_LICENSE4": "자격증4", "SPECIAL_ITEM": "우대사항",
    "PUB_DATE": "접수개시일 원문", "PUB_END_DATE": "접수마감일 원문",
    "ACCUSATION": "접수방법", "REFERENCE": "문의처", "EXHIBIT": "제출서류",
    "JOB_SEEK_ETC": "구직자한마디", "FILE_NAME1": "첨부파일명1",
    "FILE_NAME2": "첨부파일명2", "FILE_NAME3": "첨부파일명3",
    "URL": "공식 공고 URL", "ADDRESS": "기관주소", "NO": "공고 고유번호",
    "UPD_DATE": "수정날짜 원문",
}
EMPLOYMENT_LABELS = {
    "정규직", "비정규직", "계약직", "기간제", "기간제근로자", "기간제 근로자",
    "일반정규직", "일반계약직", "전문계약직", "비상임",
    "무기계약직", "무기계약근로자", "공무직", "인턴", "청년인턴", "청년 인턴",
    "체험형인턴", "체험형 인턴", "채용형인턴", "채용형 인턴", "파견직", "일용직",
    "단시간근로자", "단시간 근로자", "상용직",
}
OPEN_STATUS = {"접수중", "모집중", "채용중", "진행중"}
UPCOMING_STATUS = {"접수예정", "모집예정", "채용예정"}
CLOSED_STATUS = {"마감", "접수마감", "채용마감", "모집마감", "모집완료", "채용완료", "종료", "접수종료"}
CANCELLED_STATUS = {"취소", "채용취소", "공고취소", "모집취소"}
# A deadline at least 10 calendar years after the collection year needs source
# review. Preserve the original date; this threshold never establishes closure.
FAR_FUTURE_REVIEW_YEARS = 10


class CollectionError(ValueError):
    """An internal, fixed error code; never construct from response text."""


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        elif not self.hidden and tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1
        elif not self.hidden and tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def plain_text(value):
    parser = _PlainText()
    parser.feed(value)
    parser.close()
    text = "".join(parser.parts)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _official_url(value):
    value = html.unescape(value.strip())
    if not value or re.search(r"[\s\x00-\x1f\x7f\\]", value):
        raise CollectionError("invalid_official_url")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.path in ("", "/")):
            raise CollectionError("invalid_official_url")
    except ValueError:
        raise CollectionError("invalid_official_url") from None
    return value


def _source_date(value, *, end=False):
    """Return a KST instant, whether the source supplied time, and validity.

    A date-only end has a sorting surrogate of 23:59:59, always accompanied by
    dueHasTime=False.  No time is claimed to be supplied by the institution.
    """
    value = value.strip()
    if not value:
        return None, False, "missing"
    explicit = False
    normalized = value
    if re.fullmatch(r"[0-9]{8}", value):
        normalized = value[:4] + "-" + value[4:6] + "-" + value[6:8]
    elif re.fullmatch(r"[0-9]{14}", value):
        normalized = (value[:4] + "-" + value[4:6] + "-" + value[6:8]
                      + "T" + value[8:10] + ":" + value[10:12] + ":" + value[12:14])
        explicit = True
    else:
        match = re.fullmatch(
            r"([0-9]{4})([-./])([0-9]{2})\2([0-9]{2})"
            r"(?:[ T]([0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?)"
            r"(Z|[+-][0-9]{2}:[0-9]{2})?)?", value)
        if not match:
            return None, False, "invalid"
        normalized = f"{match[1]}-{match[3]}-{match[4]}"
        if match[5]:
            explicit = True
            normalized += "T" + match[5] + ("+00:00" if match[6] == "Z" else (match[6] or ""))
    try:
        instant = datetime.fromisoformat(normalized)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=KST)
        instant = instant.astimezone(KST)
        if end and not explicit:
            instant = instant.replace(hour=23, minute=59, second=59)
    except ValueError:
        return None, False, "invalid"
    return instant, explicit, "valid"


def _reception_state(status, start, due, due_has_time, date_problem, now):
    label = re.sub(r"\s+", "", plain_text(status))
    if label in CANCELLED_STATUS:
        return "cancelled"
    if label in CLOSED_STATUS:
        return "expired"
    if date_problem:
        return "invalid_date"
    if due and (due < now if due_has_time else due.date() < now.date()):
        return "expired"
    if label not in OPEN_STATUS | UPCOMING_STATUS:
        return "verification_pending"
    if start and start > now:
        return "upcoming"
    if not start or not due or label in UPCOMING_STATUS:
        return "verification_pending"
    if not due_has_time and due.date() == now.date():
        return "verification_pending"
    return "verified_open"


def normalize(record, now):
    if not isinstance(record, dict) or any(not isinstance(v, str) for v in record.values()):
        raise CollectionError("invalid_record")
    # The live source uses the exact text "null" for missing optional values.
    # Do not substitute institution location, zero headcount, or guessed values.
    required_or_date_fields = {"NO", "ENT_NAME", "ENT_TITLE", "PUB_DATE", "PUB_END_DATE", "UPD_DATE"}
    record = {name: "" if value == "null" and name not in required_or_date_fields else value
              for name, value in record.items()}
    identity = record.get("NO", "").strip()
    if (identity == "null" or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", identity)
            or len("cleaneye-" + identity) > 128):
        raise CollectionError("invalid_notice_id")
    title, org = (plain_text(record.get(field, "")) for field in ("ENT_TITLE", "ENT_NAME"))
    if not title or not org or title == "null" or org == "null":
        raise CollectionError("missing_notice_title_or_org")
    url = _official_url(record.get("URL", ""))
    start, start_has_time, start_valid = _source_date(record.get("PUB_DATE", ""))
    due, due_has_time, due_valid = _source_date(record.get("PUB_END_DATE", ""), end=True)
    date_problem = "invalid" in (start_valid, due_valid) or bool(start and due and start > due)
    status = record.get("STATUS", "")
    reception_state = _reception_state(status, start, due, due_has_time, date_problem, now)
    far_future = bool(due and due.year >= now.year + FAR_FUTURE_REVIEW_YEARS)
    if far_future and reception_state in {"verified_open", "upcoming"}:
        reception_state = "verification_pending"
    employment = [label.strip() for label in re.split(r"[,/;·|]", record.get("JOB_TYPE", ""))]
    employment = list(dict.fromkeys(label for label in employment if label in EMPLOYMENT_LABELS))
    number = plain_text(record.get("EMPLOY_NUM", ""))
    number = int(number) if re.fullmatch(r"[0-9]{1,9}", number) else number
    detail = {label: record[field] for field, label in DETAIL_FIELDS.items() if record.get(field, "").strip()}
    searchable = [plain_text(record.get(field, "")) for field in (
        "ENT_TITLE", "ENT_NAME", "ENT_RECRUIT", "WORK_PLACE", "JOB_TYPE", "POSITION",
        "DUTY_DETAIL", "JUDGE_METHOD", "SPECIAL_ITEM", "ACCUSATION", "EXHIBIT", "JOB_SEEK_ETC")]
    return {
        "id": "cleaneye-" + identity, "type": "j", "cleaneye": True, "source": SOURCE,
        "cat": "지방공공기관 채용", "title": title, "org": org,
        "desc": "클린아이 잡플러스 공식 채용공고 · 접수 시각과 첨부는 원문 확인",
        "url": url, "src": url, "pub": None,
        "start": start.isoformat() if start and start_has_time else (start.date().isoformat() if start else None),
        "due": due.isoformat() if due else None,
        "dueHasTime": bool(due and due_has_time), "emp": employment, "edu": [],
        "n": number if number != "" else None, "region": plain_text(record.get("WORK_PLACE", "")),
        "sourceRegion": plain_text(record.get("SIDO_CD", "")), "sourceStatus": status,
        "receptionState": reception_state,
        **({"deadlineReviewReason": "far_future_source_date"} if far_future else {}),
        "sourceMissing": False, "text": "\n".join(value for value in searchable if value),
        "cleaneyeDetail": detail,
    }


def _region_codes(value):
    if not isinstance(value, (list, tuple)) or not value:
        raise CollectionError("missing_verified_region_codes")
    if (len(value) > cleaneye.MAX_REGIONS
            or any(not isinstance(code, str) or not code.strip() or len(code) > cleaneye.MAX_REGION_CODE_CHARS
                   or any(ord(char) < 32 or ord(char) == 127 for char in code) for code in value)
            or len(set(value)) != len(value)):
        raise CollectionError("invalid_region_codes")
    return tuple(sorted(value))


def merge(previous, records, now, *, sido_codes, region_counts, complete_collection):
    codes = _region_codes(sido_codes)
    if complete_collection is not True:
        raise CollectionError("incomplete_collection")
    if (not isinstance(records, list) or not isinstance(region_counts, dict)
            or set(region_counts) != set(codes)
            or any(type(count) is not int or count < 0 for count in region_counts.values())
            or sum(region_counts.values()) != len(records)):
        raise CollectionError("incomplete_region_counts")
    if not records:
        raise CollectionError("empty_list_preserved")
    if not isinstance(previous, dict) or not isinstance(previous.get("posts"), list):
        raise CollectionError("invalid_baseline")
    old = {}
    for post in previous["posts"]:
        if (not isinstance(post, dict) or not isinstance(post.get("id"), str)
                or not post["id"].startswith("cleaneye-") or post["id"] in old):
            raise CollectionError("invalid_previous_id")
        old[post["id"]] = post
    if old and previous.get("regionCodes") and not set(previous["regionCodes"]).issubset(codes):
        raise CollectionError("collection_scope_narrowed")
    baseline = previous.get("last_received", 0)
    if type(baseline) is not int or baseline < 0:
        raise CollectionError("invalid_baseline_count")
    if baseline and len(records) < baseline * 0.7:
        raise CollectionError("unexpected_collection_decrease")
    live = {}
    for record in records:
        post = normalize(record, now)
        if post["id"] in live:
            raise CollectionError("duplicate_notice_id")
        live[post["id"]] = post
    # Dates may identify a current candidate without proving its source status.
    # Such an item stays verification_pending, never verified_open.
    current_candidates = sum(
        p["receptionState"] not in {"expired", "cancelled", "invalid_date"}
        and bool(p["due"]) and p["due"][:10] >= now.date().isoformat()
        for p in live.values())
    if not old and not current_candidates:
        raise CollectionError("no_current_initial_candidate")
    rows = dict(live)
    for identity, post in old.items():
        if identity in live:
            continue
        retained = dict(post, sourceMissing=True)
        # List absence is not evidence of closure.  Preserve the stored ID and
        # content, but don't advertise a missing future notice as verified open.
        if retained.get("receptionState") not in {"expired", "cancelled"}:
            retained["receptionState"] = "verification_pending"
            deadline, _, _ = _source_date(retained.get("due") or "", end=True)
            if deadline and (deadline < now if retained.get("dueHasTime") else deadline.date() < now.date()):
                retained["receptionState"] = "expired"
        rows[identity] = retained
    posts = sorted(rows.values(), key=lambda post: post["id"])
    counts = {
        "before": len(old), "received": len(live), "new": len(live.keys() - old.keys()),
        "changed": sum(rows[identity] != old[identity] for identity in old),
        "retained": len(old.keys() - live.keys()), "deleted": 0, "after": len(rows),
        "active": sum(p.get("receptionState") == "verified_open" for p in posts),
        "upcoming": sum(p.get("receptionState") == "upcoming" for p in posts),
        "expired": sum(p.get("receptionState") == "expired" for p in posts),
        "cancelled": sum(p.get("receptionState") == "cancelled" for p in posts),
        "status_uncertain": sum(p.get("receptionState") in {"verification_pending", "invalid_date"} for p in posts),
        "deadline_time_uncertain": sum(bool(p.get("due")) and not p.get("dueHasTime") for p in posts),
        "deadline_unknown": sum(not p.get("due") for p in posts),
        "far_future_source_date": sum(p.get("deadlineReviewReason") == "far_future_source_date" for p in posts),
        "current_candidates": current_candidates,
    }
    candidate = {
        **previous, "source": "cleaneye", "collectionStatus": "verified",
        "scope": "지방공공기관 채용정보", "regionCodes": list(codes),
        "last_received": len(live), "posts": posts,
    }
    changed = any(candidate.get(key) != previous.get(key) for key in candidate if key != "updated")
    if not changed:
        return previous, False, counts
    candidate["updated"] = now.isoformat(timespec="seconds")
    return candidate, True, counts


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _reject_credential_echo(value, key):
    if not key:
        return
    text = json.dumps(value, ensure_ascii=False)
    secrets = {key.casefold(), unquote(key).casefold()}
    for _ in range(4):
        if any(secret and secret in text.casefold() for secret in secrets):
            raise CollectionError("credential_echo_rejected")
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded


def _safe_counts(client, name):
    values = getattr(client, name, {}) if client else {}
    counts = {}
    for operation in ("region_codes", "list"):
        value = values.get(operation, 0) if isinstance(values, dict) else 0
        limit = cleaneye.MAX_REGION_PAGES if operation == "region_codes" else cleaneye.MAX_REGIONS
        counts[operation] = value if type(value) is int and 0 <= value <= limit else 0
    return counts


def _snapshot(root):
    paths = set(root.glob("*.json")) | set((root / "data").rglob("*.json")) | {root / "cleaneye.json"}
    return {path: path.read_bytes() if path.exists() else None for path in paths}


def _unchanged(originals):
    return all((path.read_bytes() if path.exists() else None) == before for path, before in originals.items())


def _atomic_write(path, content):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".cleaneye-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.close()
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


def run(root=ROOT, output=None, *, key=None, client_factory=cleaneye.Client, now=None, sido_codes=None):
    root = Path(root).resolve()
    output = (Path(output) if output is not None else root / "cleaneye-operation-output").resolve()
    now = (now or datetime.now(KST)).astimezone(KST)
    key = (os.environ.get("CLEANEYE_KEY", "") if key is None else key).strip()
    report = {
        "source": "cleaneye", "service": cleaneye.SERVICE_ID,
        "started_at": now.isoformat(timespec="seconds"), "status": "failed_preserved", "changed": False,
        "key_present": bool(key), "authentication_verified": False, "complete_collection": False,
        "originals_preserved": False,
    }
    originals, client, writable_output, wrote_candidate = {}, None, False, False
    stage = "configuration"
    target = output / "cleaneye.json"
    try:
        if output == root or output.is_relative_to(root / "data"):
            raise CollectionError("unsafe_output_directory")
        output.mkdir(parents=True, exist_ok=True)
        writable_output = True
        originals = _snapshot(root)
        if target.exists() or target.is_symlink():
            raise CollectionError("existing_candidate_output")
        original = originals[root / "cleaneye.json"]
        previous = json.loads(original) if original is not None else {"posts": []}
        if not key:
            raise CollectionError("blocked_missing_secret")
        if sido_codes is None:
            supplied = os.environ.get("CLEANEYE_SIDO_CODES", "")
            if supplied.strip():
                sido_codes = [part.strip() for part in supplied.split(",") if part.strip()]
        client = client_factory(key)
        if sido_codes is None:
            stage = "region_codes"
            report["region_code_source"] = "official_api"
            report["region_code_source_url"] = cleaneye.REGION_SOURCE_URL
            report["region_code_lookup_year"] = now.year
            report["region_code_lookup_verified"] = False
            mapping = client.collect_region_codes(ac_year=now.year)
            _reject_credential_echo(mapping, key)
            metadata = getattr(client, "region_code_metadata", {})
            if (not isinstance(mapping, dict) or not mapping
                    or any(not isinstance(name, str) or not name.strip() for name in mapping.values())
                    or not isinstance(metadata, dict) or metadata.get("complete") is not True
                    or metadata.get("reference_year") != now.year
                    or type(metadata.get("total_count")) is not int or metadata["total_count"] != len(mapping)
                    or type(metadata.get("pages")) is not int or metadata["pages"] < 1):
                raise CollectionError("incomplete_region_code_list")
            codes = _region_codes(list(mapping))
            report["region_code_metadata"] = {
                "reference_year": now.year, "total_count": len(mapping),
                "pages": metadata["pages"], "complete": True,
            }
            report["region_code_lookup_verified"] = True
        else:
            report["region_code_source"] = "explicit"
            codes = _region_codes(sido_codes)
        report["region_codes"] = list(codes)
        stage = "employment"
        records = client.collect_list(sido_codes=codes)
        _reject_credential_echo(records, key)
        complete = getattr(client, "collection_complete", False) is True
        report.update(authentication_verified=True, complete_collection=complete)
        region_counts = getattr(client, "region_counts", {})
        stage = "candidate_validation"
        # Diagnostics contain only bounded known fields, never raw responses,
        # exception messages, credential-bearing requests, or attachment links.
        report["observed_source_values"] = {
            field: sorted({record.get(field, "") for record in records if isinstance(record, dict)})[:20]
            for field in ("STATUS", "JOB_TYPE")
        }
        feed, changed, counts = merge(previous, records, now, sido_codes=codes,
                                      region_counts=region_counts, complete_collection=complete)
        report["region_counts"] = dict(region_counts)
        report["counts"] = {"cleaneye": counts}
        _reject_credential_echo(feed, key)
        _reject_credential_echo(report, key)
        if not _unchanged(originals):
            raise CollectionError("source_changed_during_collection")
        content = _encoded(feed)
        _atomic_write(target, content)
        wrote_candidate = True
        report.update(status="changed" if changed else "unchanged", changed=changed,
                      snapshot_at=feed.get("updated"), candidate_sha256=hashlib.sha256(content).hexdigest())
    except (CollectionError, cleaneye.APIError) as error:
        report["error"] = error.safe_code if isinstance(error, cleaneye.APIError) else str(error)
        report["error_source"] = stage
    except Exception:
        report["error"] = "candidate_validation_failed"
        report["error_source"] = stage
    finally:
        report["requests"] = _safe_counts(client, "request_counts")
        report["successful_responses"] = _safe_counts(client, "success_counts")
        report["source_sha256"] = {
            str(path.relative_to(root)): hashlib.sha256(content).hexdigest() if content is not None else None
            for path, content in sorted(originals.items())
        }
        try:
            report["originals_preserved"] = bool(originals) and _unchanged(originals)
        except OSError:
            report["originals_preserved"] = False
        if not report["originals_preserved"] and report["status"] in {"changed", "unchanged"}:
            report.update(status="failed_preserved", changed=False, error="source_changed_during_collection")
        try:
            _reject_credential_echo(report, key)
        except CollectionError:
            report = {"source": "cleaneye", "status": "failed_preserved", "changed": False,
                      "error": "credential_echo_rejected", "originals_preserved": report["originals_preserved"]}
        if wrote_candidate and report["status"] == "failed_preserved":
            target.unlink(missing_ok=True)
        if writable_output:
            _atomic_write(output / "report.json", _encoded(report))
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    sys.exit(0 if result["status"] in {"changed", "unchanged"} and result["originals_preserved"] else 1)
