"""Pure, conservative facts and eligibility for Cleaneye publication consumers.

The saved feed retains the official API fields under Korean display labels.
Application dates come from PUB_DATE/PUB_END_DATE, never a guessed publication
period. Institution region/address must never fill in a missing workplace.
This module reads no files, performs no requests and creates no queue entries.
"""

from datetime import datetime, timedelta
import re
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
SOURCE = "cleaneye"
SOURCE_LABEL = "클린아이 잡플러스"
OPEN_STATUS = {"접수중", "모집중", "채용중", "진행중"}
RECRUITMENT_TITLE = re.compile(r"채용|모집|구인|초빙|충원|선발|위촉")
NON_RECRUITMENT_TITLE = re.compile(
    r"취\s*소|철\s*회|합격자|합격\s*발표|결과\s*(?:발표|공고|안내)|전형\s*결과|"
    r"(?:필기|면접|실기|체력|인적성)\s*(?:시험|전형|검사)?\s*(?:일정|일시|장소|대상자|안내)|"
    r"시험\s*(?:일정|일시|장소|안내)|(?:전형|시험|면접)\s*일정\s*변경"
)
REQUIREMENT_FIELDS = (
    "채용구분", "모집분야", "직위", "직무세부내용", "자격증1", "자격증2", "자격증3", "자격증4",
    "지역제한", "지역명칭", "지역제한사유", "정년", "우대사항", "근무시간", "심사방법", "접수방법", "제출서류",
)
EMPLOYMENT_LABELS = {
    "정규직", "일반정규직", "비정규직", "계약직", "일반계약직", "전문계약직", "기간제", "기간제근로자",
    "기간제 근로자", "무기계약직", "무기계약근로자", "공무직", "비상임", "인턴", "청년인턴",
    "청년 인턴", "체험형인턴", "체험형 인턴", "채용형인턴", "채용형 인턴", "파견직", "일용직",
    "단시간근로자", "단시간 근로자", "상용직",
}


class SourceValidationError(ValueError):
    """A fixed reason code, without a record, URL, or external exception text."""


def _fail(code):
    raise SourceValidationError(code)


def source_text(value):
    if not isinstance(value, str) or value.strip().casefold() in {"", "null", "none", "-"}:
        return ""
    return " ".join(value.split())


def source_date(value):
    """Return a KST instant and whether the source actually states its time.

    Date-only midnight is a comparison aid, not a claimed opening/closing time.
    Accepted formats mirror the collector's explicitly recognized formats.
    """
    if not isinstance(value, str):
        _fail("CLEANEYE_APPLICATION_DATE_INVALID")
    value = value.strip()
    has_time = False
    if re.fullmatch(r"[0-9]{8}", value):
        normalized = value[:4] + "-" + value[4:6] + "-" + value[6:8]
    elif re.fullmatch(r"[0-9]{14}", value):
        normalized = (value[:4] + "-" + value[4:6] + "-" + value[6:8]
                      + "T" + value[8:10] + ":" + value[10:12] + ":" + value[12:14])
        has_time = True
    else:
        match = re.fullmatch(
            r"([0-9]{4})([-./])([0-9]{2})\2([0-9]{2})"
            r"(?:[ T]([0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?)"
            r"(Z|[+-][0-9]{2}:[0-9]{2})?)?", value)
        if not match:
            _fail("CLEANEYE_APPLICATION_DATE_INVALID")
        normalized = f"{match[1]}-{match[3]}-{match[4]}"
        if match[5]:
            has_time = True
            normalized += "T" + match[5] + ("+00:00" if match[6] == "Z" else (match[6] or ""))
    try:
        instant = datetime.fromisoformat(normalized)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=KST)
        return instant.astimezone(KST), has_time
    except (ValueError, OverflowError):
        _fail("CLEANEYE_APPLICATION_DATE_INVALID")


def _aware(value, code):
    try:
        value = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError
        return value.astimezone(KST)
    except (TypeError, ValueError, OverflowError):
        _fail(code)


def _official_url(value, official_id):
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


