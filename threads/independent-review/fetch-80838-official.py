#!/usr/bin/env python3
"""Read-only independent official PDF fetch for cleaneye-80838; does not approve or publish."""
import datetime, hashlib, json, pathlib, re, subprocess, sys, time, urllib.request
OUT=pathlib.Path("threads/independent-review/evidence-80838"); OUT.mkdir(parents=True,exist_ok=True)
URL="https://www.yumcorp.or.kr/ybscript.io/common/file_download/6066/6975/%EB%B6%99%EC%9E%84_%EA%B3%B5%EA%B3%A0%EB%AC%B8.pdf?pkey=BxV8TSjh7"
LANDING="https://www.yumcorp.or.kr/www/notify/job?idx=6066&mode=view"
raw=None; diagnostics=[]
for n in range(3):
    try:
        req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0 (compatible; CareerPick-official-review/1.0)","Referer":LANDING,"Accept":"application/pdf,*/*"})
        with urllib.request.urlopen(req,timeout=25) as r: raw=r.read(15000000)
        if not raw.startswith(b"%PDF-"):raise RuntimeError(f"BAD_PDF_MAGIC:{raw[:30]!r}")
        break
    except Exception as exc:
        diagnostics.append(f"attempt {n+1}: {type(exc).__name__}: {exc}")
        if n<2:time.sleep((2,4)[n])
if raw is None or not raw.startswith(b"%PDF-"):
    print("OFFICIAL_DOWNLOAD_FAILED "+json.dumps(diagnostics,ensure_ascii=False))
    sys.exit(2)
pdf=OUT/"official-80838.pdf";pdf.write_bytes(raw)
txt=OUT/"official-80838.txt"
subprocess.run(["pdftotext","-layout",str(pdf),str(txt)],check=True)
plain=txt.read_text(encoding="utf-8",errors="replace")
if len(plain)<1200:raise RuntimeError(f"PDF_TEXT_TOO_SHORT:{len(plain)}")
page_info=subprocess.run(["pdfinfo",str(pdf)],check=True,text=True,capture_output=True).stdout
page_count=int(re.search(r"Pages:\s*(\d+)",page_info).group(1))
observed=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
evidence={"status":"official_source_downloaded_unapproved","notice_id":"cleaneye-80838","org":"여수시도시관리공단","official_detail_url":LANDING,"official_pdf_url":URL,"retrieved_at_actual":observed,"pdf_byte_size":len(raw),"pdf_sha256":hashlib.sha256(raw).hexdigest(),"extracted_text_sha256":hashlib.sha256(plain.encode()).hexdigest(),"extracted_pages":page_count,"approval":False,"post":False,"validation":"independent_semantic_review_pending","download_diagnostics":diagnostics}
(OUT/"official-80838-evidence.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
print("EVIDENCE "+json.dumps(evidence,ensure_ascii=False))
lines=plain.splitlines()
# Show short source excerpts with original adjacency, not automatic human approval.
match=re.compile("일반직|기능직|미화|접수|응시자격|필수|우대|마감|정정|취소|전형|거주|자격증|2026",re.I)
indices=[i for i,line in enumerate(lines) if match.search(line)]
shown=set()
for i in indices[:60]:
    for j in range(max(0,i-1),min(len(lines),i+2)):shown.add(j)
excerpt="\n".join(f"{i+1}: {lines[i]}" for i in sorted(shown))
print("SOURCE_TEXT_EXCERPTS_BEGIN\n"+excerpt[:24000]+"\nSOURCE_TEXT_EXCERPTS_END")
