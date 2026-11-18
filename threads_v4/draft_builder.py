"""Deterministic Korean Threads draft from a fully verified official evidence record.

No approval, queue mutation, or Meta publishing occurs here.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from threads_v4.evidence_gate import decision
from threads_v4.manuscript_gate import validate_copy, CTA

KST = ZoneInfo("Asia/Seoul")

def make_draft(evidence, scheduled_at, media, now):
    gate = decision(evidence, now)
    if gate["decision"] != "PASS":
        raise ValueError("OFFICIAL_EVIDENCE_NOT_APPROVED: " + str(gate["reason"]))
    required = ("organization", "position", "employment", "headcount",
                "eligibility", "official_url", "official_source_sha256",
                "application_deadline_at", "official_checked_at")
    if any(not evidence.get(k) for k in required):
        raise ValueError("REQUIRED_COPY_FACT_MISSING")
    if not isinstance(evidence["headcount"], int) or evidence["headcount"] < 1:
        raise ValueError("HEADCOUNT_INVALID")
    deadline = datetime.fromisoformat(evidence["application_deadline_at"]).astimezone(KST)
    deadline_text = deadline.strftime("%m월 %d일 %H:%M")
    text = (
        f'{evidence["organization"]}에서 {evidence["position"]} 채용을 진행합니다.\n'
        f'고용형태: {evidence["employment"]} · 모집: {evidence["headcount"]}명\n'
        f'지원자격: {evidence["eligibility"]}\n'
        f'접수마감: {deadline_text} (한국시간)\n'
        f'{CTA}'
    )
    draft = {
        "notice_id": evidence["notice_id"],
        "organization": evidence["organization"],
        "employment": evidence["employment"],
        "headcount": evidence["headcount"],
        "eligibility": evidence["eligibility"],
        "official_url": evidence["official_url"],
        "source_sha256": evidence["official_source_sha256"],
        "scheduled_at": scheduled_at,
        "deadline_at": evidence["application_deadline_at"],
        "checked_at": evidence["official_checked_at"],
        "official_verified": True,
        "correction_checked": True,
        "profile_verified": True,
        "reply_texts": [],
        "post_text": text,
        "media": media,
        "card_review_passed": evidence.get("card_review_passed", False),
        "approval_status": "DRAFT_REQUIRES_QUEUE_REVIEW",
    }
    validate_copy(draft, now)
    return draft
