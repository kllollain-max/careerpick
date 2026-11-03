#!/usr/bin/env python3
"""One-shot live check; repository snapshots stay unchanged."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alio
from scripts.collect_alio import collect
ROOT = Path(__file__).resolve().parents[1]

def main():
    report = {"status": "not_started", "list_verified": False,
              "detail_verified": False, "source_preserved": False}
    names = ("alio.json", "alio-detail.json")
    originals = {n: (ROOT / n).read_bytes() for n in names}
    key = os.environ.get("ALIO_KEY", "").strip()
    report["key_present"] = bool(key)
    output = ROOT / "live-check-output"
    output.mkdir(exist_ok=True)
    try:
        if not key:
            raise RuntimeError("blocked_missing_secret")
        listing = alio.call(key, 1)
        report["list_verified"] = True
        if not listing["result"]:
            raise RuntimeError("empty_list_preserved")
        alio.call_detail(key, listing["result"][0]["recrutPblntSn"])
        report["detail_verified"] = True
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            for name, content in originals.items():
                (stage / name).write_bytes(content)
            result = collect(stage)
            report["collection_status"] = result["status"]
            if result["status"] != "collected":
                raise RuntimeError("collection_not_confirmed")
            old = {p["id"]:p for p in json.loads(originals["alio.json"])["posts"]}
            candidate = json.loads((stage / "alio.json").read_text())
            new = {p["id"]:p for p in candidate["posts"]}
            report.update(status="verified_candidate", before=len(old), after=len(new),
                added=len(new.keys()-old.keys()),
                changed=sum(old[k] != new[k] for k in old.keys() & new.keys()),
                removed=len(old.keys()-new.keys()), collected_at=candidate["updated"],
                deadline_expired=sum(bool(p.get("due")) and
                    datetime.fromisoformat(p["due"]) < datetime.now(alio.KST)
                    for p in new.values()))
            report["closure_note"] = "Date-based expiration only; absence does not prove official closure"
            for name in names:
                shutil.copyfile(stage / name, output / name)
    except Exception as error:
        report["status"] = "blocked_or_failed_preserved"
        report["error_type"] = type(error).__name__
        safe = {"blocked_missing_secret", "empty_list_preserved", "collection_not_confirmed"}
        safe.update("ALIO API failure code=" + str(c) for c in (1,2,3,5,6,7,8,10,11))
        if str(error) in safe:
            report["reason"] = str(error)
    finally:
        report["source_preserved"] = all((ROOT / n).read_bytes()==b for n,b in originals.items())
        report["source_sha256"] = {n:hashlib.sha256(b).hexdigest() for n,b in originals.items()}
        (output / "report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False))
    return 0 if report["status"]=="verified_candidate" and report["source_preserved"] else 2
if __name__=="__main__":
    sys.exit(main())
