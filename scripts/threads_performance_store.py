#!/usr/bin/env python3
"""Collect read-only Threads insights and CAS-save their dedicated state file.

Only kllollain-max/careerpick's threads-publisher-state:threads/performance.json
is writable here. Publication claims, writer queue, maintenance checkpoints and
main are never written. GitHub PUTs are not blindly retried after uncertainty.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.threads_http import read_response
from scripts.threads_performance import POLICY_ID, collect_due, merge_observations, summarize

REPOSITORY = "kllollain-max/careerpick"
BRANCH = "threads-publisher-state"
STATE_PATH = "threads/performance.json"
API_ROOT = "https://api.github.com/repos/" + REPOSITORY


class StateError(RuntimeError):
    """Only fixed, credential-free error messages may leave this boundary."""


class RequestError(StateError):
    def __init__(self, status=None, *, uncertain=False):
        self.status = status
        self.uncertain = uncertain
        super().__init__("GitHub measurement state request unconfirmed" if uncertain
                         else "GitHub measurement state request rejected")


def validate_state(state):
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise StateError("Measurement state schema invalid; preserve existing data")
    if state.get("policy_id", POLICY_ID) != POLICY_ID:
        raise StateError("Measurement state policy conflict; preserve existing data")
    values = state.get("observations")
    if not isinstance(values, list):
        raise StateError("Measurement observations invalid; preserve existing data")
    by_id = {}
    for value in values:
        if not isinstance(value, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("observation_id", ""))):
            raise StateError("Observation identity invalid; preserve existing data")
        identifier = value["observation_id"]
        if identifier in by_id:
            raise StateError("Duplicate observation identity; preserve existing data")
        if not str(value.get("post_id", "")).isdigit() or value.get("window") not in {"24h", "7d"}:
            raise StateError("Observation key invalid; preserve existing data")
        by_id[identifier] = value
    return state


def contains_observations(state, observations):
    existing = {value["observation_id"]: value for value in validate_state(state)["observations"]}
    for value in observations:
        current = existing.get(value["observation_id"])
        if current is not None and current != value:
            raise StateError("Immutable observation conflict; preserve existing data")
        if current is None:
            return False
    return True


class GitHubPerformanceState:
    def __init__(self, token, *, opener=None, sleeper=None):
        if not isinstance(token, str) or not token:
            raise StateError("Existing GitHub state credential unavailable")
        if os.getenv("GITHUB_REPOSITORY", REPOSITORY) != REPOSITORY:
            raise StateError("Unexpected repository; measurement write blocked")
        self._token = token
        self._opener = opener or urllib.request.urlopen
        self._sleeper = sleeper

    def _request(self, method, path, payload=None):
        if method not in {"GET", "PUT"}:
            raise StateError("Unsupported measurement state method")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(API_ROOT + path, data=data, method=method,
            headers={"Authorization": "Bearer " + self._token,
                     "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2022-11-28"})
        try:
            if method == "GET":
                response = read_response(request, timeout=20, opener=self._opener, sleeper=self._sleeper)
            else:
                response = self._opener(request, timeout=20)
            with response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Do not read or print request/response bodies or arbitrary messages.
            raise RequestError(error.code, uncertain=method == "PUT" and error.code not in {400, 401, 403, 404, 409, 422}) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError, TypeError):
            raise RequestError(uncertain=method == "PUT") from None

    def read(self):
        path = "/contents/" + STATE_PATH + "?" + urllib.parse.urlencode({"ref": BRANCH})
        try:
            result = self._request("GET", path)
        except RequestError as error:
            if error.status != 404:
                raise
            # Contents 404 also means an absent branch or inaccessible repo.
            # Never turn either condition into a new empty publisher-state branch.
            branch = self._request("GET", "/git/ref/heads/" + BRANCH)
            if (not isinstance(branch, dict) or branch.get("ref") != "refs/heads/" + BRANCH
                    or not isinstance(branch.get("object"), dict)
                    or not re.fullmatch(r"[0-9a-f]{40,64}", str(branch["object"].get("sha", "")))):
                raise StateError("Existing publisher-state branch unverified")
            return None, {"schema_version": 1, "policy_id": POLICY_ID, "observations": []}
        try:
            sha = result["sha"]
            if not re.fullmatch(r"[0-9a-f]{40,64}", sha) or result.get("encoding") != "base64":
                raise ValueError
            raw = base64.b64decode("".join(result["content"].split()), validate=True)
            state = json.loads(raw.decode("utf-8"))
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise StateError("Existing measurement state could not be decoded") from None
        return sha, validate_state(state)

    def put(self, expected_sha, state):
        validate_state(state)
        payload = {"message": "Record read-only Threads performance observations",
                   "branch": BRANCH,
                   "content": base64.b64encode((json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii")}
        if expected_sha is not None:
            if not re.fullmatch(r"[0-9a-f]{40,64}", str(expected_sha)):
                raise StateError("Invalid conditional measurement state SHA")
            payload["sha"] = expected_sha
        result = self._request("PUT", "/contents/" + STATE_PATH, payload)
        content = result.get("content", {}) if isinstance(result, dict) else {}
        if not isinstance(content, dict) or not re.fullmatch(r"[0-9a-f]{40,64}", str(content.get("sha", ""))):
            raise RequestError(uncertain=True)
        return content["sha"]

    def append(self, additions, *, max_attempts=3):
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise StateError("Measurement CAS attempt limit invalid")
        # Validate additions independently before any write.
        validate_state({"schema_version": 1, "observations": additions})
        for attempt in range(max_attempts):
            sha, current = self.read()
            if contains_observations(current, additions):
                return current, {"status": "already_saved", "blob_sha": sha, "writes": attempt}
            try:
                merged = merge_observations(current, additions)
            except ValueError:
                raise StateError("Immutable observation merge conflict") from None
            uncertain = False
            try:
                self.put(sha, merged)
            except RequestError as error:
                if error.status in {409, 422} and not error.uncertain:
                    # Explicit conflict permits a new read/merge with the next SHA.
                    continue
                if not error.uncertain:
                    raise
                uncertain = True
            # Always verify persisted observation bytes; changed unrelated fields
            # or a later writer's additions remain untouched and are retained.
            observed_sha, observed = self.read()
            if contains_observations(observed, merged["observations"]):
                return observed, {"status": "verified_after_uncertain_write" if uncertain else "saved_verified",
                                  "blob_sha": observed_sha, "writes": attempt + 1}
            if uncertain:
                raise StateError("Measurement persistence unconfirmed; reread on the next run")
            raise StateError("Measurement read-back mismatch; preserve existing data")
        raise StateError("Measurement CAS remained conflicted; retry on the next run")


def run(history, *, backend, include_history=False, now=None, collector=None):
    """Read current state, collect once, append only new immutable observations."""
    now = now or datetime.now(timezone.utc)
    initial_sha, initial = backend.read()
    collection = collector or collect_due
    collected, result = collection(history, deepcopy(initial), now, include_history=include_history)
    validate_state(collected)
    old = {item["observation_id"]: item for item in initial["observations"]}
    for item in collected["observations"]:
        if item["observation_id"] in old and old[item["observation_id"]] != item:
            raise StateError("Collector attempted to change a preserved observation")
    if not contains_observations(collected, initial["observations"]):
        raise StateError("Collector omitted a preserved observation")
    additions = [item for item in collected["observations"] if item["observation_id"] not in old]
    if not additions:
        final, persistence = initial, {"status": "no_new_observations", "blob_sha": initial_sha, "writes": 0}
    else:
        try:
            final, persistence = backend.append(additions)
        except StateError as error:
            # Keep the concrete observations available in the workflow artifact.
            # The scheduled successor must read the remote state before deciding
            # whether anything still needs persistence; do not repeat collection.
            return {"state": collected, "collection_result": result,
                    "persistence": {"status": "unconfirmed", "reason": str(error)},
                    "summary": summarize(history, collected, now)}
    return {"state": final, "collection_result": result, "persistence": persistence,
            "summary": summarize(history, final, now)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", default="threads_posted.json")
    parser.add_argument("--output", required=True, help="Local audit artifact, even when state saving is unavailable")
    parser.add_argument("--include-history", action="store_true")
    args = parser.parse_args()
    result = None
    try:
        history = json.loads(Path(args.history).read_text(encoding="utf-8"))
        credential = os.getenv("THREADS_CLAIM_TOKEN") or os.getenv("GITHUB_TOKEN")
        backend = GitHubPerformanceState(credential)
        result = run(history, backend=backend, include_history=args.include_history)
    except StateError as error:
        result = {"collection_result": {"status": "blocked_before_persistence"},
                  "persistence": {"status": "unconfirmed", "reason": str(error)}}
    except Exception:
        result = {"collection_result": {"status": "unavailable"},
                  "persistence": {"status": "unconfirmed", "reason": "Measurement execution could not be verified"}}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Threads metrics collection:", result["collection_result"]["status"])
    print("Threads metrics state:", result["persistence"]["status"])
    if result["persistence"]["status"] == "unconfirmed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
