"""Cross-source evidence matching. Text matches are never equivalent to approval."""
import re

def compare(checks):
    if len(checks)!=2 or any(c.get("status")!="FETCHED_NOT_VERIFIED" for c in checks):
        return {"decision":"HOLD","reason":"OFFICIAL_SOURCE_FETCH_INCOMPLETE","matched":{}}
    texts=[c.get("text_evidence",{}).get("evidence",{}) for c in checks]
    fields={"organization":"한국조세재정연구원","position":"연구위원","headcount":"10명","employment":"정규직"}
    matches={}
    for field,term in fields.items():
        matches[field]={"alio":bool(texts[0].get(term,{}).get("found")),
                        "institution":bool(texts[1].get(term,{}).get("found"))}
    # Employment classification appears in ALIO; institutional body can omit the exact word.
    required=("organization","position","headcount")
    if not all(matches[f]["alio"] and matches[f]["institution"] for f in required):
        reason="CROSS_SOURCE_FACT_MISMATCH"
    elif not matches["employment"]["alio"]:
        reason="EMPLOYMENT_CLASSIFICATION_UNVERIFIED"
    else:
        reason="CORRECTIONS_ATTACHMENTS_AND_DEADLINE_CLOCK_UNVERIFIED"
    return {"decision":"HOLD","reason":reason,"matched":matches,
            "official_approved":False,"meta_posted":False}
