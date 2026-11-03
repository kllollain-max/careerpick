"""Private checkpoint cursor for scheduled rollout; no subscriber identifiers stored.

This records only a numeric position and a digest of the ordered export.
Repository must be private. GitHub SHA compare-and-swap prevents lost updates.
"""
import base64
import hashlib
import json
from urllib.error import HTTPError
from scripts.private_delivery_store import _config, _request

FILE = "push-rollout-cursor.json"


def fingerprint(ids):
    digest = hashlib.sha256()
    for sid in ids:
        digest.update(str(sid).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def read_cursor():
    repo, token = _config()
    url = "https://api.github.com/repos/" + repo + "/contents/" + FILE
    try:
        payload = _request(url, token)
    except HTTPError as error:
        if error.code == 404:
            return {"version": 1, "next_index": 0, "export_hash": ""}, None
        raise
    state = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
    if (not isinstance(state, dict) or state.get("version") != 1
            or type(state.get("next_index")) is not int or state["next_index"] < 0
            or not isinstance(state.get("export_hash"), str)
            or len(state["export_hash"]) not in (0, 64)):
        raise ValueError("Invalid private push checkpoint")
    return state, payload["sha"]


def save_cursor(index, export_hash, sha):
    if type(index) is not int or index < 0 or len(export_hash) != 64:
        raise ValueError("Invalid cursor update")
    repo, token = _config()
    data = {"version": 1, "next_index": index, "export_hash": export_hash}
    payload = {"message": "Advance private push scan checkpoint",
               "content": base64.b64encode(
                   (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")
               ).decode("ascii")}
    if sha is not None:
        payload["sha"] = sha
    url = "https://api.github.com/repos/" + repo + "/contents/" + FILE
    try:
        return _request(url, token, method="PUT", payload=payload)
    except HTTPError as error:
        if error.code in (409, 422):
            raise RuntimeError("Concurrent checkpoint writer detected; stop without sending") from None
        raise


def plan_window(ids, state, max_lookups):
    if not ids or max_lookups < 1:
        return [], 0, fingerprint(ids)
    export_hash = fingerprint(ids)
    start = state["next_index"] if state["export_hash"] == export_hash else 0
    if start >= len(ids):
        start = 0
    end = min(start + max_lookups, len(ids))
    return ids[start:end], (end if end < len(ids) else 0), export_hash
