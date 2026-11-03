"""Conservative offline notice triage; API dates never establish official status."""
import re
import unicodedata
from datetime import date

# Matching uses NFKC text without whitespace/format characters. These classify
# notice content, not the legal effect or current application status of a notice.
ANNOUNCEMENT = re.compile(r"최종합격|서류(?:전형)?합격|(?:필기|면접)(?:시험|전형)?합격|합격자(?:발표|공고|명단)|합격발표|(?:채용|전형|시험)결과(?:발표|공고)")
REGISTRATION = re.compile(r"(?:임용|채용)후보자(?:임용)?등록|(?:최종)?합격자(?:임용)?등록")
EXAM = re.compile(r"시험(?:장소|일정|시간|안내)|면접(?:일정|장소|안내)|응시자안내")
RECRUIT = re.compile(r"채용(?:시험)?(?:재?공고|계획|모집)|모집(?:공고|안내)|공개경쟁채용|경력경쟁채용")
CANCELLATION = re.compile(r"취소|철회")
NOTICE_CANCELLATION = re.compile(r"(?:채용(?:시험)?|모집|공고|임용(?:시험)?|선발)(?:공고|계획)?(?:을|를|이|가|은|는)?(?:취소|철회)|(?:취소|철회)(?:공고|안내|알림)")
REOPEN = re.compile(r"(?:추가|신규|재)(?:채용|모집)|재공고|(?:원서)?접수(?:기간)?(?:연장|재개|추가)|모집(?:기간)?(?:연장|재개)")
RESULT_EVENT = re.compile(r"합격자?(?:발표|공고|명단)|(?:채용|전형|시험)결과(?:발표|공고)|최종합격자(?:를|는)?(?:다음과같이)?(?:발표|공고)")
CLOSED = re.compile(r"(?:원서)?(?:접수|모집)(?:이|가|은|는|을|를)?(?:마감|종료)")


def _text(value):
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(character for character in normalized
                   if not character.isspace() and unicodedata.category(character) != "Cf")


def _decision(category, reason, recruiting=False):
    return {"category": category, "recruiting": recruiting, "reason": reason}


def _hold(reason):
    return _decision("상태 미확인", reason)


def _date(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("invalid_date")
    return date.fromisoformat(value)


def _scheduled_mention(text, match):
    """Distinguish schedule labels/conditions from a result or closure statement."""
    after = text[match.end():]
    if re.match(r"^(?:일정|일시|일자|예정|계획|후|전|까지|부터|일(?=$|[:(0-9은는이]))", after):
        return True
    if re.match(r"^(?:[(:]|은|는)?(?:예정|[0-9]{4}[-./년]|[0-9]{1,2}[./월])", after):
        return True
    before = text[max(0, match.start() - 40):match.start()]
    return bool(re.search(r"(?:마감|종료|전형|시험)후(?:에|에는)?$", before))


def _official_closure(text):
    if re.fullmatch(r"(?:원서)?(?:접수|모집)(?:이|가|은|는|을|를)?(?:마감|종료)(?:안내|공고)?[.!]?", text):
        return True
    return any(not _scheduled_mention(text, match)
               and re.match(r"^(?:되었|됐|하였|했|완료|상태|(?:을|를)(?:공고|알려))", text[match.end():])
               for match in CLOSED.finditer(text))


def _official_cancellation(text):
    return bool(re.search(r"(?:채용(?:시험)?|모집|채용공고|모집공고)(?:을|를|이|가|은|는)?(?:취소|철회)(?:되었습니다|되었|됐|하였습니다|하였|했습니다|했|합니다|함)", text)
                or re.fullmatch(r"(?:채용|모집)?공고(?:취소|철회)(?:안내|공고)?[.!]?", text))


def _mixed_title(text, signals):
    if any(fresh.start() >= signal.end() for fresh in REOPEN.finditer(text) for signal in signals):
        return True
    # A recruitment phrase in the exam's name is context, not a second notice.
    clauses = re.split(r"및|그리고|;|/", text)
    return bool(signals and len(clauses) > 1 and any(
        (RECRUIT.search(clause) or REOPEN.search(clause))
        and not any(pattern.search(clause) for pattern in
                    (ANNOUNCEMENT, REGISTRATION, EXAM, CANCELLATION))
        for clause in clauses))


def classify_notice(title, *, official_text=None, official_verified=False,
                    application_open_verified=False, application_closed_verified=False,
                    as_of=None, deadline=None):
    """Return the existing three-key triage contract with fixed reason codes.

    Verification flags must be bools. They describe independently inspected
    official evidence; a title, API date, or valid-looking URL cannot set them.
    An elapsed API deadline is only an observation and cannot overrule explicitly
    verified current official status (for example, an inspected extension).
    """
    if not isinstance(title, str) or len(title) > 2000:
        return _hold("invalid_title")
    title = _text(title)
    if not title:
        return _hold("missing_title")
    flags = (official_verified, application_open_verified, application_closed_verified)
    if any(type(flag) is not bool for flag in flags):
        return _hold("invalid_verification_flags")
    try:
        check_date, api_deadline = _date(as_of), _date(deadline)
    except (TypeError, ValueError):
        return _hold("invalid_date")
    if application_open_verified and application_closed_verified:
        return _hold("conflicting_application_status")
    if official_verified and (not isinstance(official_text, str) or not _text(official_text)):
        return _hold("missing_official_text")
    body = _text(official_text) if official_verified else ""

    cancellation = NOTICE_CANCELLATION.search(title)
    announcement = ANNOUNCEMENT.search(title)
    registration = REGISTRATION.search(title)
    exam = EXAM.search(title)
    signals = [match for match in (cancellation, announcement, registration, exam) if match]
    if CANCELLATION.search(title) and not cancellation:
        return _hold("ambiguous_cancellation_title")
    if cancellation and re.match(r"^(?:(?:이|가|는)?(?:아니|아님)|되지않|하지않|없|안함|예정|방지|여부|검토)", title[cancellation.end():]):
        return _hold("ambiguous_cancellation_title")
    if _mixed_title(title, signals):
        return _hold("mixed_notice_signals")
    if cancellation:
        return _decision("취소 공고", "cancellation_title")
    if registration and not RESULT_EVENT.search(title):
        return _decision("등록 안내", "candidate_registration_title")
    if announcement:
        return _decision("합격자 발표", "announcement_title")
    if registration:
        return _decision("등록 안내", "candidate_registration_title")
    if exam:
        return _decision("시험 안내", "exam_notice_title")

    if official_verified:
        if any(not _scheduled_mention(body, match) for match in RESULT_EVENT.finditer(body)):
            return _hold("conflicting_official_announcement")
        if _official_cancellation(body):
            return _hold("conflicting_official_cancellation")
        if application_closed_verified or _official_closure(body):
            if application_open_verified:
                return _hold("conflicting_official_closure")
            return _decision("접수 종료", "official_closure")
    if not RECRUIT.search(title):
        return _hold("not_established_recruitment")
    if official_verified and application_open_verified:
        return _decision("모집공고", "official_open_verified", recruiting=True)
    if api_deadline is not None and check_date is not None and api_deadline < check_date:
        return _hold("deadline_elapsed_unverified")
    if not official_verified:
        return _hold("official_source_unverified")
    return _hold("application_status_unverified")