def _recruitment_purpose(title, detail):
    # An opening's short title need not repeat "채용". Explicit stage/result
    # notices always lose, even when a source field mentions the original hire.
    if NON_RECRUITMENT_TITLE.search(title):
        _fail("CLEANEYE_NOT_RECRUITMENT")
    if RECRUITMENT_TITLE.search(title):
        return
    employment = {part.strip() for part in re.split(r"[,/;·|]", source_text(detail.get("고용형태 원문")))}
    if "공고" in title and employment & EMPLOYMENT_LABELS:
        if any(RECRUITMENT_TITLE.search(source_text(detail.get(field)))
               for field in ("구직자한마디", "직무세부내용")):
            return
        position, duties = source_text(detail.get("직위")), source_text(detail.get("직무세부내용"))
        if position and position in title and duties and position in duties:
            return
    _fail("CLEANEYE_RECRUITMENT_PURPOSE_UNCONFIRMED")


def is_recruitment_notice(title, detail):
    """Recognize grounded opening notices; stage/result exclusions take priority."""
    if not isinstance(title, str) or not isinstance(detail, dict):
        return False
    try:
        _recruitment_purpose(title, detail)
    except SourceValidationError:
        return False
    return True


def validate_cleaneye_feed(feed, now, *, scheduled=None, max_age_hours=24):
    """Validate snapshot identity/freshness, independent of eligible job count.

    Every canonical ID is safe to retain in a seen-ID baseline, including closed
    or otherwise ineligible records. Duplicate/malformed IDs invalidate the feed.
    """
    now = _aware(now, "CLEANEYE_REFERENCE_TIME_INVALID")
    scheduled = now if scheduled is None else _aware(scheduled, "CLEANEYE_REFERENCE_TIME_INVALID")
    if type(max_age_hours) not in (int, float) or not 0 < max_age_hours <= 24:
        _fail("CLEANEYE_FRESHNESS_INVALID")
    if (not isinstance(feed, dict) or feed.get("source") != SOURCE or feed.get("collectionStatus") != "verified"
            or not isinstance(feed.get("posts"), list)):
        _fail("CLEANEYE_SOURCE_UNVERIFIED")
    if not feed["posts"]:
        _fail("CLEANEYE_SOURCE_EMPTY")
    snapshot = _aware(feed.get("updated"), "CLEANEYE_SOURCE_TIME_INVALID")
    if snapshot > now or max(now, scheduled) - snapshot > timedelta(hours=max_age_hours):
        _fail("CLEANEYE_SOURCE_STALE")
    seen = set()
    for post in feed["posts"]:
        if (not isinstance(post, dict) or post.get("cleaneye") is not True or post.get("type") != "j"
                or post.get("source") != SOURCE_LABEL or not isinstance(post.get("cleaneyeDetail"), dict)
                or type(post.get("sourceMissing")) is not bool):
            _fail("CLEANEYE_NOTICE_IDENTITY")
        official_id = source_text(post["cleaneyeDetail"].get("공고 고유번호"))
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,118}", official_id)
                or post.get("id") != "cleaneye-" + official_id):
            _fail("CLEANEYE_NOTICE_IDENTITY")
        if post["id"] in seen:
            _fail("CLEANEYE_DUPLICATE_NOTICE")
        seen.add(post["id"])
    received = feed.get("last_received")
    if "last_received" in feed and (type(received) is not int or received < 0
            or received != sum(post["sourceMissing"] is False for post in feed["posts"])):
        _fail("CLEANEYE_SOURCE_COUNT_INVALID")
    return True


