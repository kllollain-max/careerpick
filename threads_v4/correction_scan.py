"""Classify correction/cancellation language without confusing eligibility exclusions with notice cancellation."""
import re

CANCEL_NOTICE=re.compile(r"(?:본\s*채용|채용\s*공고|모집\s*공고|본\s*공고).{0,30}(?:취소|철회|폐지)|(?:취소|철회).{0,30}(?:본\s*채용|채용\s*공고|모집\s*공고)",re.I)
CORRECTION_NOTICE=re.compile(r"(?:채용\s*공고|모집\s*공고|본\s*공고).{0,30}(?:정정|수정)|(?:정정|수정)\s*공고",re.I)

def scan(text):
    if not isinstance(text,str):
        raise ValueError("SOURCE_TEXT_REQUIRED")
    cancellations=[m.group(0) for m in CANCEL_NOTICE.finditer(text)]
    corrections=[m.group(0) for m in CORRECTION_NOTICE.finditer(text)]
    if cancellations:
        status="CANCELLATION_SUSPECTED"
    elif corrections:
        status="CORRECTION_REVIEW_REQUIRED"
    else:
        status="NO_MATCH_NOT_PROOF_OF_ABSENCE"
    return {"status":status,"cancellation_matches":cancellations[:10],
            "correction_matches":corrections[:10],"official_approved":False}
