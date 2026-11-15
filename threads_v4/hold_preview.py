"""Generate a factual, clearly unapproved preview for human review.

Never place previews in reviewed staging or the publisher queue.
"""
import json
from pathlib import Path

CTA="자세한 사항은 프로필링크 확인"

def preview(audit):
    facts=audit["official_page_content_review"]
    cross=audit.get("cross_source_text_evidence",{})
    if not cross.get("institution_page_body_confirmed") or cross.get("approval")!="HOLD":
        raise ValueError("CROSS_SOURCE_REVIEW_REQUIRED")
    required=("organization","title","employment","headcount","qualification","application_window_as_published")
    if any(not facts.get(k) for k in required):
        raise ValueError("MISSING_SOURCE_FACTS")
    text=(f'{facts["organization"]}에서 {facts["title"]} 채용을 진행합니다.\n'
          f'고용형태: {facts["employment"]} · 모집인원: {facts["headcount"]}명\n'
          f'지원자격: {facts["qualification"]}\n'
          f'접수기간: {facts["application_window_as_published"]} (UTC 기준)\n'
          f'{CTA}')
    if len(text)>350 or text.count(CTA)!=1:
        raise ValueError("COPY_POLICY_FAILURE")
    return {"schema_version":1,"notice_id":audit["notice_id"],"status":"HOLD_PREVIEW_ONLY",
            "post_text":text,"source_urls":[audit["source"],audit["institution_notice"]],
            "unresolved":["CORRECTION_AND_CANCELLATION_CHECK","OFFICIAL_ATTACHMENT_REVIEW",
                          "EXACT_DEADLINE_CLOCK","POSTED_LEDGER_AND_PROFILE_RECONCILIATION",
                          "IMAGE_CARD_REVIEW"],"approved":False,"queue_eligible":False,
            "meta_posted":False}

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--audit",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    data=json.loads(Path(a.audit).read_text(encoding="utf-8"))
    result=preview(data)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"notice_id":result["notice_id"],"status":result["status"],
                      "chars":len(result["post_text"]),"queue_eligible":False},ensure_ascii=False))
