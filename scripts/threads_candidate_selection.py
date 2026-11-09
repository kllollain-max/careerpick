"""Read-only ranking over all connected saved feeds, before a writer-input cap.

This is source triage, not a claim that every official attachment was read.
ALIO publication dates and notice totals never stand in for application dates
or a selected recruiting unit. Unresolved notices remain an uncapped review
list. Independent official reviews can resolve them. The live queue instead
protects prepared notices from reassignment.
"""
from collections import Counter
from datetime import datetime, timedelta
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from scripts.cleaneye_source_adapter import (
    SourceValidationError, validate_cleaneye_feed, validate_cleaneye_post,
)
from scripts.threads_writer_queue import (
    QueueValidationError, _application_period, _fact_supported, fingerprint,
    validate_entry,
)

KST = ZoneInfo("Asia/Seoul")
POLICY_ID = "careerpick-threads-selection-v2-20261109"
DATE_RE = re.compile(r"(?<!\d)(20\d{2})\s*(?:[./-]|년)\s*(\d{1,2})\s*(?:[./-]|월)\s*(\d{1,2})(?:일|\.)?(?!\d)")
TIME_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?::\s*(\d{2})(?::\s*(\d{2}))?|시(?:\s*(\d{1,2})\s*분)?)(?!\d)")
RECEPTION_RE = re.compile(r"(?:응시\s*원서|입사\s*지원서|지원서|서류|원서)?\s*접수\s*(?:기간|일정)?\s*[:：]?|지원\s*기간\s*[:：]?")
NON_APPLICATION_PREFIX = re.compile(r'면접|이의\s*신청|증빙|증명|합격|추가\s*서류|보완\s*서류|임용|등록')
NON_RECRUITMENT_RE = re.compile(r"취\s*소|철\s*회|모집\s*종료|합격자|합격\s*발표|전형\s*결과|결과\s*(?:공고|발표)")


def _normal(value):
    return " ".join(str(value or "").split())


def exact_count(value):
    """Unknown, approximate and zero-padded placeholders remain None."""
    if type(value) is int:
        return value if value > 0 else None
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"([1-9][0-9]*)(?:\s*명)?", value.strip())
    return int(match[1]) if match else None


def employment_rank(value):
    labels = {_normal(x) for x in re.split(r"[,/;·|]", _normal(value)) if _normal(x)}
    if labels and labels <= {"정규직", "일반정규직"}:
        return 0
    if labels and labels <= {"무기계약직", "무기계약근로자", "공무직"}:
        return 1
    if labels and labels <= {"비정규직", "기간제", "기간제근로자", "기간제 근로자", "계약직", "일반계약직", "전문계약직"}:
        return 2
    if labels and all("인턴" in x for x in labels):
        return 3
    return 4  # Mixed/unknown status does not become regular employment.


def _aware(value):
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise ValueError("timezone required")
    return moment.astimezone(KST)


