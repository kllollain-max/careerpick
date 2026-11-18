"""Fail-closed triage of official review candidates; no auto-approval."""
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

def triage(candidate, now):
    nid = candidate.get("notice_id")
    url = candidate.get("official_url")
    result = {"notice_id": nid, "decision": "HOLD", "official_verified": False,
              "reason": None, "official_url": url}
    if not nid:
        result["reason"] = "NOTICE_ID_MISSING"
        return result
    if not isinstance(url, str):
        result["reason"] = "OFFICIAL_URL_MISSING"
        return result
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid official URL")
    except ValueError:
        result["reason"] = "OFFICIAL_URL_INVALID"
        return result
    period = candidate.get("application_period")
    if not isinstance(period, dict) or not period.get("end"):
        result["reason"] = "APPLICATION_END_UNVERIFIED"
        return result
    try:
        end = datetime.fromisoformat(period["end"])
        if end.tzinfo is None:
            raise ValueError("naive")
    except (TypeError, ValueError):
        result["reason"] = "APPLICATION_END_INVALID"
        return result
    if end.astimezone(KST) <= now.astimezone(KST):
        result["decision"] = "REJECT"
        result["reason"] = "APPLICATION_CLOSED"
        return result
    result["reason"] = "OFFICIAL_DOCUMENT_REVIEW_REQUIRED"
    return result

def triage_report(report, now):
    if now.tzinfo is None:
        raise ValueError("timezone required")
    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("invalid candidates")
    records = [triage(row, now) for row in candidates]
    return {"schema_version": 1, "results": records,
            "hold_count": sum(r["decision"] == "HOLD" for r in records),
            "reject_count": sum(r["decision"] == "REJECT" for r in records),
            "pass_count": 0, "official_verified_count": 0}
