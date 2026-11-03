"""Private durable push queue with CAS writes and fail-closed transitions.

Stores only hashed pair keys and provider message metadata in a private repo.
The pre-existing delivery ledger remains the authoritative duplicate guard.
"""
import base64
import json
import hashlib
from urllib.error import HTTPError
from scripts.private_delivery_store import _config, _request
from scripts.alert_delivery_ledger import delivery_key

FILE = "push-delivery-queue.json"
STATES = {"pending", "reserved", "accepted", "failed", "uncertain"}
TRANSITIONS = {
    "pending": {"reserved", "failed"},
    "reserved": {"accepted", "failed", "uncertain"},
    "accepted": set(), "failed": set(), "uncertain": set(),
}


def subscriber_hash(sid):
    return hashlib.sha256(sid.encode("utf-8")).hexdigest()


def empty_queue():
    return {"version": 1, "tasks": {}}


def validate(data):
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("tasks"), dict):
        raise ValueError("Invalid private push queue")
    for key, entry in data["tasks"].items():
        if (not isinstance(key, str) or len(key) != 64
                or any(c not in "0123456789abcdef" for c in key)
                or not isinstance(entry, dict) or entry.get("state") not in STATES):
            raise ValueError("Invalid push queue entry")
        if entry.get("message_id") is not None and not isinstance(entry["message_id"], str):
            raise ValueError("Invalid OneSignal message ID")
    return data


def enqueue(data, pairs, ledger):
    """Retain old tasks; never override accepted or uncertain entries."""
    validate(data)
    tasks = dict(data["tasks"])
    completed = set(ledger.get("delivered", []))
    protected = completed | set(ledger.get("pending", []))
    for job, sub in pairs:
        key = delivery_key(job["id"], sub["subscription_id"])
        if key not in tasks and key not in completed:
            tasks[key] = {"state": "uncertain" if key in protected else "pending",
                          "message_id": None, "job_id": str(job["id"]),
                          "subscriber_hash": subscriber_hash(sub["subscription_id"])}
    return {"version": 1, "tasks": tasks}


def transition(data, key, target, *, message_id=None):
    validate(data)
    tasks = dict(data["tasks"])
    if key not in tasks or target not in TRANSITIONS[tasks[key]["state"]]:
        raise ValueError("Unsafe push state transition")
    if target == "accepted" and not message_id:
        raise ValueError("Provider message ID required to accept")
    entry = dict(tasks[key])
    entry["state"] = target
    if message_id is not None:
        entry["message_id"] = message_id
    tasks[key] = entry
    return {"version": 1, "tasks": tasks}


def quarantine_inflight(data):
    """A crashed process may have sent any reserved task; never retry it."""
    validate(data)
    tasks = {k: (dict(v, state="uncertain") if v["state"] == "reserved" else v)
             for k, v in data["tasks"].items()}
    return {"version": 1, "tasks": tasks}


def counts(data):
    validate(data)
    result = {state: 0 for state in STATES}
    for entry in data["tasks"].values():
        result[entry["state"]] += 1
    result["total"] = len(data["tasks"])
    return result


def read_queue():
    repo, token = _config()
    url = "https://api.github.com/repos/" + repo + "/contents/" + FILE
    try:
        value = _request(url, token)
    except HTTPError as error:
        if error.code == 404:
            return empty_queue(), None
        raise
    sha = value["sha"]
    if value.get("encoding") == "none":
        value = _request("https://api.github.com/repos/" + repo + "/git/blobs/" + sha, token)
    return validate(json.loads(base64.b64decode(value["content"]).decode("utf-8"))), sha


def write_queue(data, sha):
    validate(data)
    repo, token = _config()
    url = "https://api.github.com/repos/" + repo + "/contents/" + FILE
    payload = {"message": "Advance private push queue",
               "content": base64.b64encode((json.dumps(data, sort_keys=True)+"\n").encode()).decode()}
    if sha:
        payload["sha"] = sha
    try:
        return _request(url, token, method="PUT", payload=payload)
    except HTTPError as error:
        if error.code in (409, 422):
            raise QueueConflict("Private queue CAS conflict; stop to prevent duplicate sends") from None
        raise


class QueueConflict(RuntimeError):
    pass


def update_queue(change):
    """Retry only a known CAS rejection, never an ambiguous storage failure.

    Recompute against the latest version; never replay a provider request.
    """
    for _ in range(5):
        data, sha = read_queue()
        updated = change(data)
        if updated == data:
            return data
        try:
            write_queue(updated, sha)
            return updated
        except QueueConflict:
            continue
    raise QueueConflict("Private queue contention budget exhausted")


def claim(key, owner):
    """Only the writer that durably claimed this pending task may send it."""
    def change(data):
        if data["tasks"].get(key, {}).get("state") != "pending":
            return data
        updated = transition(data, key, "reserved")
        updated["tasks"][key]["owner"] = owner
        return updated
    updated = update_queue(change)
    entry = updated["tasks"].get(key, {})
    return entry.get("state") == "reserved" and entry.get("owner") == owner


def owned(key, owner):
    data, _ = read_queue()
    entry = data["tasks"].get(key, {})
    return entry.get("state") == "reserved" and entry.get("owner") == owner


def record_outcome(key, owner, state, reason, message_id=None):
    if state not in {"accepted", "failed", "uncertain"}:
        raise ValueError("Invalid provider outcome state")
    def change(data):
        entry = data["tasks"].get(key, {})
        if entry.get("owner") != owner:
            raise RuntimeError("Private queue owner mismatch")
        # Another run may quarantine an in-flight request. Only its original
        # owner with a confirmed provider ID may settle it as accepted.
        if entry.get("state") == "accepted":
            return data
        if entry.get("state") == "uncertain" and state != "accepted":
            return data
        if state == "accepted" and not message_id:
            raise ValueError("Provider message ID required")
        if entry.get("state") not in {"reserved", "uncertain"}:
            raise RuntimeError("Private queue task is not in flight")
        tasks = dict(data["tasks"])
        tasks[key] = dict(entry, state=state, reason=reason, message_id=message_id)
        return {"version": 1, "tasks": tasks}
    return update_queue(change)