def canonical_notice_url(value):
    """Only exact URL identity; never merge based on institution alone."""
    try:
        url = urlsplit(str(value or ""))
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
            return None
        query = [(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
        return urlunsplit((url.scheme.lower(), url.netloc.lower(), url.path.rstrip("/"), urlencode(sorted(query)), ""))
    except ValueError:
        return None


def _identities(post):
    org, title = _normal(post.get("org")), _normal(post.get("title"))
    if not org or not title:
        return set()
    return {(org, title, url) for key in ("src", "url")
            if (url := canonical_notice_url(post.get(key)))}


def _period_point(match, following):
    year, month, day = map(int, match.groups())
    date = datetime(year, month, day, tzinfo=KST)
    # Only the clock immediately after this date/weekday is relevant. A later
    # unrelated announcement clock must not be captured as the reception time.
    clock = TIME_RE.search(following)
    if clock:
        prefix = following[:clock.start()]
        if not re.fullmatch(r"[\s.()\[\]월화수목금토일요일오전후]*", prefix):
            clock = None
    if clock:
        hour = int(clock[1]); minute = int(clock[2] or clock[4] or 0); second = int(clock[3] or 0)
        if "오후" in following[:clock.start()] and hour < 12:
            hour += 12
        elif "오전" in following[:clock.start()] and hour == 12:
            hour = 0
        return date.replace(hour=hour, minute=minute, second=second).isoformat(), False
    return date.date().isoformat(), True


def alio_application_period(detail, now):
    """Recognize one explicit reception range in official saved narrative.

    Conservative: two full-year dates, a reception label and range separator.
    A missing/ambiguous range needs official review; pbanc dates are never read.
    """
    periods = []
    for field in ("scrnprcdrMthdExpln", "aplyQlfcCn"):
        for line in str(detail.get(field, "")).splitlines():
            label = RECEPTION_RE.search(line)
            if not label:
                continue
            # A source can contain later-stage submission windows as well as
            # the original application window. Preserve the heading context.
            if NON_APPLICATION_PREFIX.search(line[:label.end()]):
                continue
            excerpt = line[label.start():].strip()
            dates = list(DATE_RE.finditer(excerpt))
            if len(dates) != 2 or not re.search(r"[~∼～]|부터", excerpt[dates[0].end():dates[1].start()]):
                continue
            try:
                start, start_only = _period_point(dates[0], excerpt[dates[0].end():dates[1].start()])
                end, end_only = _period_point(dates[1], excerpt[dates[1].end():])
            except ValueError:
                continue
            ref = "alio-detail.json#" + str(detail.get("recrutPblntSn", "")) + "/" + field
            period = {"start": start, "end": end, "start_date_only": start_only,
                      "date_only": end_only, "source_ref": ref, "evidence": excerpt}
            refs = [{"ref": ref, "excerpt": excerpt}]
            try:
                _application_period({"application_period": period}, refs, detail, now, now)
            except QueueValidationError as error:
                periods.append((period, str(error)))
            else:
                periods.append((period, None))
    unique = {(p["start"], p["end"], p["start_date_only"], p["date_only"]): (p, err) for p, err in periods}
    if len(unique) != 1:
        return None, "APPLICATION_PERIOD_AMBIGUOUS" if unique else "APPLICATION_PERIOD_REVIEW_REQUIRED"
    return next(iter(unique.values()))


def _source_status(source, now, max_age):
    operations = source.get("_operations", {})
    try:
        if operations.get("source") != "alio" or not isinstance(operations.get("unconfirmed_ids"), list):
            return "SOURCE_OPERATIONS_REQUIRED"
        snapshot, updated, checked = map(_aware, (operations.get("snapshot_at"), source.get("updated"), operations.get("last_success_at")))
        if snapshot != updated or snapshot > checked:
            return "SOURCE_SNAPSHOT_MISMATCH"
        if checked > now or now - checked > timedelta(hours=max_age):
            return "SOURCE_STALE"
    except (TypeError, ValueError):
        return "SOURCE_TIME_INVALID"
    return "verified_snapshot"


def _reviewed(entries, history, source, details, policy, now):
    accepted, errors = {}, []
    for entry in entries or []:
        jid = entry.get("notice_id") if isinstance(entry, dict) else None
        try:
            selected = validate_entry(entry, _aware(entry["scheduled_at"]), now, history, source, details, policy)
            if jid in accepted:
                raise ValueError("DUPLICATE_REVIEW_NOTICE")
        except (QueueValidationError, KeyError, TypeError, ValueError) as error:
            errors.append({"notice_id": jid, "reason": str(error) if isinstance(error, (QueueValidationError, ValueError)) else "REVIEW_INVALID"})
            continue
        review, unit = selected["writer_review"], selected["image_job"]
        refs = review["source_refs"]
        detail = (next(p["cleaneyeDetail"] for p in source["_cleaneye"]["posts"] if p["id"] == jid)
                  if str(jid).startswith("cleaneye-") else details[jid])
        # An explicit unit count/title evidence pair is needed even if the count
        # happens to equal the notice total accepted by the older queue contract.
        scoped = (_fact_supported("title", unit["title"], review, refs, detail)
                  and _fact_supported("count", unit["count"], review, refs, detail)
                  and any(fact.get("field") == "count" and fact.get("value") == unit["count"]
                          and _normal(unit["title"]) in _normal(fact.get("excerpt"))
                          for fact in review.get("fact_evidence", []) if isinstance(fact, dict)))
        accepted[jid] = {"application_period": review["application_period"], "employment": unit["employment"],
                         "unit_title": unit["title"], "unit_count": unit["count"] if scoped else None,
                         "unit_scope": "reviewed_unit" if scoped else "unit_count_unconfirmed",
                         "official_checked_at": review["checked_at"]}
    return accepted, errors


def _queued_notice_ids(entries, now):
    """Keep ready drafts out of selection through their publication window."""
    ids = set()
    for entry in entries or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("writer"), dict):
            continue
        jid = entry.get("notice_id")
        if entry["writer"].get("status") != "ready" or not isinstance(jid, str) or not jid:
            continue
        try:
            scheduled = _aware(entry.get("scheduled_at"))
        except (TypeError, ValueError):
            # A malformed ready reservation must not make the notice selectable.
            ids.add(jid)
            continue
        if scheduled + timedelta(hours=2) > now:
            ids.add(jid)
    return ids


def build_selection(source, details, history, policy, now, limit=24, reviewed_entries=None, *, queued_entries=None):
    if type(limit) is not int or not 1 <= limit <= 60:
        raise ValueError("limit must be 1 to 60")
    now = _aware(now)
    blocked = {str(x) for x in history.get("posted_ids", [])}
    for record in history.get("records", []):
        blocked.update(str(x) for x in [record.get("job_id"), *record.get("job_ids", [])] if x)
    queued = _queued_notice_ids(queued_entries, now)
    protected = blocked | queued
    reviews, review_errors = _reviewed(reviewed_entries, history, source, details, policy, now)
    cleaneye = source.get("_cleaneye", {})
    alio_status = _source_status(source, now, policy["max_source_age_hours"])
    try:
        validate_cleaneye_feed(cleaneye, now, max_age_hours=policy["max_source_age_hours"])
        cleaneye_status = "verified"
    except SourceValidationError as error:
        cleaneye_status = str(error)
    pools = {"alio": source.get("posts", []), "cleaneye": cleaneye.get("posts", []) if isinstance(cleaneye, dict) else []}
    blocked_identities = set()
    for posts in pools.values():
        for post in posts:
            if isinstance(post, dict) and post.get("id") in protected:
                blocked_identities.update(_identities(post))
    sources = {
        "alio": {"status": alio_status, "snapshot_at": source.get("updated"), "source_checked_at": source.get("_operations", {}).get("last_success_at")},
        "cleaneye": {"status": cleaneye_status, "snapshot_at": cleaneye.get("updated") if isinstance(cleaneye, dict) else None,
                     "source_checked_at": cleaneye.get("updated") if isinstance(cleaneye, dict) else None},
    }
    rows, eligible, seen = [], [], set()
    unconfirmed = set(source.get("_operations", {}).get("unconfirmed_ids", []))
    for source_name, posts in pools.items():
        sources[source_name]["total_records"] = len(posts)
        for post in posts:
            row = {"source": source_name, "notice_id": post.get("id") if isinstance(post, dict) else None,
                   "decision": "excluded", "reasons": [], "official_checked_at": None,
                   "unit_count": None, "unit_scope": "unit_count_unconfirmed", "interest": None,
                   "audience_breadth": None, "application_period": None}
            rows.append(row)
            if not isinstance(post, dict) or not isinstance(post.get("id"), str):
                row["reasons"] = ["SOURCE_NOTICE_IDENTITY"]; continue
            jid = post["id"]
            if jid in seen:
                row["reasons"] = ["DUPLICATE_SOURCE_ID"]; continue
            seen.add(jid)
            row.update(org=post.get("org"), title=post.get("title"))
            if jid in blocked:
                row["reasons"] = ["NOTICE_ALREADY_USED"]; continue
            if jid in queued:
                row["reasons"] = ["NOTICE_ALREADY_QUEUED"]; continue
            if _identities(post) & blocked_identities:
                row["reasons"] = ["EXACT_CROSS_SOURCE_NOTICE_ALREADY_USED"]; continue
            context = None
            if source_name == "cleaneye":
                if cleaneye_status != "verified":
                    row["reasons"] = [cleaneye_status]; continue
                try:
                    context = validate_cleaneye_post(post, cleaneye, now, max_age_hours=policy["max_source_age_hours"])
                except SourceValidationError as error:
                    row["reasons"] = [str(error)]; continue
                detail = post["cleaneyeDetail"]
                row.update(employment=context["employment"], notice_total_count=context["count"],
                           notice_total_count_raw=detail.get("채용인원"), application_period=context["application_period"],
                           application_status="source_verified_open")
            else:
                if alio_status != "verified_snapshot":
                    row["reasons"] = [alio_status]; continue
                detail = details.get(jid)
                if jid in unconfirmed:
                    row["reasons"] = ["SOURCE_NOTICE_UNCONFIRMED"]; continue
                if not isinstance(detail, dict) or str(detail.get("recrutPblntSn")) != jid.removeprefix("a"):
                    row["reasons"] = ["SOURCE_DETAIL_IDENTITY"]; continue
                if _normal(post.get("org")) != _normal(detail.get("instNm")) or _normal(post.get("title")) != _normal(detail.get("recrutPbancTtl")):
                    row["reasons"] = ["SOURCE_IDENTITY_CONFLICT"]; continue
                if detail.get("ongoingYn") != "Y" or NON_RECRUITMENT_RE.search(_normal(post.get("title"))):
                    row["reasons"] = ["SOURCE_NOT_CURRENT_RECRUITMENT"]; continue
                try:
                    parsed = urlsplit(str(post.get("url", "")))
                    url_valid = parsed.scheme == "https" and parsed.hostname in {"job.alio.go.kr", "kllollain-max.github.io"} and not parsed.username and not parsed.password
                except ValueError:
                    url_valid = False
                if not url_valid:
                    row["reasons"] = ["SOURCE_OFFICIAL_URL_INVALID"]; continue
                row.update(employment=detail.get("hireTypeNmLst", ""), notice_total_count=exact_count(detail.get("recrutNope")),
                           notice_total_count_raw=detail.get("recrutNope"))
                period, error = alio_application_period(detail, now)
                row["application_period"] = period
                if error and jid not in reviews:
                    if error in {"APPLICATION_PERIOD_REVIEW_REQUIRED", "APPLICATION_PERIOD_AMBIGUOUS"}:
                        row.update(decision="review_required", application_status="unconfirmed", reasons=[error])
                    else:
                        row["reasons"] = [error]
                    continue
                row["application_status"] = "source_narrative_open"
            if jid in reviews:
                row.update(reviews[jid], application_status="reviewed_open")
            row.update(decision="eligible_for_official_review", employment_priority=employment_rank(row.get("employment")),
                       source_post_sha256=fingerprint(post), source_detail_sha256=fingerprint(detail))
            row["reasons"] = ["OFFICIAL_DETAIL_AND_UNIT_REVIEW_REQUIRED"] if row["unit_count"] is None else []
            eligible.append((row, post, detail, context))
    # Exact identity deduplication occurs before limiting. No fuzzy scores or
    # institution-level deduplication that could erase distinct recruiting units.
    def key(item):
        row = item[0]
        end = row["application_period"]["end"]
        return (row["employment_priority"], row["unit_count"] is None,
                -(row["unit_count"] or 0), end[:10], end[10:], row["notice_id"])
    eligible.sort(key=key)
    unique, identities = [], set()
    for item in eligible:
        row, post, _, _ = item
        signatures = _identities(post)
        if signatures & identities:
            row.update(decision="excluded", reasons=["EXACT_CROSS_SOURCE_DUPLICATE"])
            continue
        identities.update(signatures)
        unique.append(item)
    items = []
    for rank, (row, post, detail, context) in enumerate(unique, 1):
        row["rank_before_limit"] = rank
        row["included_in_writer_input"] = rank <= limit
        if rank > limit:
            continue
        items.append({"notice_id": row["notice_id"],
                      **({"source": "cleaneye", "official_id": context["official_id"], "source_context": context} if context else {}),
                      "source_post": post, "source_detail": detail,
                      "source_post_sha256": row["source_post_sha256"], "source_detail_sha256": row["source_detail_sha256"],
                      "selection_context": {k: v for k, v in row.items() if k not in {"source_post_sha256", "source_detail_sha256"}}})
    for source_name, summary in sources.items():
        decisions = Counter(r["decision"] for r in rows if r["source"] == source_name)
        summary.update(eligible_count=decisions["eligible_for_official_review"], review_required_count=decisions["review_required"],
                       excluded_count=decisions["excluded"], returned_count=sum(x.get("source", "alio") == source_name for x in items))
        summary["exclusion_reasons"] = dict(Counter(reason for r in rows if r["source"] == source_name and r["decision"] == "excluded" for reason in r["reasons"]))
    audit = {"schema_version": 1, "policy_id": POLICY_ID, "evaluated_at": now.isoformat(),
             "scan_scope": "complete_saved_alio_and_cleaneye_feeds", "connected_sources": ["alio", "cleaneye"],
             "official_details_fully_reviewed": False, "sources": sources,
             "total_scanned": len(rows), "eligible_before_limit": len(unique), "writer_limit": limit,
             "returned_count": len(items), "unconfirmed_unit_counts": sum(r["unit_count"] is None for r, *_ in unique),
             "interest_ranking": "unavailable_not_used", "audience_breadth_ranking": "unavailable_not_used",
             "ranking_order": ["current_application_open", "exact_employment_type", "verified_unit_count_desc", "actual_deadline", "notice_id_tiebreak"],
             "review_errors": review_errors, "rows": rows}
    review_rows = [{k: v for k, v in r.items() if k not in {"source_post_sha256", "source_detail_sha256"}}
                   for r in rows if r["decision"] == "review_required"]
    return {"candidates": items, "selection_audit": audit, "review_candidates": review_rows,
            "all_blocked_notice_ids": sorted(protected), "cleaneye_status": cleaneye_status}
