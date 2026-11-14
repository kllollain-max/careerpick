"""Offline end-to-end cardnews build from independently verified normalized API snapshot.
Never modifies live CareerPick or publishes social posts.
"""
import argparse,datetime,hashlib,json,os,shutil,tempfile,zipfile
from pathlib import Path
from zoneinfo import ZoneInfo
from select_jobs import choose
from prepare_cards import cards_for
from generate import render
KST=ZoneInfo("Asia/Seoul")
def run(snapshot,output,limit=5):
    snapshot=Path(snapshot);output=Path(output)
    if output.exists():raise FileExistsError("Refusing to overwrite existing output")
    data=snapshot.read_bytes()
    rows=json.loads(data)
    if not isinstance(rows,list):raise ValueError("Expected verified job snapshot array")
    now=datetime.datetime.now(KST)
    selected,held=choose(rows,now,limit)
    if not selected:return {"created":0,"held":len(held),"reason":"No independently verified open regular vacancies"}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cardnews-stage-",dir=output.parent) as tmp:
        stage=Path(tmp)
        manifest={"snapshot_sha256":hashlib.sha256(data).hexdigest(),"checked_at":now.isoformat(),"jobs":[],"held":held,"publication":"disabled"}
        for job in selected:
            identifier=str(job["id"])
            if not identifier.replace("-","").replace("_","").isalnum():raise ValueError("Unsafe job ID")
            payload=cards_for(job)
            folder=stage/identifier;folder.mkdir()
            names=[]
            for i,card in enumerate(payload["cards"],1):
                name=f"card_{i:02}.png"
                render(card,i,len(payload["cards"]),payload["brand"]).save(folder/name)
                names.append(name)
            (folder/"source.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
            with zipfile.ZipFile(folder/"cardnews.zip","w",zipfile.ZIP_DEFLATED) as z:
                for name in names+["source.json"]:z.write(folder/name,name)
            with zipfile.ZipFile(folder/"cardnews.zip") as z:
                if z.testzip() is not None:raise RuntimeError("ZIP integrity failure")
            manifest["jobs"].append({"id":identifier,"headcount":job["headcount"],"official_url":job["official_url"],"png_count":len(names),"visual_review":"PENDING"})
        (stage/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
        if output.exists():raise FileExistsError("Output created concurrently")
        os.rename(stage,output)
    return {"created":len(selected),"held":len(held),"output":str(output),"visual_review":"PENDING"}
def main():
    p=argparse.ArgumentParser();p.add_argument("snapshot");p.add_argument("output");p.add_argument("--limit",type=int,default=5);a=p.parse_args()
    print(json.dumps(run(a.snapshot,a.output,a.limit),ensure_ascii=False))
if __name__=="__main__":main()
