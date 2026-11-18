"""Read-only official source fetch with explicit failure evidence. Never auto-approves."""
import hashlib
import json
import urllib.error
import urllib.request
import ipaddress
import socket
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from threads_v4.official_text import extract
from threads_v4.cross_source import compare
from threads_v4.correction_scan import scan

def check_url(url, *, timeout=12, opener=None):
    parsed=urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:
        return {"url":url,"status":"HOLD","reason":"URL_INVALID"}
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        return {"url":url,"status":"HOLD","reason":"PRIVATE_HOST_BLOCKED"}
    try:
        resolved=socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
        if not resolved or any(not ipaddress.ip_address(item[4][0]).is_global for item in resolved):
            return {"url":url,"status":"HOLD","reason":"PRIVATE_ADDRESS_BLOCKED"}
    except (OSError,ValueError):
        return {"url":url,"status":"HOLD","reason":"DNS_UNVERIFIED"}
    request=urllib.request.Request(url,headers={"User-Agent":"CareerPick-SourceAudit/1.0","Accept":"text/html,application/pdf"})
    opener=opener or urllib.request.urlopen
    try:
        with opener(request,timeout=timeout) as response:
            data=response.read(2_000_001)
            status=response.getcode()
            kind=response.headers.get("Content-Type","")
        if status!=200 or not data or len(data)>2_000_000:
            return {"url":url,"status":"HOLD","reason":"HTTP_OR_SIZE_INVALID","http_status":status}
        result={"url":url,"status":"FETCHED_NOT_VERIFIED","http_status":status,
                "content_type":kind,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        if "text/html" in kind.lower():
            result["text_evidence"]=extract(data)
            result["correction_scan"]=scan(result["text_evidence"]["plain_text"])
            result["text_evidence"].pop("plain_text",None)
        return result
    except urllib.error.HTTPError as exc:
        return {"url":url,"status":"HOLD","reason":"HTTP_ERROR","http_status":exc.code}
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        return {"url":url,"status":"HOLD","reason":"NETWORK_ERROR","error_type":type(exc).__name__}

def audit(urls):
    checks=[check_url(u) for u in urls]
    return {"schema_version":1,"checked_at":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
            "checks":checks,"cross_source_review":compare(checks),
            "official_approved_count":0,"meta_posted":False}

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
