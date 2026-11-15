"""Turn a reviewed evidence record into a HOLD/PASS decision without guessing."""
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
REQUIRED = ("institution_document_checked", "correction_checked", "application_window_checked",
            "unit_headcount_checked", "eligibility_checked", "existing_post_checked",
            "profile_checked", "official_source_sha256")

def decision(evidence, now):
    if not isinstance(evidence, dict) or now.tzinfo is None:
        raise ValueError("invalid evidence or clock")
    result = {"notice_id": evidence.get("notice_id"), "decision": "HOLD",
              "official_verified": False, "reason": None}
    if evidence.get("decision") == "REJECT":
        result.update(decision="REJECT", reason="SOURCE_REJECTED")
        return result
    if evidence.get("cancelled") is True:
        result.update(decision="REJECT", reason="OFFICIAL_CANCELLATION")
        return result
    for field in REQUIRED:
        value = evidence.get(field)
        if (field == "official_source_sha256" and
                (not isinstance(value, str) or len(value) != 64 or
                 any(ch not in "0123456789abcdef" for ch in value))):
            result["reason"] = "MISSING_" + field.upper()
            return result
        if field != "official_source_sha256" and value is not True:
            result["reason"] = "MISSING_" + field.upper()
            return result
    try:
        deadline = datetime.fromisoformat(evidence["application_deadline_at"])
        checked = datetime.fromisoformat(evidence["official_checked_at"])
        if deadline.tzinfo is None or checked.tzinfo is None:
            raise ValueError("timezone missing")
    except (ValueError, TypeError, KeyError):
        result["reason"] = "OFFICIAL_DATES_INVALID"
        return result
    if deadline.astimezone(KST) <= now.astimezone(KST):
        result.update(decision="REJECT", reason="APPLICATION_CLOSED")
        return result
    if checked > now or (now - checked).total_seconds() > 86400:
        result["reason"] = "OFFICIAL_REVIEW_STALE"
        return result
    if evidence.get("already_posted") is not False:
        result["reason"] = "POST_HISTORY_UNCERTAIN"
        return result
    result.update(decision="PASS", official_verified=True, reason="OFFICIAL_EVIDENCE_COMPLETE")
    return result
