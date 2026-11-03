"""Separate candidate observation state from successful notification delivery.

Detection is not delivery. Never mark a notification sent from a dry run.
"""
import json
import hashlib
import os
import tempfile
from pathlib import Path

def delivery_key(job_id, subscription_id, kind="new_job"):
    """Avoid storing raw subscription identifiers in persisted delivery records."""
    raw = json.dumps([str(kind), str(job_id), str(subscription_id)], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def delivered(state, job_id, subscription_id, kind="new_job"):
    key = delivery_key(job_id, subscription_id, kind)
    return key in state.get("delivered", [])

def mark_delivered(state, job_id, subscription_id, kind="new_job"):
    if not job_id or not subscription_id:
        raise ValueError("job and subscriber are required")
    key = delivery_key(job_id, subscription_id, kind)
    updated = dict(state)
    updated["delivered"] = sorted(set(state.get("delivered", [])) | {key})
    return updated

def load(path):
    p = Path(path)
    if not p.exists():
        return {"delivered": []}
    state = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("delivered"), list):
        raise ValueError("Invalid delivery ledger format")
    if any(not isinstance(key, str) or len(key) != 64 or any(ch not in "0123456789abcdef" for ch in key)
           for key in state["delivered"]):
        raise ValueError("Invalid hashed delivery key")
    return state

def save(path, state):
    """Atomically persist a delivery snapshot; caller must save it privately."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=".delivery-", dir=str(p.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, p)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
