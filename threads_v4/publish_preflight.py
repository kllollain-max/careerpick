"""Read-only publication preflight. Never makes a Meta POST."""
import json
from pathlib import Path

def preflight(audit, queue, staging, *, account):
    blockers=[]
    if account!="hid_119":
        blockers.append("ACCOUNT_MISMATCH")
    if audit.get("decision")!="PASS" or not audit.get("official_verified"):
        blockers.append("OFFICIAL_REVIEW_NOT_PASS")
    if audit.get("cross_source_text_evidence",{}).get("approval")!="PASS":
        blockers.append("CROSS_SOURCE_REVIEW_NOT_PASS")
    if not isinstance(queue.get("entries"),list) or not isinstance(staging.get("entries"),list):
        blockers.append("QUEUE_SCHEMA_INVALID")
    if not any(x.get("notice_id")==audit.get("notice_id") and isinstance(x.get("writer"),dict) and x["writer"].get("status")=="ready" and isinstance(x.get("writer_review"),dict) and x["writer_review"].get("status")=="approved" for x in staging.get("entries",[]) if isinstance(x,dict)):
        blockers.append("APPROVED_STAGING_ENTRY_MISSING")
    return {"status":"BLOCKED" if blockers else "REQUIRES_META_ACCOUNT_CHECK",
            "blockers":blockers,"meta_posted":False,"notice_id":audit.get("notice_id")}

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    for arg in ("audit","queue","staging","output"):p.add_argument("--"+arg,required=True)
    a=p.parse_args()
    docs=[json.loads(Path(x).read_text(encoding="utf-8")) for x in (a.audit,a.queue,a.staging)]
    result=preflight(*docs,account="hid_119")
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
