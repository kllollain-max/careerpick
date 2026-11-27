"""Collect pinned public attachments for human review, never approval or posting."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

NOTICE = "a307271"
POST_SHA = "1a06be223e4027c53bbdd19f2e2036238025b4e8c60813bdfd86e161e3292316"
DETAIL_SHA = "f8a323ac11eb6dc569c946d66df0cdb045e5686ce7ea54d37388031ec30e82ce"
KST = ZoneInfo("Asia/Seoul")
DEADLINE = datetime(2026, 11, 30, 16, tzinfo=KST)
MAX_BYTES = 20_000_000
ALIO = "https://www.alio.go.kr/download/download.json?fileNo="
DOCUMENTS = (
    ("notice.pdf", b"%PDF-", (ALIO + "3088960", "https://www.korea.kr/common/download.do?fileId=145822501&tblKey=GBD")),
    ("application.hwp", bytes.fromhex("d0cf11e0a1b11ae1"), (ALIO + "3088961",)),
    ("job-description.hwp", bytes.fromhex("d0cf11e0a1b11ae1"), (ALIO + "3088962",)),
)

# Exact institution PDF linked from the current, separately read KNPS notice.
# Preserve the legacy pin and its output; the new pin has its own subdirectory.
MUDEUNGSAN_NOTICE = "a307417"
MUDEUNGSAN_POST_SHA = "b3a52f04564d142583f5d90b3866c2e384d97d79414b626128f8749ea67f95c5"
MUDEUNGSAN_DETAIL_SHA = "50fcceca68d11f84611f382082ee5672fd350ce36bf6f34a67465b9cecedcc5e"
MUDEUNGSAN_DEADLINE = datetime(2026, 12, 9, 18, tzinfo=KST)
MUDEUNGSAN_DOCUMENTS = (
    ("notice.pdf", b"%PDF-", ("https://www.knps.or.kr/portal/file/cdown.do?fileId=w2nychgk7yxFPuOMtBtMbg%3D%3D&fileNo=0&tfId=TF006",)),
)


def fetch_public(url):
    import urllib.request
    from scripts.threads_http import read_response
    from scripts.threads_reviewed_ingest import OfficialRedirect, official_url_allowed
    if not official_url_allowed(url):
        raise ValueError("OFFICIAL_URL_NOT_ALLOWED")
    req = urllib.request.Request(url, headers={"User-Agent": "CareerPickIndependentOfficialReview/1.0", "Accept": "*/*"})
    opener = urllib.request.build_opener(OfficialRedirect())
    with read_response(req, timeout=10, opener=opener.open) as response:
        final = response.geturl()
        if response.status != 200 or not official_url_allowed(final):
            raise ValueError("OFFICIAL_RESPONSE_NOT_ALLOWED")
        return response.read(MAX_BYTES + 1), final, response.headers.get("Content-Type", "")


def capture(bundle, out, fetch=fetch_public, now=None, *, notice=NOTICE,
            post_sha=POST_SHA, detail_sha=DETAIL_SHA, deadline=DEADLINE,
            documents=DOCUMENTS):
    now = now or datetime.now(KST)
    manifest = {"notice_id": notice, "automatic_approval": False,
                "approved_for_queue": False, "meta_posted": False,
                "semantic_review": "required", "documents": []}
    if (bundle.get("status") != "review_required" or bundle.get("approved_for_queue") is not False
            or now >= deadline):
        return manifest
    candidates = bundle.get("drafts", []) + bundle.get("official_source_alternatives", [])
    if not any(isinstance(c, dict) and c.get("notice_id") == notice
               and c.get("status") == "unreviewed" and c.get("source_post_sha256") == post_sha
               and c.get("source_detail_sha256") == detail_sha for c in candidates):
        return manifest
    out.mkdir(parents=True, exist_ok=True)
    for filename, magic, urls in documents:
        item = {"name": filename, "status": "unverified", "attempts": []}
        for url in urls:
            try:
                data, final, content_type = fetch(url)
                if len(data) > MAX_BYTES or not data.startswith(magic):
                    raise ValueError("ATTACHMENT_BYTES_OR_MAGIC_INVALID")
                (out / filename).write_bytes(data)
                item.update(status="raw_bytes_captured_for_review", url=url, final_url=final,
                            size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                            content_type=content_type, checked_at=datetime.now(KST).isoformat())
                break
            except (OSError, ValueError) as exc:
                item["attempts"].append({"url": url, "error": str(exc)[:160]})
        manifest["documents"].append(item)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="threads-unreviewed-drafts.json")
    parser.add_argument("--output", default="threads-official-raw-review")
    args = parser.parse_args()
    out = Path(args.output)
    bundle = json.loads(Path(args.input).read_text(encoding="utf-8"))
    manifest = capture(bundle, out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Pinned raw-document review artifacts:", sum(d["status"] == "raw_bytes_captured_for_review" for d in manifest["documents"]), "; approved: 0; posted: 0")
    extra_out = out / MUDEUNGSAN_NOTICE
    extra = capture(bundle, extra_out, notice=MUDEUNGSAN_NOTICE,
                    post_sha=MUDEUNGSAN_POST_SHA, detail_sha=MUDEUNGSAN_DETAIL_SHA,
                    deadline=MUDEUNGSAN_DEADLINE, documents=MUDEUNGSAN_DOCUMENTS)
    if extra["documents"]:
        (extra_out / "manifest.json").write_text(json.dumps(extra, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Mudeungsan pinned raw-document review artifacts:", sum(d["status"] == "raw_bytes_captured_for_review" for d in extra["documents"]), "; approved: 0; posted: 0")


if __name__ == "__main__":
    main()
