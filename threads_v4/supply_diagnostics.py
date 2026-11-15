"""Safe supply diagnostics; never manufacture approval or mutate production."""
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from threads_v4.queue_health import inspect

KST=ZoneInfo("Asia/Seoul")

def supply_decision(queue, staging, history, triage, now):
    health=inspect(queue,staging,history,now)
    decisions=triage.get("results",[])
    reasons=Counter(row.get("reason","UNKNOWN") for row in decisions if row.get("decision")=="HOLD")
    if not health["missing_slots"]:
        status="READY"
        action="NO_ACTION"
    elif staging.get("entries"):
        status="QUEUE_SLOT_MISSING"
        action="REVIEW_STAGING_AND_RUN_EXISTING_CAS_BRIDGE"
    elif any(row.get("decision")=="PASS" for row in decisions):
        status="STAGING_EMPTY"
        action="BUILD_DRAFTS_FROM_VERIFIED_PASS_ONLY"
    else:
        status="STAGING_EMPTY"
        action="REVERIFY_OFFICIAL_DOCUMENTS"
    return {"status":status,"action":action,"missing_slots":health["missing_slots"],
            "review_hold_reasons":dict(reasons),"queue_ready":health["ready_count"],
            "staging_count":health["staged_count"],"meta_posted":False}
