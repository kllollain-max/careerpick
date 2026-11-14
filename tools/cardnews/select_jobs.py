"""Fail-closed selection of active jobs from a preserved API JSON snapshot.
No external calls, publishing or modification of existing collection workflows.
"""
import argparse,datetime,json,re,sys
from urllib.parse import urlparse
from pathlib import Path
from zoneinfo import ZoneInfo
KST=ZoneInfo("Asia/Seoul")
REGULAR={"정규직"}
def parse_deadline(value):
    if not isinstance(value,str):return None
    value=value.strip()
    # Date-only closing is uncertain without an official time.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?",value):return None
    try:return datetime.datetime.fromisoformat(value.replace(" ","T")).replace(tzinfo=KST)
    except ValueError:return None
def choose(rows,now=None,limit=5):
    now=now or datetime.datetime.now(KST)
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=20:raise ValueError('limit must be 1..20')
    if now.tzinfo is None:raise ValueError("timezone-aware now required")
    accepted=[];held=[]
    for row in rows:
        if not isinstance(row,dict):continue
        identifier=str(row.get("id","")).strip()
        deadline=parse_deadline(row.get("application_deadline"))
        kind=str(row.get("employment_type","")).strip()
        count=row.get("headcount")
        org=row.get("organization")
        title=row.get("title")
        source=row.get("official_url")
        verified=row.get("official_verified") is True
        evidence=row.get("deadline_evidence")
        evidence_ok=(isinstance(evidence,dict) and evidence.get("kind")=="official_application_deadline" and isinstance(evidence.get("quote"),str) and len(evidence["quote"].strip())>=8 and evidence.get("reviewed") is True)
        evidence_time=parse_deadline(evidence.get("application_deadline")) if isinstance(evidence,dict) else None
        evidence_ok=evidence_ok and evidence_time is not None and evidence_time==deadline
        if evidence_ok:
            # Evidence text must contain the same date and clock time, not just a separately supplied value.
            quote=evidence["quote"].replace(".","-").replace("/","-")
            stamp=deadline.strftime("%Y-%m-%d")
            evidence_ok=stamp in quote and deadline.strftime("%H:%M") in quote
        # A bare verified flag or ALIO posting-end date is not sufficient.
        url=urlparse(source) if isinstance(source,str) else None
        official_url_ok=bool(url and url.scheme=='https' and url.hostname and not url.hostname.endswith(('.test','.example','.invalid')) and url.hostname not in {'example.com','example.org','localhost'})
        if not identifier or not isinstance(org,str) or not org.strip() or not isinstance(title,str) or not title.strip() or not official_url_ok or not verified or not evidence_ok or deadline is None or not isinstance(count,int) or isinstance(count,bool) or count<1:
            held.append({"id":identifier,"reason":"missing verified official deadline, source, or count"});continue
        if deadline<=now:
            held.append({"id":identifier,"reason":"application deadline elapsed"});continue
        if kind not in REGULAR:
            held.append({"id":identifier,"reason":"not confirmed regular employment"});continue
        accepted.append(row)
    # Popularity is intentionally excluded unless measured, comparable metrics exist.
    accepted.sort(key=lambda r:(-r["headcount"],r["application_deadline"],str(r["id"])))
    seen=set();unique=[]
    for row in accepted:
        if row["id"] not in seen:unique.append(row);seen.add(row["id"])
    return unique[:limit],held
def main():
    p=argparse.ArgumentParser();p.add_argument("snapshot");p.add_argument("output");p.add_argument("--limit",type=int,default=5)
    args=p.parse_args()
    raw=json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    if not isinstance(raw,list):raise ValueError("Expected a JSON array of verified official job rows")
    selected,held=choose(raw,limit=args.limit)
    out=Path(args.output)
    if out.exists():raise FileExistsError("Existing output protected")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({"selected":selected,"held":held,"checked_at":datetime.datetime.now(KST).isoformat()},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Selected {len(selected)}; held {len(held)}. No posting performed.")
if __name__=="__main__":main()
