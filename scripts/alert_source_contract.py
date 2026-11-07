"""Pure source-aware candidate checks, before mandatory fresh-source preflight.

This layer does not establish source freshness, discover subscribers, reserve
delivery keys or send. A queued Cleaneye row can outlive one feed snapshot;
the sender must still verify it against a fresh official source before sending.
"""

import re
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from scripts.cleaneye_source_adapter import (
    KST, SOURCE_LABEL, OPEN_STATUS, is_recruitment_notice, source_date, source_text,
)


CLEANEYE_JOB_FIELDS = (
    "cleaneye", "source", "sourceUpdated", "src", "type", "start", "dueHasTime",
    "receptionState", "sourceMissing", "sourceRegion", "sourceStatus",
    "cleaneyeDetail", "deadlineReviewReason", "dateReview", "dateReviewReason",
    "text", "n",
)


def supported_job_id(value):
    """Accept canonical IDs without trimming, coercion or ledger-key changes."""
    return isinstance(value, str) and re.fullmatch(r"(?:a[0-9]+|cleaneye-[0-9]+)", value) is not None


def _official_cleaneye_url(value, official_id):
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and url.hostname in {"job.cleaneye.go.kr", "www.job.cleaneye.go.kr"}
                and not url.username and not url.password and url.port in (None, 443)
                and url.path == "/user/ypCareersData.do" and not url.fragment
                and parse_qs(url.query, keep_blank_values=True, strict_parsing=True) == {"idx": [official_id]})
    except ValueError:
        return False


def _cleaneye_candidate_open(job, now):
    if (job.get("cleaneye") is not True or job.get("source") != SOURCE_LABEL
            or job.get("type") != "j" or job.get("alio") or job.get("gojobs")
            or job.get("receptionState") != "verified_open"
            or job.get("sourceMissing") is not False
            or any(job.get(key) for key in ("deadlineReviewReason", "dateReview", "dateReviewReason"))):
        return False
    detail = job.get("cleaneyeDetail")
    if not isinstance(detail, dict):
        return False
    official_id = job["id"][len("cleaneye-"):]
    if source_text(detail.get("공고 고유번호")) != official_id:
        return False
    if not all(_official_cleaneye_url(value, official_id) for value in
               (job.get("url"), job.get("src"), detail.get("공식 공고 URL"))):
        return False
    title, org = source_text(detail.get("채용제목")), source_text(detail.get("기관명"))
    if (not title or not org or source_text(job.get("title")) != title
            or source_text(job.get("org")) != org or not is_recruitment_notice(title, detail)):
        return False
    status = source_text(detail.get("채용상태 원문"))
    if re.sub(r"\s+", "", status) not in OPEN_STATUS or source_text(job.get("sourceStatus")) != status:
        return False
    try:
        start, start_has_time = source_date(detail.get("접수개시일 원문"))
        end, end_has_time = source_date(detail.get("접수마감일 원문"))
        listed_start, listed_start_has_time = source_date(job.get("start"))
        listed_end, _ = source_date(job.get("due"))
    except ValueError:
        return False
    if (listed_start != start or listed_start_has_time != start_has_time
            or job.get("dueHasTime") is not end_has_time
            or (listed_end != end if end_has_time else listed_end.date() != end.date())
            or start > end or start == end and start_has_time and end_has_time
            or end.year >= now.year + 10):
        return False
    if (now < start if start_has_time else now.date() <= start.date()):
        return False
    return now < end if end_has_time else now.date() < end.date()


def candidate_open(job, now):
    """Whether a canonical stored candidate may proceed to later source checks.

    Cleaneye needs explicit original opening/closing dates and open status.
    A date-only deadline is never treated as an exact 23:59 closing time, and
    same-day unknown opening/closing times remain ineligible. ALIO's existing
    deadline rule is retained. No feed timestamp is fabricated here.
    """
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone-aware time required")
    if (not isinstance(job, dict) or not supported_job_id(job.get("id"))
            or not isinstance(job.get("title"), str) or not job["title"].strip()):
        return False
    if job["id"].startswith("cleaneye-"):
        return _cleaneye_candidate_open(job, now.astimezone(KST))
    if job.get("cleaneye"):
        return False
    # Lazy import preserves the established ALIO parser without introducing a
    # module-import cycle when the detector also uses these shared predicates.
    from scripts.detect_new_job_alerts import parse_due
    due = parse_due(job.get("due"))
    return due is not None and due > now