def validate_cleaneye_post(post, feed, now, *, scheduled=None, max_age_hours=24):
    """Return explicit official facts, or fail closed with a fixed reason code.

    Count and workplace are optional. Unknown values remain None/empty; callers
    that publish a claimed fact must separately require supporting evidence.
    """
    now = _aware(now, "CLEANEYE_REFERENCE_TIME_INVALID")
    scheduled = now if scheduled is None else _aware(scheduled, "CLEANEYE_REFERENCE_TIME_INVALID")
    validate_cleaneye_feed(feed, now, scheduled=scheduled, max_age_hours=max_age_hours)
    snapshot = _aware(feed.get("updated"), "CLEANEYE_SOURCE_TIME_INVALID")
    if (not isinstance(post, dict) or post.get("cleaneye") is not True or post.get("type") != "j"
            or post.get("source") != SOURCE_LABEL or post.get("alio") or post.get("gojobs")):
        _fail("CLEANEYE_NOTICE_IDENTITY")
    detail = post.get("cleaneyeDetail")
    if not isinstance(detail, dict):
        _fail("CLEANEYE_DETAIL_REQUIRED")
    official_id = source_text(detail.get("공고 고유번호"))
    if (official_id == "null" or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,118}", official_id)
            or post.get("id") != "cleaneye-" + official_id):
        _fail("CLEANEYE_NOTICE_IDENTITY")
    for value in (post.get("url"), post.get("src"), detail.get("공식 공고 URL")):
        if not _official_url(value, official_id):
            _fail("CLEANEYE_OFFICIAL_URL_INVALID")
    title, org = source_text(detail.get("채용제목")), source_text(detail.get("기관명"))
    if not title or not org or source_text(post.get("title")) != title or source_text(post.get("org")) != org:
        _fail("CLEANEYE_SOURCE_IDENTITY_CONFLICT")
    _recruitment_purpose(title, detail)
    if (post.get("receptionState") != "verified_open" or post.get("sourceMissing") is not False
            or any(post.get(key) for key in ("deadlineReviewReason", "dateReview", "dateReviewReason"))):
        _fail("CLEANEYE_NOT_VERIFIED_OPEN")
    status = source_text(detail.get("채용상태 원문"))
    if re.sub(r"\s+", "", status) not in OPEN_STATUS or source_text(post.get("sourceStatus")) != status:
        _fail("CLEANEYE_SOURCE_NOT_OPEN")
    start, start_has_time = source_date(detail.get("접수개시일 원문"))
    end, end_has_time = source_date(detail.get("접수마감일 원문"))
    listed_start, listed_start_has_time = source_date(post.get("start"))
    listed_end, _ = source_date(post.get("due"))
    if (listed_start != start or listed_start_has_time != start_has_time
            or post.get("dueHasTime") is not end_has_time
            or (listed_end != end if end_has_time else listed_end.date() != end.date())):
        _fail("CLEANEYE_APPLICATION_SOURCE_CONFLICT")
    if start > end or start == end and start_has_time and end_has_time:
        _fail("CLEANEYE_APPLICATION_PERIOD_REVERSED")
    if end.year >= now.year + 10:
        _fail("CLEANEYE_APPLICATION_NEEDS_REVIEW")
    for moment in (now, scheduled):
        if (moment < start if start_has_time else moment.date() <= start.date()):
            _fail("CLEANEYE_APPLICATION_NOT_OPEN")
        if (moment >= end if end_has_time else moment.date() >= end.date()):
            _fail("CLEANEYE_APPLICATION_CLOSED_OR_TIME_UNKNOWN")
    raw_count = source_text(detail.get("채용인원"))
    match = re.fullmatch(r"([1-9][0-9]{0,8})(?:\s*명)?", raw_count)
    return {
        "source": SOURCE, "official_id": official_id, "notice_id": post["id"],
        "org": org, "title": title, "employment": source_text(detail.get("고용형태 원문")),
        "count": int(match[1]) if match else None,
        "location": source_text(detail.get("근무지")),
        "institution_region": source_text(detail.get("기관 시도명")),
        "requirements": {key: detail[key] for key in REQUIREMENT_FIELDS if source_text(detail.get(key))},
        "application_period": {
            "start": start.isoformat() if start_has_time else start.date().isoformat(),
            "end": end.isoformat() if end_has_time else end.date().isoformat(),
            "start_date_only": not start_has_time, "date_only": not end_has_time,
        },
        "source_url": post["url"], "snapshot_at": snapshot.isoformat(),
    }


def eligible_cleaneye_post(post, feed, now):
    """Whether a consumer may consider this record; this never reserves/sends."""
    try:
        validate_cleaneye_post(post, feed, now)
    except SourceValidationError:
        return False
    return True
