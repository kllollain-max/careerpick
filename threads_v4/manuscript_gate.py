"""Strict public-copy checks for a newly reviewed Threads manuscript."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

CTA = "자세한 사항은 프로필링크 확인"
URL = re.compile(r"https?\s*[:：]|www\s*[.．]|(?:[a-z0-9-]+\.)+(?:com|net|org|kr|io|co|gov|edu)(?:\b|/)", re.I)
TAG = re.compile(r"(?<!\w)#[\w가-힣]+")
SLOTS = (8, 12, 16, 20)

class ReviewBlocked(ValueError):
    pass

def validate_copy(manuscript, now):
    if not isinstance(manuscript, dict):
        raise ReviewBlocked("MANUSCRIPT_SCHEMA")
    text = manuscript.get("post_text")
    if not isinstance(text, str) or not text.strip() or len(text) > 350:
        raise ReviewBlocked("TEXT_LENGTH")
    if URL.search(text) or TAG.search(text):
        raise ReviewBlocked("URL_OR_TAG")
    if text.splitlines()[-1].strip() != CTA or text.count(CTA) != 1:
        raise ReviewBlocked("CTA_MISMATCH")
    if manuscript.get("reply_texts") != []:
        raise ReviewBlocked("REPLIES_FORBIDDEN")
    if manuscript.get("official_verified") is not True:
        raise ReviewBlocked("OFFICIAL_REVIEW_REQUIRED")
    if manuscript.get("correction_checked") is not True:
        raise ReviewBlocked("CORRECTION_REVIEW_REQUIRED")
    if manuscript.get("profile_verified") is not True:
        raise ReviewBlocked("PROFILE_REVIEW_REQUIRED")
    if not all(manuscript.get(k) for k in ("notice_id", "organization", "headcount", "employment", "eligibility", "official_url", "source_sha256")):
        raise ReviewBlocked("REQUIRED_FACT_MISSING")
    if not re.fullmatch(r"[a-f0-9]{64}", str(manuscript["source_sha256"])):
        raise ReviewBlocked("SOURCE_HASH_INVALID")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ReviewBlocked("CLOCK_INVALID")
    try:
        slot = datetime.fromisoformat(manuscript["scheduled_at"]).astimezone(ZoneInfo("Asia/Seoul"))
        deadline = datetime.fromisoformat(manuscript["deadline_at"]).astimezone(ZoneInfo("Asia/Seoul"))
        checked = datetime.fromisoformat(manuscript["checked_at"]).astimezone(ZoneInfo("Asia/Seoul"))
    except (KeyError, ValueError, TypeError):
        raise ReviewBlocked("TIME_INVALID")
    if slot.hour not in SLOTS or slot.minute or slot.second or slot <= now.astimezone(ZoneInfo("Asia/Seoul")):
        raise ReviewBlocked("SLOT_INVALID")
    if deadline <= slot or checked > now or (now - checked).total_seconds() > 86400:
        raise ReviewBlocked("SOURCE_STALE_OR_CLOSED")
    if manuscript.get("media") not in ("IMAGE", "TEXT"):
        raise ReviewBlocked("MEDIA_INVALID")
    if manuscript["media"] == "IMAGE" and manuscript.get("card_review_passed") is not True:
        raise ReviewBlocked("CARD_REVIEW_REQUIRED")
    return True
