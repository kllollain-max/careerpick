"""Conservative, offline GOJOBS notice triage. Never asserts live application status from API deadlines."""
import re
from datetime import date

ANNOUNCEMENT = re.compile(r"최종\s*합격|서류\s*(?:전형\s*)?합격|합격자\s*(?:발표|공고)|임용\s*후보자|등록\s*안내|합격\s*발표")
EXAM = re.compile(r"시험\s*(?:장소|일정|시간|안내)|필기\s*시험\s*(?:장소|안내)|면접\s*(?:일정|장소|안내)|응시자\s*안내")
RECRUIT = re.compile(r"채용\s*(?:공고|계획|모집)|모집\s*(?:공고|안내)|공개\s*경쟁\s*채용|경력\s*경쟁\s*채용")
CLOSED = re.compile(r"접수\s*(?:마감|종료)|모집\s*(?:마감|종료)")

def classify_notice(title, *, official_text=None, official_verified=False,
                    application_open_verified=False, application_closed_verified=False,
                    as_of=None, deadline=None):
    """Return non-operational classification and auditable fixed reason codes.

    official_verified means the linked official document was actually inspected,
    not merely that the API returned a title or a syntactically valid URL.
    """
    if not isinstance(title, str) or len(title) > 2000:
        return {"category": "상태 미확인", "recruiting": False, "reason": "invalid_title"}
    title = " ".join(title.split())
    if not title:
        return {"category": "상태 미확인", "recruiting": False, "reason": "missing_title"}
    if official_verified and (not isinstance(official_text, str) or not official_text.strip()):
        return {"category": "상태 미확인", "recruiting": False, "reason": "missing_official_text"}
    text = title + (" " + official_text if official_verified else "")
    if ANNOUNCEMENT.search(title):
        return {"category": "합격자 발표", "recruiting": False, "reason": "announcement_title"}
    if EXAM.search(title):
        return {"category": "시험 안내", "recruiting": False, "reason": "exam_notice_title"}
    if official_verified and ANNOUNCEMENT.search(official_text):
        return {"category": "상태 미확인", "recruiting": False, "reason": "conflicting_official_announcement"}
    if application_closed_verified or (official_verified and CLOSED.search(official_text)):
        return {"category": "접수 종료", "recruiting": False, "reason": "official_closure"}
    if deadline and as_of:
        try:
            if date.fromisoformat(deadline) < date.fromisoformat(as_of):
                return {"category": "접수 종료", "recruiting": False, "reason": "deadline_elapsed"}
        except (TypeError, ValueError):
            return {"category": "상태 미확인", "recruiting": False, "reason": "invalid_date"}
    if not RECRUIT.search(title):
        return {"category": "상태 미확인", "recruiting": False, "reason": "not_established_recruitment"}
    if not official_verified:
        return {"category": "상태 미확인", "recruiting": False, "reason": "official_source_unverified"}
    if not application_open_verified or application_closed_verified:
        return {"category": "상태 미확인", "recruiting": False, "reason": "application_status_unverified"}
    return {"category": "모집공고", "recruiting": True, "reason": "official_open_verified"}
