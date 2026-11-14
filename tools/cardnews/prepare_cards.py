"""Build factual, minimal card inputs from previously verified selected jobs.
No auto-publishing; only fields explicitly supplied by the reviewed snapshot.
"""
import argparse,json
from pathlib import Path
def cards_for(job):
    name=job.get("organization","기관명 원문 확인")
    title=job.get("title","채용공고 원문 확인")
    deadline=job["application_deadline"]
    n=job["headcount"]
    return {
        "verified":True,
        "source":job["official_url"],
        "brand":"CAREERPICK | 커리어픽",
        "cards":[
            {"title":name,"subtitle":title,"sections":[{"heading":"정규직 채용","items":[f"모집인원: {n}명",f"원서 접수마감: {deadline} (한국시간)"]}]},
            {"title":"모집 정보","sections":[{"heading":"확인된 조건","items":[f"기관: {name}","고용형태: 정규직",f"채용인원: {n}명"]}]},
            {"title":"지원 전 확인","sections":[{"heading":"공식 원문 필수","items":[f"접수마감: {deadline} (한국시간)","세부 자격·직무·전형은 공식 공고 확인","공식 원문에서 접수 가능 여부 재확인"]}]}
        ],
        "threads_caption":f"{name} 정규직 {n}명 채용. 접수마감 {deadline} (한국시간). 세부사항은 공식 공고 확인.\n자세한 사항은 프로필링크 확인",
        "instagram_caption":f"{name} 정규직 채용 안내. 모집인원 {n}명. 접수마감 {deadline} (한국시간). 상세 지원 조건은 공식 공고를 확인하세요."
    }
def main():
    p=argparse.ArgumentParser();p.add_argument("selected_json");p.add_argument("output_dir");args=p.parse_args()
    data=json.loads(Path(args.selected_json).read_text(encoding="utf-8"))
    out=Path(args.output_dir)
    if out.exists():raise FileExistsError("Existing directory protected")
    jobs=data["selected"]
    if not jobs:print("No verified active jobs; no output");return
    out.mkdir(parents=True)
    for job in jobs:
        id=str(job["id"])
        if not id.replace("-","").replace("_","").isalnum():raise ValueError("Unsafe ID")
        (out/(id+".json")).write_text(json.dumps(cards_for(job),ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Prepared {len(jobs)} reviewed job inputs; run generate.py for each, then visually inspect. No posting.")
if __name__=="__main__":main()
