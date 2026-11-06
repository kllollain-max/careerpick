"""Validate AI-written CareerPick copy before the existing publisher reserves it.

This module performs no network requests, generates no prose and never posts.
The writer must read the versioned master prompt and retain its factual review.
Only a ready result for the requested slot can cross this boundary. Semantic
fact checking remains the writer's responsibility; this boundary also checks
the current source identity, freshness, evidence, CTA, limits and deduplication.
"""

from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
CTA = "자세한 채용정보는 프로필 링크를 확인하세요."
SLOTS = (8, 12, 16, 20)
URL_RE = re.compile(
    r"https?\s*[:：]|www\s*[.．]|(?:[a-z0-9-]+\.)+(?:com|net|org|kr|io|co|gov|edu)(?:\b|/)",
    re.IGNORECASE,
)
OTHER_ACTION_RE = re.compile(
    r"(?:댓글|답글|저장|공유|팔로우|구독|좋아요|리포스트|DM|디엠)"
    r"[^\n.!?]{0,24}(?:주세요|하세요|해요|남겨|남기|부탁|해두|눌러|보내|달아|해\s*줘)",
    re.IGNORECASE,
)


class QueueValidationError(ValueError):
    """An intentionally terse reason suitable for a public diagnostic log."""


def _fail(reason):
    raise QueueValidationError(reason)


def _normal(value):
    return " ".join(str(value).split())


def fingerprint(value):
    """Hash canonical UTF-8 JSON, ignoring only ALIO detail's decimalDay.

    decimalDay changes as a calendar countdown without changing the notice.
    It is ignored only at the top level of an ALIO detail object identified by
    recrutPblntSn. All fields in a listing, and all nested values, are retained.
    """
    if isinstance(value, dict) and "recrutPblntSn" in value:
        value = {key: item for key, item in value.items() if key != "decimalDay"}
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        _fail("NON_CANONICAL_INPUT")
    return hashlib.sha256(encoded).hexdigest()


def _aware(value, reason):
    try:
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError
        return moment.astimezone(KST)
    except (ValueError, TypeError, OverflowError):
        _fail(reason)


def _fresh(value, now, scheduled, reason, max_age):
    moment = _aware(value, reason)
    if moment > now or now - moment > max_age or scheduled - moment > max_age:
        _fail(reason)
    return moment


