"""Private GitHub repository storage for the notification delivery ledger.

Requires CP_LEDGER_REPOSITORY (owner/private-repo), CP_LEDGER_TOKEN (fine-grained
Contents read/write token), and an existing private repository. This module
does not enable sending. Public CareerPick repository must never hold the ledger.
"""
import base64
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.alert_delivery_ledger import load as load_local


def _config():
    repo = os.environ.get("CP_LEDGER_REPOSITORY", "").strip()
    token = os.environ.get("CP_LEDGER_TOKEN", "").strip()
    if not repo or not token or len(repo.split("/")) != 2:
        raise RuntimeError("Private ledger repository and token are required")
    if repo.lower() in {"jobinfo-hub/jobinfo-hub.github.io", "kllollain-max/careerpick"}:
        raise RuntimeError("Refusing to store delivery ledger in the public site repository")
    return repo, token


def _request(url, token, method="GET", payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github.object+json" if "/contents/" in url else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    with urlopen(request, timeout=15) as response:
        # Queue/ledger snapshots can exceed the Contents API inline threshold.
        raw = response.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise RuntimeError("Private state response exceeds safety limit")
        return json.loads(raw.decode("utf-8"))


def read_private_ledger():
    repo, token = _config()
    url = "https://api.github.com/repos/" + repo + "/contents/delivery-ledger.json"
    try:
        result = _request(url, token)
    except HTTPError as error:
        if error.code == 404:
            return {"delivered": []}, None
        raise
    if result.get("encoding") == "none":
        result_blob = _request("https://api.github.com/repos/" + repo + "/git/blobs/" + result["sha"], token)
        encoded = result_blob["content"]
    else:
        encoded = result["content"].replace(chr(10), "")
    data = json.loads(base64.b64decode(encoded).decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("delivered"), list):
        raise ValueError("Invalid private ledger")
    for field in ("delivered", "pending"):
        entries = data.get(field, [])
        if not isinstance(entries, list) or any(not isinstance(key, str) or len(key) != 64 or any(ch not in "0123456789abcdef" for ch in key) for key in entries):
            raise ValueError("Invalid private ledger " + field + " records")
    if set(data["delivered"]) & set(data.get("pending", [])):
        raise ValueError("A delivery cannot be pending and delivered simultaneously")
    return data, result["sha"]


def write_private_ledger(state, sha):
    repo, token = _config()
    if not isinstance(state, dict) or not isinstance(state.get("delivered"), list):
        raise ValueError("Invalid ledger state")
    payload = {
        "message": "Update private notification delivery ledger",
        "content": base64.b64encode((json.dumps(state, sort_keys=True) + chr(10)).encode("utf-8")).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    url = "https://api.github.com/repos/" + repo + "/contents/delivery-ledger.json"
    # GitHub's sha precondition prevents silent overwrites; callers must retry conflicts.
    return _request(url, token, method="PUT", payload=payload)


def reserve_private_delivery(job_id, subscription_id, kind="new_job"):
    """Reserve before sending. An uncertain outcome must be reviewed, not retried.

    The GitHub content SHA prevents two concurrent writers from reserving the
    same delivery key. Reservation is not proof that a push was delivered.
    """
    from scripts.alert_delivery_ledger import delivery_key
    key = delivery_key(job_id, subscription_id, kind)
    if not job_id or not subscription_id:
        raise ValueError("Job and subscription are required")
    for attempt in range(3):
        state, sha = read_private_ledger()
        if sha is None:
            raise RuntimeError("Private ledger must be initialized before reserving")
        if key in state["delivered"] or key in state.get("pending", []):
            return False
        updated = dict(state)
        updated["pending"] = sorted(set(state.get("pending", [])) | {key})
        try:
            write_private_ledger(updated, sha)
            return True
        except HTTPError as error:
            if error.code not in (409, 422) or attempt == 2:
                raise RuntimeError("Private GitHub ledger reservation write failed (HTTP %d); do not retry push blindly" % error.code) from None
    raise RuntimeError("Could not reserve delivery")


def finalize_private_delivery(job_id, subscription_id, kind="new_job"):
    """Mark an accepted send; retain pending reservation if persistence fails."""
    from scripts.alert_delivery_ledger import delivery_key
    key = delivery_key(job_id, subscription_id, kind)
    for attempt in range(3):
        state, sha = read_private_ledger()
        if sha is None or key not in state.get("pending", []):
            raise RuntimeError("Missing delivery reservation")
        updated = dict(state)
        updated["pending"] = sorted(set(state.get("pending", [])) - {key})
        updated["delivered"] = sorted(set(state["delivered"]) | {key})
        try:
            write_private_ledger(updated, sha)
            return
        except HTTPError as error:
            if error.code not in (409, 422) or attempt == 2:
                raise RuntimeError("Private GitHub ledger finalization write failed (HTTP %d); review pending reservation" % error.code) from None
    raise RuntimeError("Could not finalize delivery")
