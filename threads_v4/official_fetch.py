"""Read-only official source fetch with explicit failure evidence. Never auto-approves."""
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

def check_url(url, *, timeout=12, opener=None):
    parsed=urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:
        return {"url":url,"status":"HOLD","reason":"URL_INVALID"}
    request=urllib.request.Request(url,headers={"User-Agent":"CareerPick-SourceAudit/1.0","Accept":"text/html,application/pdf"})
    opener=opener or urllib.request.urlopen
    try:
        with opener(request,timeout=timeout) as response:
            data=response.read(2_000_001)
            status=response.getcode()
            kind=response.headers.get("Content-Type","")
        if status!=200 or not data or len(data)>2_000_000:
            return {"url":url,"status":"HOLD","reason":"HTTP_OR_SIZE_INVALID","http_status":status}
        return {"url":url,"status":"FETCHED_NOT_VERIFIED","http_status":status,
                "content_type":kind,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
    except urllib.error.HTTPError as exc:
        return {"url":url,"status":"HOLD","reason":"HTTP_ERROR","http_status":exc.code}
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        return {"url":url,"status":"HOLD","reason":"NETWORK_ERROR","error_type":type(exc).__name__}

def audit(urls):
    return {"schema_version":1,"checked_at":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
            "checks":[check_url(u) for u in urls],"official_approved_count":0,
            "meta_posted":False}

if __name__=="__main__":
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--audit",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    source=json.loads(Path(args.audit).read_text(encoding="utf-8"))
    urls=[source.get("source"),source.get("institution_notice")]
    result=audit([u for u in urls if isinstance(u,str)])
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