def _policy(policy):
    if not isinstance(policy, dict) or type(policy.get("schema_version")) is not int or policy["schema_version"] != 1:
        _fail("POLICY_SCHEMA")
    if policy.get("cta") != CTA or policy.get("slots") != list(SLOTS):
        _fail("POLICY_CONTRACT")
    if not isinstance(policy.get("prompt_path"), str) or not policy["prompt_path"].strip():
        _fail("POLICY_PROMPT_PATH")
    digest = policy.get("prompt_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        _fail("POLICY_PROMPT_HASH")
    limit = policy.get("max_chars")
    age = policy.get("max_source_age_hours")
    if type(limit) is not int or not 1 <= limit <= 450:
        _fail("POLICY_LENGTH")
    if type(age) not in (int, float) or not 0 < age <= 24:
        _fail("POLICY_FRESHNESS")
    formats = policy.get("formats")
    if not isinstance(formats, dict) or set(formats) != {f"{hour:02}" for hour in SLOTS}:
        _fail("POLICY_FORMATS")
    if any(not isinstance(value, str) or not value.strip() for value in formats.values()) or len(set(formats.values())) != 4:
        _fail("POLICY_FORMATS")
    return limit, timedelta(hours=age)


def _slot(value):
    slot = _aware(value, "SLOT_TIMEZONE")
    if slot.hour not in SLOTS or slot.minute or slot.second or slot.microsecond:
        _fail("SLOT_NOT_SCHEDULED")
    return slot


def _ref_id(ref):
    if isinstance(ref, str):
        return ref.strip()
    if isinstance(ref, dict):
        for key in ("url", "ref", "location", "source"):
            if isinstance(ref.get(key), str) and ref[key].strip():
                return ref[key].strip()
    return ""


def _evidence_supported(evidence, source_ref, refs, detail):
    """Require the cited excerpt to be retained in the supplied source material."""
    if not isinstance(evidence, str) or len(_normal(evidence)) < 4:
        return False
    matching = [ref for ref in refs if _ref_id(ref) == source_ref]
    if not matching:
        return False
    excerpt = _normal(evidence)
    material = [str(value) for value in detail.values() if isinstance(value, (str, int))]
    for ref in matching:
        if isinstance(ref, dict):
            material.extend(str(ref[key]) for key in ("excerpt", "text", "evidence") if isinstance(ref.get(key), str))
    return any(excerpt in _normal(text) for text in material)


def _date_or_time(value, date_only, reason):
    if date_only:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            _fail(reason)
        try:
            return date.fromisoformat(value)
        except ValueError:
            _fail(reason)
    return _aware(value, reason)


def _date_spans(text, expected, detail):
    """Find a stated calendar date, including official Korean M/D shorthand."""
    full = list(re.finditer(
        r"(?<!\d)((?:19|20)\d{2}|\d{2})\s*(?:[./-]|년)\s*(\d{1,2})\s*(?:[./-]|월)\s*(\d{1,2})(?!\d)", text
    ))
    all_dates = [(match.start(), match.end()) for match in full]
    matches = []
    for match in full:
        year, month, day = map(int, match.groups())
        if year < 100:
            year += 2000
        if (year, month, day) == (expected.year, expected.month, expected.day):
            matches.append((match.start(), match.end()))
    year_context = any(str(expected.year) in str(value) for value in detail.values())
    for match in re.finditer(r"(?<!\d)(\d{1,2})\s*(?:[./-]|월)\s*(\d{1,2})(?!\d)", text):
        if any(match.start() < stop and match.end() > start for start, stop in all_dates):
            continue
        all_dates.append((match.start(), match.end()))
        if year_context and tuple(map(int, match.groups())) == (expected.month, expected.day):
            matches.append((match.start(), match.end()))
    return sorted(matches), sorted(all_dates)


def _stated_times(text):
    found = []
    patterns = (
        r"(?<!\d)(\d{1,2})\s*:\s*(\d{2})(?:\s*:\s*(\d{2}))?(?!\d)",
        r"(?<!\d)(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?(?:\s*(\d{1,2})\s*초)?",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            hour, minute, second = (int(value or 0) for value in match.groups())
            prefix = text[max(0, match.start() - 8):match.start()]
            if re.search(r"오후\s*$", prefix) and hour < 12:
                hour += 12
            elif re.search(r"오전\s*$", prefix) and hour == 12:
                hour = 0
            if hour < 24 and minute < 60 and second < 60:
                found.append((hour, minute, second))
    return found


def _period_matches_excerpt(period, start, end, detail):
    text = period["evidence"]
    for side, value, date_only in (
        ("START", start, period.get("start_date_only", False)),
        ("END", end, period["date_only"]),
    ):
        day = value if date_only else value.date()
        matches, dates = _date_spans(text, day, detail)
        if not matches:
            _fail("APPLICATION_" + side + "_EVIDENCE_MISMATCH")
        _, stop = matches[0] if side == "START" else matches[-1]
        next_date = next((a for a, _ in dates if a >= stop), len(text))
        stated = _stated_times(text[stop:next_date])
        if not date_only and (value.hour, value.minute, value.second) not in stated:
            _fail("APPLICATION_" + side + "_TIME_EVIDENCE_MISMATCH")
        if date_only and stated:
            _fail("APPLICATION_" + side + "_PRECISION_CONFLICT")


def _application_period(review, refs, detail, now, scheduled):
    period = review.get("application_period")
    if not isinstance(period, dict) or type(period.get("date_only")) is not bool:
        _fail("APPLICATION_PERIOD_REQUIRED")
    if not _evidence_supported(period.get("evidence"), period.get("source_ref"), refs, detail):
        _fail("APPLICATION_EVIDENCE_REQUIRED")
    start_date_only = period.get("start_date_only", False)
    if type(start_date_only) is not bool:
        _fail("APPLICATION_START_INVALID")
    start = _date_or_time(period.get("start"), start_date_only, "APPLICATION_START_INVALID")
    end = _date_or_time(period.get("end"), period["date_only"], "APPLICATION_END_INVALID")
    start_day = start if start_date_only else start.date()
    end_day = end if period["date_only"] else end.date()
    if start_day > end_day or (not start_date_only and not period["date_only"] and start >= end):
        _fail("APPLICATION_PERIOD_REVERSED")
    for moment in (now, scheduled):
        if start_date_only:
            if moment.date() < start:
                _fail("APPLICATION_NOT_OPEN")
            if moment.date() == start:
                if period.get("current_open_verified") is not True or not _evidence_supported(
                    period.get("current_open_evidence"), period.get("source_ref"), refs, detail
                ):
                    _fail("APPLICATION_START_TIME_UNKNOWN")
        elif moment < start:
            _fail("APPLICATION_NOT_OPEN")
        if period["date_only"]:
            if moment.date() > end:
                _fail("APPLICATION_CLOSED")
            if moment.date() == end:
                _fail("APPLICATION_END_TIME_UNKNOWN")
        elif moment >= end:
            _fail("APPLICATION_CLOSED")
    _period_matches_excerpt(period, start, end, detail)
    return end_day.isoformat(), period


def _site_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https" and parsed.hostname == "kllollain-max.github.io"
            and not parsed.username and not parsed.password and parsed.port in (None, 443)
            and (parsed.path == "/careerpick" or parsed.path.startswith("/careerpick/"))
            and not re.search(r"(?:^|/)\.\.(?:/|$)|%2e|%2f|%5c|\\", parsed.path, re.IGNORECASE)
        )
    except ValueError:
        return False


def _profile(review, notice_id, now, scheduled, max_age):
    target = review.get("profile_target")
    if not isinstance(target, dict) or target.get("verified") is not True or target.get("notice_id") != notice_id:
        _fail("PROFILE_TARGET_UNVERIFIED")
    if not _site_url(target.get("url")) or not _site_url(target.get("notice_url")):
        _fail("PROFILE_TARGET_UNTRUSTED")
    _fresh(target.get("checked_at"), now, scheduled, "PROFILE_TARGET_STALE", max_age)


def _source(entry, source_doc, details, now, scheduled, max_age):
    if not isinstance(source_doc, dict) or not isinstance(source_doc.get("posts"), list) or not isinstance(details, dict):
        _fail("SOURCE_SCHEMA")
    notice_id = entry.get("notice_id")
    if not isinstance(notice_id, str) or not re.fullmatch(r"a[1-9][0-9]*", notice_id):
        _fail("NOTICE_ID_INVALID")
    matches = [post for post in source_doc["posts"] if isinstance(post, dict) and post.get("id") == notice_id]
    if len(matches) != 1:
        _fail("SOURCE_NOTICE_NOT_UNIQUE")
    post, detail = matches[0], details.get(notice_id)
    if not isinstance(detail, dict) or str(detail.get("recrutPblntSn")) != notice_id[1:]:
        _fail("SOURCE_DETAIL_IDENTITY")
    if fingerprint(post) != entry.get("source_post_sha256") or fingerprint(detail) != entry.get("source_detail_sha256"):
        _fail("SOURCE_CHANGED")
    if _normal(post.get("org")) != _normal(detail.get("instNm")) or _normal(post.get("title")) != _normal(detail.get("recrutPbancTtl")):
        _fail("SOURCE_IDENTITY_CONFLICT")
    if detail.get("ongoingYn") != "Y" or re.search(r"취\s*소|철\s*회|모집\s*종료", str(detail.get("recrutPbancTtl", ""))):
        _fail("SOURCE_NOT_CURRENT")
    ops = source_doc.get("_operations")
    if not isinstance(ops, dict) or ops.get("source") != "alio" or not isinstance(ops.get("unconfirmed_ids"), list):
        _fail("SOURCE_OPERATIONS_REQUIRED")
    if notice_id in ops["unconfirmed_ids"]:
        _fail("SOURCE_NOTICE_UNCONFIRMED")
    source_time = _aware(source_doc.get("updated"), "SOURCE_TIME_INVALID")
    snapshot_time = _aware(ops.get("snapshot_at"), "SOURCE_SNAPSHOT_INVALID")
    verified_time = _fresh(ops.get("last_success_at"), now, scheduled, "SOURCE_STALE", max_age)
    if source_time != snapshot_time or source_time > verified_time:
        _fail("SOURCE_SNAPSHOT_MISMATCH")
    return notice_id, post, detail


def _fact_supported(field, value, review, refs, detail):
    facts = review.get("fact_evidence", [])
    if not isinstance(facts, list):
        return False
    for fact in facts:
        if not isinstance(fact, dict) or fact.get("field") != field or type(fact.get("value")) is not type(value) or fact.get("value") != value:
            continue
        if not _evidence_supported(fact.get("excerpt"), fact.get("source_ref"), refs, detail):
            continue
        excerpt = _normal(fact["excerpt"])
        if type(value) is int:
            if re.search(r"(?<!\d)" + re.escape(str(value)) + r"(?!\d)", excerpt):
                return True
        elif _normal(value) in excerpt:
            return True
    return False


def _count(value):
    text = str(value).strip()
    match = re.fullmatch(r"([1-9][0-9]*)(?:\s*명)?", text)
    return int(match[1]) if match else None


def _employment(value):
    return {_normal(part) for part in re.split(r"[,|·/]", str(value)) if _normal(part)}


def _image(entry, post, detail, review, refs, end_date, period):
    image = entry.get("image_job")
    if not isinstance(image, dict) or image.get("id") != entry["notice_id"]:
        _fail("IMAGE_NOTICE_IDENTITY")
    if _normal(image.get("org")) != _normal(detail.get("instNm")):
        _fail("IMAGE_ORGANIZATION_CONFLICT")
    title = image.get("title")
    official_title = _normal(detail.get("recrutPbancTtl"))
    if not isinstance(title, str) or len(_normal(title)) < 3:
        _fail("IMAGE_TITLE_INVALID")
    if _normal(title) not in official_title and not _fact_supported("title", title, review, refs, detail):
        _fail("IMAGE_TITLE_UNSUPPORTED")
    count = image.get("count")
    if count is not None:
        if type(count) is not int or count < 1:
            _fail("IMAGE_COUNT_INVALID")
        if count != _count(detail.get("recrutNope")) and not _fact_supported("count", count, review, refs, detail):
            _fail("IMAGE_COUNT_UNSUPPORTED")
    employment = image.get("employment")
    raw_employment = _employment(detail.get("hireTypeNmLst", ""))
    chosen_employment = _employment(employment)
    if not isinstance(employment, str) or not raw_employment or not chosen_employment or not chosen_employment <= raw_employment:
        if not _fact_supported("employment", employment, review, refs, detail):
            _fail("IMAGE_EMPLOYMENT_UNSUPPORTED")
    if len(raw_employment) > 1 and chosen_employment != raw_employment:
        if not _fact_supported("employment", employment, review, refs, detail):
            _fail("IMAGE_EMPLOYMENT_UNIT_UNVERIFIED")
    location = image.get("location")
    raw_location = _normal(detail.get("workRgnNmLst", ""))
    if not isinstance(location, str) or not location.strip():
        _fail("IMAGE_LOCATION_REQUIRED")
    if _normal(location) not in raw_location and not _fact_supported("location", location, review, refs, detail):
        _fail("IMAGE_LOCATION_UNSUPPORTED")
    if image.get("due") != end_date:
        _fail("IMAGE_APPLICATION_DEADLINE_CONFLICT")
    label = image.get("deadline_label")
    if period["date_only"]:
        expected_label = end_date
    else:
        end_time = _aware(period["end"], "APPLICATION_END_INVALID")
        if end_time.microsecond:
            _fail("APPLICATION_END_PRECISION_UNSUPPORTED")
        expected_label = end_time.strftime("%Y-%m-%d %H:%M:%S" if end_time.second else "%Y-%m-%d %H:%M")
    if not isinstance(label, str) or len(label) > 32 or label != expected_label:
        _fail("IMAGE_DEADLINE_LABEL_CONFLICT")
    for field in ("org", "title", "employment", "location"):
        if URL_RE.search(str(image.get(field, ""))):
            _fail("IMAGE_FIELD_CONTAINS_URL")
    # Retain only the agreed rendering inputs. Do not pass arbitrary URLs or
    # executable/rendering options from a writer-produced object to the renderer.
    return {key: deepcopy(image.get(key)) for key in (
        "id", "org", "title", "count", "due", "employment", "location", "deadline_label"
    )}


def _history(history, notice_id, format_id, scheduled, body, org):
    if not isinstance(history, dict) or not isinstance(history.get("records"), list) or not isinstance(history.get("posted_ids"), list):
        _fail("HISTORY_SCHEMA")
    if notice_id in {str(value) for value in history["posted_ids"]}:
        _fail("NOTICE_ALREADY_USED")
    for record in history["records"]:
        if not isinstance(record, dict):
            _fail("HISTORY_SCHEMA")
        job_ids = record.get("job_ids", [])
        if not isinstance(job_ids, list) or (record.get("text") is not None and not isinstance(record["text"], str)):
            _fail("HISTORY_SCHEMA")
        if record.get("job_id") == notice_id or notice_id in job_ids:
            _fail("NOTICE_ALREADY_USED")
        stamp = record.get("scheduled_at")
        if stamp:
            other_slot = _aware(stamp, "HISTORY_SLOT_INVALID")
            if other_slot == scheduled:
                _fail("SLOT_ALREADY_RESERVED")
            if other_slot.date() == scheduled.date() and record.get("status") in ("pending", "published") and record.get("format_id") == format_id:
                _fail("DAILY_FORMAT_ALREADY_USED")
    previous = [record for record in history["records"] if record.get("status") == "published" and record.get("text")][-10:]
    for record in previous:
        if record["text"].strip() == body.strip():
            _fail("BODY_ALREADY_USED")
    if previous:
        first = body.splitlines()[0].strip()
        old_first = previous[-1]["text"].splitlines()[0].strip()
        if first == old_first:
            _fail("CONSECUTIVE_HOOK_DUPLICATE")


def _structure(body, format_id):
    content = body[:-len("\n\n" + CTA)]
    paragraphs = [part for part in content.split("\n\n") if part.strip()]
    list_lines = re.findall(r"(?m)^\s*(?:\d{1,2}[.)]|[□☐✓✔•-])\s*\S.*$", content)
    label_lines = re.findall(r"(?m)^[^\n:：]{1,18}[:：]\s*\S.*$", content)
    if format_id == "key_facts" and len(label_lines) < 2:
        _fail("FORMAT_FACT_LABELS_REQUIRED")
    if format_id == "application_checklist" and len(list_lines) < 2:
        _fail("FORMAT_CHECKLIST_REQUIRED")
    if format_id in ("reader_story", "job_explainer"):
        if len(paragraphs) < 3 or len(list_lines) >= 2 or len(label_lines) >= 2:
            _fail("FORMAT_NARRATIVE_PARAGRAPHS_REQUIRED")
    if format_id == "job_explainer" and not (
        re.search(r"업무|맡|관리|담당|일해|근무", content) and re.search(r"자격|면허|경력|필수|지원|요건|기사", content)
    ):
        _fail("FORMAT_JOB_AND_REQUIREMENTS_REQUIRED")


def validate_entry(entry, scheduled, now, history, source_doc, details, policy):
    """Validate one ready entry, including a future slot, without side effects.

    The caller verifies the actual master-prompt file bytes against the policy.
    source_doc must contain the matched operations-status.json under _operations.
    Image assignment/creation and final API account checks occur in the publisher.
    """
    limit, max_age = _policy(policy)
    scheduled = _slot(scheduled)
    now = _aware(now, "NOW_TIMEZONE")
    if not isinstance(entry, dict) or _slot(entry.get("scheduled_at")) != scheduled:
        _fail("ENTRY_SLOT_MISMATCH")
    expected_format = policy["formats"][f"{scheduled.hour:02}"]
    if entry.get("format_id") != expected_format:
        _fail("ENTRY_FORMAT_MISMATCH")
    if entry.get("prompt_sha256") != policy["prompt_sha256"]:
        _fail("ENTRY_PROMPT_MISMATCH")
    notice_id, post, detail = _source(entry, source_doc, details, now, scheduled, max_age)
    writer = entry.get("writer")
    if not isinstance(writer, dict) or writer.get("status") != "ready":
        _fail("WRITER_NOT_READY")
    if writer.get("draft_text") is not None or writer.get("reply_texts") != []:
        _fail("WRITER_OUTPUT_CONTRACT")
    body = writer.get("post_text")
    if not isinstance(body, str) or not body.strip() or body != body.strip() or len(body) > limit:
        _fail("BODY_LENGTH_OR_WHITESPACE")
    if body.count(CTA) != 1 or not body.endswith("\n\n" + CTA):
        _fail("BODY_CTA_CONTRACT")
    if URL_RE.search(body) or "#" in body or "＃" in body:
        _fail("BODY_LINK_OR_HASHTAG")
    if OTHER_ACTION_RE.search(body):
        _fail("BODY_OTHER_ACTION")
    if _normal(detail["instNm"]) not in _normal(body):
        _fail("BODY_ORGANIZATION_MISSING")
    _structure(body, expected_format)
    review = writer.get("review")
    if not isinstance(review, dict) or review.get("notice_id") != notice_id:
        _fail("REVIEW_NOTICE_IDENTITY")
    if _aware(review.get("scheduled_at"), "REVIEW_SLOT_INVALID") != scheduled:
        _fail("REVIEW_SLOT_MISMATCH")
    if review.get("verification_basis") not in ("checked_official_source", "provided_verified_data"):
        _fail("REVIEW_BASIS_UNVERIFIED")
    if review.get("missing_or_conflicting") != [] or review.get("cta_check") != "passed":
        _fail("REVIEW_UNRESOLVED")
    if review.get("media_check") not in ("not_supplied", "passed") or review.get("length_check") != "measured_within_limit":
        _fail("REVIEW_MEDIA_OR_LENGTH")
    for field in ("target_reader", "central_message", "pattern_id"):
        if not isinstance(review.get(field), str) or not review[field].strip():
            _fail("REVIEW_EDITORIAL_FIELDS")
    if not re.fullmatch(r"P(?:[1-9]|10)", review["pattern_id"]):
        _fail("REVIEW_PATTERN_INVALID")
    if not isinstance(review.get("pre_publish_checks"), list) or not isinstance(review.get("omitted_optional_facts"), list):
        _fail("REVIEW_FIELDS_MISSING")
    refs = review.get("source_refs")
    if not isinstance(refs, list) or not refs or any(not _ref_id(ref) for ref in refs):
        _fail("REVIEW_SOURCES_MISSING")
    checked_at = _fresh(review.get("checked_at"), now, scheduled, "REVIEW_SOURCE_STALE", max_age)
    reference_at = _aware(review.get("reference_at"), "REVIEW_REFERENCE_TIME")
    if reference_at > now or reference_at < checked_at:
        _fail("REVIEW_REFERENCE_TIME")
    for ref in refs:
        if isinstance(ref, dict) and ref.get("checked_at") is not None:
            _fresh(ref["checked_at"], now, scheduled, "REVIEW_SOURCE_STALE", max_age)
    end_date, period = _application_period(review, refs, detail, now, scheduled)
    _profile(review, notice_id, now, scheduled, max_age)
    image_job = _image(entry, post, detail, review, refs, end_date, period)
    _history(history, notice_id, expected_format, scheduled, body, detail["instNm"])
    has_published = any(record.get("status") == "published" and record.get("text") for record in history["records"])
    allowed_repetition = ("checked", "partial") if has_published else ("checked", "no_history")
    if review.get("repetition_check") not in allowed_repetition:
        _fail("REVIEW_REPETITION_UNCHECKED")
    return {
        "job_id": notice_id,
        "text": body,
        "reply_text": "",
        "engagement_text": "",
        "content_type": "master_job",
        "format_id": expected_format,
        "writer_prompt_sha256": policy["prompt_sha256"],
        "writer_source_post_sha256": entry["source_post_sha256"],
        "writer_source_detail_sha256": entry["source_detail_sha256"],
        "writer_review": deepcopy(review),
        "image_job": image_job,
        "queue_entry_sha256": fingerprint(entry),
    }


def select_ready(queue, scheduled, now, history, source_doc, details, policy):
    """Consume only the exact current slot; never catch up an expired slot."""
    scheduled = _slot(scheduled)
    now = _aware(now, "NOW_TIMEZONE")
    if not scheduled <= now < scheduled + timedelta(hours=2):
        _fail("PUBLISH_SLOT_NOT_CURRENT")
    if not isinstance(queue, dict) or type(queue.get("schema_version")) is not int or queue["schema_version"] != 1 or not isinstance(queue.get("entries"), list):
        _fail("QUEUE_SCHEMA")
    matches = []
    seen_slots = set()
    ready_notices = set()
    for entry in queue["entries"]:
        if not isinstance(entry, dict):
            _fail("QUEUE_SCHEMA")
        slot = _slot(entry.get("scheduled_at"))
        if slot in seen_slots:
            _fail("QUEUE_DUPLICATE_SLOT")
        seen_slots.add(slot)
        if isinstance(entry.get("writer"), dict) and entry["writer"].get("status") == "ready":
            notice = entry.get("notice_id")
            if not isinstance(notice, str):
                _fail("NOTICE_ID_INVALID")
            if notice in ready_notices:
                _fail("QUEUE_DUPLICATE_NOTICE")
            ready_notices.add(notice)
        if slot == scheduled:
            matches.append(entry)
    if not matches:
        _fail("QUEUE_SLOT_MISSING")
    return validate_entry(matches[0], scheduled, now, history, source_doc, details, policy)
