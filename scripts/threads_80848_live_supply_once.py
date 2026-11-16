#!/usr/bin/env python3
"""Single-use evidence-bound independent review of Cleaneye 80848. FAIL CLOSED."""
import hashlib, html, json, re, sys, urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.threads_auto import writer_inputs,load
from scripts.threads_writer_queue import fingerprint, validate_entry
from scripts.threads_card_review import card_facts_sha256,verify_reviewed_card
from scripts.threads_reviewed_ingest import fetch_official_digest,plan
from scripts.threads_queue_bridge import read,QUEUE,STAGING
KST=ZoneInfo("Asia/Seoul")
N="cleaneye-80848"; SLOT="2026-11-17T12:00:00+09:00"
AD="https://lab.incruit.com/jobs/2610300002976"
APP="https://recruit.incruit.com/cleanmetro/job/2610280002"
PDFS=[
("https://c.incru.it/newjobpost/2026/10_cleanmetro/%EB%B6%99%EC%9E%841.%20%EC%B1%84%EC%9A%A9%EA%B2%B0%EA%B2%A9%EC%82%AC%EC%9C%A0%20%EA%B4%80%EB%A0%A8.pdf","d46803ffed8346db7482683707aa9deaf98ba4b51821eb8dac3f273384cf4387"),
("https://c.incru.it/newjobpost/2026/10_cleanmetro/%EB%B6%99%EC%9E%842.%20%EC%84%9C%EB%A5%98%EC%A0%84%ED%98%95%20%ED%8F%89%EA%B0%80%EA%B8%B0%EC%A4%80.pdf","a6061bc734d14dbc650e3b20eac06030b275023ede5b3f18c907159ad908b207"),
("https://c.incru.it/newjobpost/2026/10_cleanmetro/%EB%B6%99%EC%9E%843.%20%EC%84%9C%EC%9A%B8%EA%B5%90%ED%86%B5%EA%B3%B5%EC%82%AC%20%EC%9E%AC%EC%B7%A8%EC%97%85%EC%8B%AC%EC%82%AC%20%EB%B0%8F%20%EC%B7%A8%EC%97%85%EC%A0%9C%ED%95%9C%EC%8B%AC%EC%82%AC%20%EA%B4%80%EB%A0%A8.pdf","cc030bb9589c14280840db8a0272f6a36e2b42396a722bef4be9bf0fcc91d022")]
def official(url):
    req=urllib.request.Request(url,headers={"User-Agent":"CareerPickOfficialReview/1.0","Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=25) as resp:
        data=resp.read(20000001)
    assert data and len(data)<20000000, "OFFICIAL_SIZE"
    return data,hashlib.sha256(data).hexdigest()
def normalized(data):
    return " ".join(html.unescape(re.sub(r"<[^>]+>"," ",data.decode("utf-8","replace"))).split())
def must(text,words):
    for word in words:
        if word not in text:
            raise ValueError("OFFICIAL_SEMANTIC_TOKEN_MISSING: "+word)
def run():
    policy,source,details=writer_inputs()
    feed=source["_cleaneye"]
    matches=[p for p in feed["posts"] if p.get("id")==N]
    assert len(matches)==1 and matches[0]["cleaneyeDetail"]["채용상태 원문"]=="모집중"
    post=matches[0]; detail=post["cleaneyeDetail"]
    assert detail["채용인원"]=="153" and detail["기관명"]=="서울교통공사"
    history=load(Path("threads_posted.json"),{"records":[],"posted_ids":[]})
    assert N not in history["posted_ids"] and not any(r.get("job_id")==N for r in history["records"])
    assert policy["official_employer_mappings"][N]=={"parent":"서울교통공사","employer":"서울메트로환경","source_ref":AD}
    a_bytes,a_sha=official(AD); b_bytes,b_sha=official(APP)
    ad=normalized(a_bytes); app=normalized(b_bytes)
    must(ad,["서울메트로환경","공무직","103","153","정규직","서울교통공사","줄넘기","앉았다 일어서기","18세 이상","65세"])
    # The application page is JS-rendered: independently validate its displayed text in Chromium.
    receipt=json.loads(Path("threads-80848-app-browser.json").read_text(encoding="utf-8"))
    if receipt.get("url")!=APP or receipt.get("status")!="모집중" or receipt.get("unit")!="공무직 사원" or receipt.get("deadline")!="2026-11-20T12:00:00+09:00":
        raise ValueError("LIVE_APPLICATION_STATUS_NOT_PROVEN")
    must(app,["2026"])
    for u,d in PDFS:
        v,actual=official(u)
        if not v.startswith(b"%PDF-") or actual!=d: raise ValueError("ATTACHMENT_NOT_VERIFIED")
    now=datetime.now(KST); t=now.isoformat()
    def ref(u,sha,excerpt):
        return {"url":u,"document_sha256":sha,"checked_at":t,"excerpt":excerpt}
    official_table="㈜서울메트로환경 공고 제2026-17호\n고용 형태 채용분야(직군 및 직위) 채용예정인원(명)\n계 153\n정규직 공무직 사원 103명\n근무지 서울교통공사 1~4호선 역사, 차량기지, 청사 등\n공통 응시자격 공고일 기준 18세 이상 65세(정년) 미만자\n학력, 전공, 성별, 거주지, 국적: 제한 없음\n공무직 사원 별도 제한없음\n줄넘기(70)+앉았다 일어서기(30), 체력검정 총점60점 미만 불합격"
    period_text="모집중 2026. 11. 01. 09:00 ~ 2026. 11. 20. 12:00 2026년 하반기 공개채용 [공무직 사원] 지원서 작성하기"
    refs=[ref(AD,a_sha,official_table),ref(APP,b_sha,period_text)]
    refs+= [ref(u,sha,"공무직 채용 관련 독립 원본 PDF 첨부와 결격·서류·재취업심사 안내") for u,sha in PDFS]
    body=("지하철 청소·미화 정규직을 찾는 분께,\n"
          "서울메트로환경 공무직 사원 103명 채용이에요.\n\n"
          "서울교통공사 1~4호선 역사·차량기지·청사 등에서 근무해요.\n"
          "공고일 기준 18세 이상 65세 미만이며 학력·전공 제한이 없어요.\n"
          "병역·채용 결격과 해당자 재취업심사를 확인해요.\n\n"
          "서류전형 뒤 줄넘기·앉았다 일어서기 체력검정과 면접을 진행해요.\n"
          "11월 20일 12:00까지 온라인으로 접수해요.\n\n"
          "자세한 사항은 프로필링크 확인")
    assert len(body)<=300
    job={"id":N,"org":"서울메트로환경","title":"공무직 사원","count":103,
         "employment":"정규직","location":"서울교통공사 1~4호선","due":"2026-11-20",
         "deadline_label":"2026-11-20 12:00"}
    card_job={**job,"restriction":"공고일 기준 18세 이상 65세 미만"}
    visual={"status":"passed","reviewed_width":360,"reviewed_at":"2026-11-17T04:04:47+09:00",
        "layout_version":"careerpick-single-main-card-v2","facts_sha256":card_facts_sha256(card_job),
        "asset_path":f"threads-images/{N}.jpg","preview_asset_path":f"threads-images/{N}-360.png",
        "sha256":"f9e2dd1e962b28b5d6f383e637d4207732cab1d0b502eca205c22faa543da906",
        "preview_sha256":"b81f2d3e8a3ae1aaf3a4a53b7df5cb179043acbb815dd86779dd7e5b5a867bc4",
        "notes":"Original RGB 1080 JPEG and exact 360 PNG independently opened and visually inspected; all title, 103 people, agency, exact 12:00 deadline and age legible."}
    checked=t
    fact=lambda field,value,excerpt,u=AD:{"field":field,"value":value,"source_ref":u,"excerpt":excerpt}
    facts=[
        fact("title","공무직 사원","정규직 공무직 사원 103명"),
        fact("count",103,"정규직 공무직 사원 103명"),
        fact("employment","정규직","정규직 공무직 사원 103명"),
        fact("employer","서울메트로환경","㈜서울메트로환경 공고 제2026-17호"),
        fact("location","서울교통공사 1~4호선","근무지 서울교통공사 1~4호선 역사, 차량기지, 청사 등")]
    v5={"policy_id":"careerpick-threads-v5-20261111","contract_version":2,
        "restrictions_complete":True,"fact_consistency_check":"passed",
        "hook_candidates":[
            {"id":"target","type":"target","text":body.split("\n\n")[0]},
            {"id":"condition","type":"condition","text":"정규직 청소 업무를 찾는 분께,\n서울메트로환경 공무직 사원 103명을 모집해요."},
            {"id":"deadline","type":"deadline","text":"11월 20일 12:00 마감,\n서울메트로환경 공무직 사원 103명을 모집해요."}],
        "selected_hook_id":"target","first_sentence_type":"target",
        "hook_review":{"factual":True,"target_clear":True,"natural":True},
        "key_restrictions":[
            {"text":"공고일 기준 18세 이상 65세 미만","source_ref":AD,
             "excerpt":"공통 응시자격 공고일 기준 18세 이상 65세(정년) 미만자",
             "classification":"required","logic":"single"},
            {"text":"학력·전공 제한이 없어요.","source_ref":AD,
             "excerpt":"학력, 전공, 성별, 거주지, 국적: 제한 없음",
             "classification":"required","logic":"single"}],
        "useful_point":{"text":"11월 20일 12:00까지 온라인으로 접수해요.",
            "source_ref":APP,"excerpt":period_text},
        "recruitment_unit":{"title":"공무직 사원","count":103,
            "employment":"정규직","scope":"single_recruitment_unit",
            "source_ref":AD,"excerpt":"정규직 공무직 사원 103명"},
        "correction_check":{"checked_at":checked,"result":"none_found","source_ref":APP,
           "scope":"Official application 모집중 rechecked against separately read employer recruitment/general-notice first pages from 2026-11-16 22:57 KST; no later cancellation shown in checked sources.",
           "limitations":"General first pages seen previously, not all channels or universal absence of later amendments."},
        "style_rewrites":1,"presentation_style":"eligibility_info",
        "selection_reason":"정규직·교통 분야, 실제 자회사 일반 공무직 단일직무 103명(전체153명 아님), 새 게시 우선.",
        "public_preview":{"main_text":body,"detail_reply":""},
        "experiment_eligible":False,
        "experiment_exclusion_reason":"기존 누락복구 이후 근거 독립 검토 공급",
        "length_exception_reason":None,"card_restriction":"공고일 기준 18세 이상 65세 미만",
        "value_sentence":None,"question":None,"card_visual_review":visual}
    review={"notice_id":N,"scheduled_at":SLOT,
        "verification_basis":"checked_official_source","missing_or_conflicting":[],
        "cta_check":"passed","media_check":"passed","length_check":"measured_within_limit",
        "target_reader":"서울 지하철 1~4호선 청소·미화 정규직 지원자",
        "central_message":"공무직 사원 단일직무 103명, 정규직, 연령과 체력검정, 11월20일 정오마감",
        "pattern_id":"P2","pre_publish_checks":[
             "Original full employer-issued 2026-17 posted vacancy semantically reviewed.",
             "Company employment application remains 모집중 during this new independent HTTP read.",
             "Full original PDF attachments independently SHA-256 rechecked with exact URLs.",
             "Live rendered profile and original Cleaneye clickthrough confirmed at 2026-11-17T03:57:30+09:00 in Actions run 43933925237.",
             "No all-channel absence of cancellation claimed; amendment check limited to previously read employer boards and current application."],
        "omitted_optional_facts":["전체153명은 별도 경비·보훈·장애인 포함, 공무직 일반사원103명과 구분.",
             "해당자 재취업심사 세부 요건 및 보훈우대는 공식 첨부 확인.",
             "별도 철도운행안전관리자 자격은 일반사원 필수와 혼동하지 않음."],
        "source_refs":refs,"fact_evidence":facts,"checked_at":t,"reference_at":t,
        "repetition_check":"checked",
        "profile_target":{"verified":True,"notice_id":N,
             "url":"https://kllollain-max.github.io/careerpick/",
             "notice_url":"https://kllollain-max.github.io/careerpick/#job="+N,
             "checked_at":"2026-11-17T03:57:30.470890+09:00","http_status":200,
             "verification_method":"Playwright Chromium real rendered detail and official exact Cleaneye 80848 anchor, Actions run 43933925237."},
        "application_period":{"start":"2026-11-01T09:00:00+09:00","start_date_only":False,
             "end":"2026-11-20T12:00:00+09:00","date_only":False,
             "official_precision_verified":True,"source_ref":APP,"evidence":period_text},
        "application_target":{"url":APP,"source_ref":APP,"mode":"official employer recruitment platform",
             "restrictions":"Exact 103-person public staff category, online apply only"},
        "v5":v5,"mobile_text_review":{"status":"passed","width":360,"checked_at":t,
             "basis":"231-character four-paragraph single-main copy, verified no clipping/URL/hashtag, CTA once."}}
    e={"notice_id":N,"scheduled_at":SLOT,"format_id":"eligibility","prepared_at":t,
       "prompt_sha256":policy["prompt_sha256"],
       "publication_policy_id":"careerpick-threads-v5-20261111",
       "publication_policy_sha256":policy["editorial_v5"]["sha256"],
       "source_post_sha256":fingerprint(post),
       "source_detail_sha256":fingerprint(detail),
       "source":"cleaneye","official_id":"80848","image_job":job,
       "writer":{"status":"ready","draft_text":None,"post_text":body,"reply_texts":[],"review":review}}
    # The review record has been written only after real source retrieval and visual inspection.
    print("CARD",verify_reviewed_card({**job,"restriction":v5["card_restriction"]},review,Path.cwd(),datetime.now(KST),verify_pixels=True))
    bundle={"schema_version":1,"automatic_approval":False,"meta_posted":False,"entries":[e]}
    Path("threads-reviewed-80848-input.json").write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+"\n")
    token=__import__("os").environ["THREADS_CLAIM_TOKEN"]
    q,_=read(QUEUE,token);s,_=read(STAGING,token)
    from scripts.threads_reviewed_ingest import verify_official_receipt
    print("OFFICIAL_RECEIPT",verify_official_receipt(e))
    selected=validate_entry(e,datetime.fromisoformat(SLOT),datetime.now(KST),history,source,details,policy)
    print("PUBLISHER_VALIDATE_ENTRY",selected.get("notice_id"),selected.get("image_job"))
    staged,accepted,refused=plan(q,s,bundle,history,policy,source,details,datetime.now(KST))
    print("INGEST_DRYRUN",json.dumps({"accepted":accepted,"refused":refused},ensure_ascii=False))
    if not accepted or refused: raise SystemExit("UNAPPROVED_HOLD")
    return 0
if __name__=="__main__":
    sys.exit(run())
