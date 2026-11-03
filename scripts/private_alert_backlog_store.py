"""Private, optimistic-concurrency storage for ALIO candidate backlog.

Not wired to live sending. Uses the existing private delivery-ledger repository,
but a separate file; never stores subscriber identifiers.
"""
import base64
import json
from urllib.error import HTTPError

from scripts.private_delivery_store import _config, _request
from scripts.alert_candidate_backlog import reconcile

FILE_NAME = "candidate-backlog.json"


def read_backlog():
    repo, token = _config()
    url = "https://api.github.com/repos/" + repo + "/contents/" + FILE_NAME
    try:
        result = _request(url, token)
    except HTTPError as error:
        if error.code == 404:
            return None, None
        raise
    if not isinstance(result, dict) or not isinstance(result.get("sha"), str):
        raise ValueError("Invalid private backlog metadata")
    try:
        raw = base64.b64decode(result["content"].replace("\n", ""), validate=True)
        state = json.loads(raw)
    except (KeyError, ValueError, TypeError):
        raise ValueError("Invalid private backlog payload") from None
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("jobs"), list):
        raise ValueError("Invalid private backlog schema")
    # Validate stored candidates without silently treating malformed data as empty.
    from datetime import datetime
    from scripts.detect_new_job_alerts import KST
    reconcile(state["jobs"], [], now=datetime.now(KST))
    return state["jobs"], result["sha"]


def save_backlog(jobs, sha):
    if sha is None:
        raise RuntimeError("Private backlog must be initialized manually before writes")
    if not isinstance(sha, str) or not sha:
        raise ValueError("Invalid private backlog SHA")
    from datetime import datetime
    from scripts.detect_new_job_alerts import KST
    reconcile(jobs, [], now=datetime.now(KST))
    repo, token = _config()
    body = json.dumps({"version": 1, "jobs": jobs}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    payload = {"message": "Update private CareerPick candidate backlog",
               "content": base64.b64encode(body).decode("ascii"), "sha": sha}
    url = "https://api.github.com/repos/" + repo + "/contents/" + FILE_NAME
    try:
        return _request(url, token, method="PUT", payload=payload)
    except HTTPError as error:
        if error.code in (409, 422):
            raise RuntimeError("Private backlog changed concurrently; do not overwrite") from None
        raise
