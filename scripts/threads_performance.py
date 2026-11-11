#!/usr/bin/env python3
"""Read-only Threads measurement planning, collection and descriptive comparison.

This module never publishes, changes a schedule or writes a remote ledger. The
caller owns the existing conditional-save contract. Collection is opt-in and
uses the existing account guard/token; unavailable insight access is recorded,
not treated as zero or as a reason to stop the publisher.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from statistics import median
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.threads_metrics_preview import METRICS, collect_post_insights

POLICY_ID = "careerpick-threads-reach-v1-20261109"
KST = ZoneInfo("Asia/Seoul")
WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7)}
V5_WINDOWS = {"24h": timedelta(hours=24), "72h": timedelta(hours=72)}
# An explicit observation tolerance, not a statistical significance threshold.
# Later observations remain useful cumulative snapshots but are not comparable
# milestone measurements. Report elapsed seconds for every observation.
COMPARABLE_DELAY = timedelta(hours=1)
TERMINAL = {"captured", "not_provided", "permission_denied", "unsupported_or_rejected"}


def moment(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timezone-aware time required")
    return result.astimezone(timezone.utc)


def _review(record):
    review = record.get("writer_review")
    if not isinstance(review, dict):
        review = record.get("writer_entry", {}).get("writer", {}).get("review", {})
    return review if isinstance(review, dict) else {}


def _text_sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_public_main(post_id, token, *, opener=None):
    """Read the actual main object; never infer its text from a publish receipt."""
    if not isinstance(post_id, str) or not post_id.isdigit() or not token:
        raise ValueError("Valid main post ID and existing token required")
    query = urllib.parse.urlencode({"fields": "id,text,is_reply"})
    request = urllib.request.Request(
        "https://graph.threads.net/v1.0/" + post_id + "?" + query, method="GET",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    from scripts.threads_http import read_response
    with read_response(request, timeout=15, opener=opener) as response:
        return json.load(response)


def public_main_evidence(record, payload, checked_at):
    """Retain a read-only public-text check without changing the publish ledger."""
    expected = record.get("text")
    evidence = {"status": "unverified", "post_id": str(record["threads_post_id"]),
                "checked_at": moment(checked_at).isoformat(), "reason": None,
                "expected_text_sha256": _text_sha256(expected) if isinstance(expected, str) else None,
                "actual_text_sha256": None, "actual_first_sentence": None}
    if not isinstance(payload, dict) or str(payload.get("id", "")) != evidence["post_id"]:
        evidence["reason"] = "public_main_id_mismatch"
    elif payload.get("is_reply") is not False:
        evidence["reason"] = "public_main_type_unverified"
    elif not isinstance(payload.get("text"), str) or not payload["text"]:
        evidence["reason"] = "public_main_text_unavailable"
    else:
        evidence["actual_text_sha256"] = _text_sha256(payload["text"])
        evidence["actual_first_sentence"] = payload["text"].split("\n", 1)[0]
        if payload["text"] != expected:
            evidence.update(status="mismatch", reason="public_main_text_mismatch")
        else:
            evidence.update(status="verified", is_reply=False)
    return evidence


def hook_status(record, public_verification=None):
    """A/B membership requires actual main GET evidence, not a saved draft/ID."""
    editorial = _review(record).get("reach_editorial", {})
    actual = str(record.get("text", "")).split("\n", 1)[0]
    reason = None
    if not isinstance(editorial, dict) or editorial.get("policy_id") != POLICY_ID:
        reason = "legacy_or_missing_policy"
    elif editorial.get("hook_type") not in {"A", "B"}:
        reason = "missing_hook_type"
    elif editorial.get("experiment_eligible") is not True:
        reason = "editorial_comparison_excluded"
    elif editorial.get("first_sentence") != actual or not actual:
        reason = "final_first_sentence_mismatch"
    elif record.get("request_status") != "confirmed":
        reason = "main_receipt_unconfirmed"
    elif not isinstance(public_verification, dict) or public_verification.get("status") != "verified":
        reason = (public_verification.get("reason") or "public_main_unverified"
                  if isinstance(public_verification, dict) else "public_main_unverified")
    elif (public_verification.get("post_id") != str(record.get("threads_post_id"))
          or public_verification.get("is_reply") is not False
          or public_verification.get("expected_text_sha256") != _text_sha256(record["text"])
          or public_verification.get("actual_text_sha256") != _text_sha256(record["text"])
          or public_verification.get("actual_first_sentence") != actual):
        reason = "public_main_evidence_mismatch"
    else:
        try:
            if moment(public_verification.get("checked_at")) < moment(record["published_at"]):
                reason = "public_main_check_time_invalid"
        except (TypeError, ValueError):
            reason = "public_main_check_time_invalid"
    return {"eligible": reason is None, "reason": reason,
            "hook_type": editorial.get("hook_type") if isinstance(editorial, dict) else None,
            "final_first_sentence": actual}


def publication_metadata(record, public_verification=None):
    """Keep confounders and their unknowns; do not infer popularity or breadth."""
    review = _review(record)
    editorial = review.get("reach_editorial", {})
    context = editorial.get("comparison_context", {}) if isinstance(editorial, dict) else {}
    if not isinstance(context, dict):
        context = {}
    facts = record.get("writer_entry", {}).get("image_job") or record.get("image_job") or {}
    if not isinstance(facts, dict):
        facts = {}
    published = moment(record["published_at"])
    period = review.get("application_period", {})
    deadline_seconds = None
    if isinstance(period, dict) and period.get("end") and period.get("date_only") is False:
        try:
            deadline_seconds = (moment(period["end"]) - published).total_seconds()
        except (ValueError, TypeError):
            pass
    count = facts.get("count")
    if type(count) is not int or count < 1:
        count = None
    slot = record.get("scheduled_at")
    try:
        slot_hour = moment(slot).astimezone(KST).hour
    except (TypeError, ValueError):
        slot_hour = None
    return {
        "post_id": str(record["threads_post_id"]), "notice_id": record.get("job_id"),
        "published_at": published.isoformat(), "scheduled_at": slot,
        "slot_hour_kst": slot_hour, "actual_hour_kst": published.astimezone(KST).hour,
        "body_chars": len(str(record.get("text", ""))),
        "first_sentence": str(record.get("text", "")).split("\n",1)[0],
        "editorial_v5": deepcopy(review.get("v5")),
        "post_attributed_profile_visits": None, "post_attributed_follow_increase": None, "post_attributed_link_clicks": None,
        "format_id": record.get("format_id"), "media": "IMAGE" if record.get("image_url") else "TEXT",
        "org": facts.get("org"), "job": facts.get("title"), "employment": facts.get("employment"),
        "recruitment_unit_count": count, "location": facts.get("location"),
        "audience_scope": context.get("audience_scope") if context.get("audience_scope") is not None else context.get("audience_breadth"),
        "audience_breadth": context.get("audience_breadth"),
        "notice_type": context.get("notice_type"),
        "comparison_context": deepcopy(context),
        "institution_interest": context.get("institution_interest"),
        "interest_evidence": context.get("interest_evidence"),
        "comparison_group": context.get("comparison_group"),
        "comparison_group_evidence": context.get("comparison_group_evidence"),
        "deadline": period.get("end") if isinstance(period, dict) else None,
        "deadline_date_only": period.get("date_only") if isinstance(period, dict) else None,
        "deadline_distance_seconds": deadline_seconds,
        "detail_reply_status": record.get("reply_status"),
        "detail_reply_id": record.get("reply_post_id"),
        "public_verification": deepcopy(public_verification),
        "hook": hook_status(record, public_verification),
    }


def recent_publications(history, now, *, lookback_days=28, include_history=True):
    now = moment(now)
    if type(lookback_days) is not int or not 1 <= lookback_days <= 28:
        raise ValueError("Lookback must be between 1 and 28 days")
    records, seen, excluded = [], set(), Counter()
    for record in history.get("records", []):
        if not isinstance(record, dict) or record.get("status") != "published":
            excluded["not_published"] += 1
            continue
        post_id = str(record.get("threads_post_id", ""))
        if not post_id.isdigit() or post_id in seen:
            excluded["missing_or_duplicate_main_id"] += 1
            continue
        try:
            published = moment(record.get("published_at"))
        except (TypeError, ValueError):
            excluded["published_time_unknown"] += 1
            continue
        if not now - timedelta(days=lookback_days) <= published <= now:
            excluded["outside_window"] += 1
            continue
        if (not include_history and _review(record).get("reach_editorial", {}).get("policy_id") != POLICY_ID
                and _review(record).get("v5", {}).get("policy_id") != "careerpick-threads-v5-20261111"):
            excluded["legacy_policy"] += 1
            continue
        seen.add(post_id)
        records.append(record)
    records.sort(key=lambda item: moment(item["published_at"]))
    return records, dict(excluded)


def measurement_plan(history, state, now, *, include_history=False):
    """Plan only main-ID observations. This does not authorize another post."""
    now = moment(now)
    records, exclusions = recent_publications(history, now, include_history=include_history)
    observations = state.get("observations", [])
    items = []
    for record in records:
        metadata = publication_metadata(record)
        published = moment(record["published_at"])
        windows = V5_WINDOWS if _review(record).get("v5", {}).get("policy_id") == "careerpick-threads-v5-20261111" else WINDOWS
        for label, age in windows.items():
            due = published + age
            previous = [o for o in observations if o.get("post_id") == metadata["post_id"]
                        and o.get("window") == label]
            done = next((o for o in previous if o.get("status") in TERMINAL), None)
            latest = max((moment(o["captured_at"]) for o in previous), default=None)
            status = "recorded" if done else "pending" if now < due else "due"
            if status == "due" and latest and now - latest < timedelta(hours=1):
                status = "retry_deferred"
            items.append({"post_id": metadata["post_id"], "window": label,
                          "due_at": due.isoformat(), "status": status,
                          "elapsed_seconds": (now - published).total_seconds(),
                          "overdue_seconds": max(0, (now - due).total_seconds()),
                          "within_comparison_window": due <= now <= due + COMPARABLE_DELAY,
                          "metadata": metadata})
    return {"schema_version": 1, "policy_id": POLICY_ID, "planned_at": now.isoformat(),
            "lookback_days": 28, "include_history": include_history,
            "main_posts": len(records), "excluded": exclusions, "items": items}


def observation(item, *, captured_at, metrics=None, status="captured", error_code=None):
    captured = moment(captured_at)
    published = moment(item["metadata"]["published_at"])
    due = moment(item["due_at"])
    if captured < due:
        raise ValueError("Observation precedes its milestone")
    if status not in {"captured", "not_provided", "permission_denied", "unsupported_or_rejected",
                      "collection_failed", "access_unavailable", "account_unverified"}:
        raise ValueError("Unknown observation status")
    values = {key: None for key in METRICS}
    if status == "captured":
        for key, value in (metrics or {}).items():
            if key in values and type(value) is int and value >= 0:
                values[key] = value
        if all(value is None for value in values.values()):
            status = "not_provided"
    delay = (captured - due).total_seconds()
    key = "|".join((item["post_id"], item["window"], captured.isoformat()))
    result = {
        "observation_id": hashlib.sha256(key.encode()).hexdigest(),
        "post_id": item["post_id"], "window": item["window"],
        "captured_at": captured.isoformat(), "published_at": published.isoformat(),
        "elapsed_seconds": (captured - published).total_seconds(), "delay_seconds": delay,
        "timing": "within_one_hour" if captured <= due + COMPARABLE_DELAY else "late_cumulative",
        "comparable_milestone": status == "captured" and captured <= due + COMPARABLE_DELAY,
        "status": status, "error_code": error_code, "metrics": values,
        "metric_status": {key: "observed" if value is not None else
                          "not_provided" if status in {"captured", "not_provided"} else status
                          for key, value in values.items()},
        # An aggregate replies metric is not an author-filtered reader count.
        # Do not subtract one and assume every remaining reply is from a reader.
        "reader_replies": None, "reader_replies_status": "author_separation_unverified",
        "automated_detail_reply_id": item["metadata"].get("detail_reply_id"),
        "site_visits": None, "profile_link_clicks": None, "applications": None,
        "public_verification": deepcopy(item["metadata"].get("public_verification")),
        "metadata": deepcopy(item["metadata"]),
    }
    return result


def merge_observations(state, additions):
    """Append-only merge for the caller's subsequent blob-SHA conditional write."""
    result = deepcopy(state)
    if result.get("schema_version", 1) != 1:
        raise ValueError("Unsupported performance state schema")
    result.setdefault("schema_version", 1)
    result.setdefault("policy_id", POLICY_ID)
    existing = result.setdefault("observations", [])
    by_id = {item["observation_id"]: item for item in existing}
    for item in additions:
        key = item["observation_id"]
        if key in by_id:
            if by_id[key] != item:
                raise ValueError("Observation identity collision; reread state")
            continue
        existing.append(deepcopy(item))
        by_id[key] = item
    return result


def collect_due(history, state, now=None, *, token=None, include_history=False,
                limit=8, account_guard=None, collector=None, public_reader=None, clock=None):
    """Only GETs, with injectable seams for tests; failures become observations."""
    if type(limit) is not int or not 1 <= limit <= 16:
        raise ValueError("Collection limit must be 1 to 16 main posts")
    now = moment(now or datetime.now(timezone.utc))
    clock = clock or (lambda: datetime.now(timezone.utc))
    plan = measurement_plan(history, state, now, include_history=include_history)
    due = [item for item in plan["items"] if item["status"] == "due"]
    due.sort(key=lambda item: (not item["within_comparison_window"], item["due_at"]))
    # Multiple due windows for an old main share one actual API snapshot.
    post_ids = list(dict.fromkeys(item["post_id"] for item in due))[:limit]
    selected = [item for item in due if item["post_id"] in post_ids]
    if not selected:
        return merge_observations(state, []), {"status": "no_due_observations", "api_calls": 0}
    access_status = None
    token = token or os.getenv("THREADS_ACCESS_TOKEN")
    if not token:
        access_status = "access_unavailable"
    else:
        if account_guard is None:
            from scripts.threads_auto import verify_account
            account_guard = verify_account
        try:
            account_guard(token)
        except Exception:
            # Never surface a request/credential-bearing exception string.
            access_status = "account_unverified"
    additions, calls, public_calls = [], 0, 0
    collector = collector or collect_post_insights
    public_reader = public_reader or read_public_main
    records, _ = recent_publications(history, now, include_history=include_history)
    by_id = {str(record["threads_post_id"]): record for record in records}
    for post_id in post_ids:
        status, metrics, error_code = access_status or "captured", None, None
        verification = {"status": "unverified", "post_id": post_id,
                        "checked_at": moment(clock()).isoformat(),
                        "reason": access_status or "public_main_read_failed"}
        if not access_status:
            public_calls += 1
            try:
                actual_main = public_reader(post_id, token)
                verification = public_main_evidence(by_id[post_id], actual_main, clock())
            except Exception:
                # Public-text verification is independent of insight access.
                # Preserve available measurements but never admit an unverified
                # main to A/B comparisons or expose credential-bearing errors.
                pass
            calls += 1
            try:
                payload = collector(post_id, token)
                metrics = payload.get("metrics")
            except urllib.error.HTTPError as error:
                error_code = error.code
                status = ("permission_denied" if error.code in {401, 403} else
                          "unsupported_or_rejected" if error.code == 400 else "collection_failed")
            except Exception:
                status = "collection_failed"
        captured = moment(clock())
        for item in selected:
            if item["post_id"] == post_id:
                checked_item = deepcopy(item)
                checked_item["metadata"] = publication_metadata(by_id[post_id], verification)
                additions.append(observation(checked_item, captured_at=captured, metrics=metrics,
                                             status=status, error_code=error_code))
    return merge_observations(state, additions), {
        "status": "measured" if any(o["status"] == "captured" for o in additions) else "unmeasured",
        "api_calls": calls + public_calls, "insight_api_calls": calls,
        "public_verification_calls": public_calls, "main_posts_attempted": len(post_ids),
        "new_observations": len(additions), "statuses": dict(Counter(o["status"] for o in additions)),
        "next_condition": "Existing scheduled maintenance; restore authorized insight access if unavailable",
    }


def summarize(history, state, now):
    """Descriptive counts and medians; never choose a winning hook automatically."""
    from scripts.threads_v5 import performance_summary
    now = moment(now)
    records, exclusions = recent_publications(history, now, include_history=True)
    all_records = {str(r.get("threads_post_id")): r for r in history.get("records", [])
                   if isinstance(r, dict) and r.get("status") == "published"}
    def verification_for(item):
        proof = item.get("public_verification")
        if proof is None:
            proof = item.get("metadata", {}).get("public_verification")
        try:
            if not isinstance(proof, dict) or moment(proof.get("checked_at")) > moment(item["captured_at"]):
                return None
        except (KeyError, TypeError, ValueError):
            return None
        return proof
    verified, latest_checks = {}, {}
    observations = sorted(state.get("observations", []), key=lambda x: x["captured_at"])
    for item in observations:
        post_id = item.get("post_id")
        record = all_records.get(post_id)
        if not record or moment(item["captured_at"]) > now:
            continue
        proof = verification_for(item)
        latest_checks[post_id] = proof
        if hook_status(record, proof)["eligible"]:
            verified.setdefault(post_id, proof)
    metadata = {str(r["threads_post_id"]): publication_metadata(r, latest_checks.get(str(r["threads_post_id"])))
                for r in records}
    experiment_records = [publication_metadata(all_records[post_id], proof)
                          for post_id, proof in verified.items() if post_id in metadata]
    # The 28-day reporting window must never restart the original experiment.
    # Derive its anchor from preserved complete history with actual main-GET
    # evidence. A bare saved timestamp or confirmed publish ID cannot prove that
    # an experimental first sentence was the text actually made public.
    anchors = []
    for post_id in verified:
        record = all_records[post_id]
        if hook_status(record, verified[post_id])["eligible"]:
            try:
                stamp = moment(record["published_at"])
                if stamp <= now:
                    anchors.append(stamp)
            except (KeyError, TypeError, ValueError):
                pass
    start = min(anchors, default=None)
    collisions = defaultdict(set)
    for m in experiment_records:
        collisions[m["hook"]["final_first_sentence"]].add(m["hook"]["hook_type"])
    invalid_hooks = {sentence for sentence, types in collisions.items() if len(types) > 1}
    groups = {label: {arm: [] for arm in ("A", "B")} for label in WINDOWS}
    reasons = Counter()
    seen = set()
    for item in observations:
        m = metadata.get(item.get("post_id"))
        if not m:
            reasons["legacy_or_invalid_final_hook"] += 1
            continue
        hook = hook_status(all_records[item["post_id"]], verification_for(item))
        if not hook["eligible"]:
            reasons[hook["reason"] or "public_main_unverified"] += 1
            continue
        if moment(item["captured_at"]) > now:
            reasons["future_observation"] += 1
            continue
        if hook["final_first_sentence"] in invalid_hooks:
            reasons["identical_final_hook_across_arms"] += 1
            continue
        if item.get("window") not in WINDOWS or item.get("comparable_milestone") is not True:
            reasons["late_or_unavailable"] += 1
            continue
        if type(item.get("metrics", {}).get("views")) is not int:
            reasons["views_unavailable"] += 1
            continue
        unique = (item["post_id"], item["window"])
        if unique in seen:
            continue
        seen.add(unique)
        groups[item["window"]][hook["hook_type"]].append(item)
    def stats(items):
        views = [o["metrics"]["views"] for o in items]
        strata = Counter((o["metadata"].get("slot_hour_kst"), o["metadata"].get("media"),
                          o["metadata"].get("employment"), o["metadata"].get("location")) for o in items)
        return {"count": len(items), "views_median": median(views) if views else None,
                "views_max": max(views) if views else None,
                "views_median_without_max": median(sorted(views)[:-1]) if len(views) > 1 else None,
                "reaction_summaries": {key: {"observed_posts": sum(o["metrics"].get(key) is not None for o in items),
                    "total": sum(o["metrics"][key] for o in items if o["metrics"].get(key) is not None)
                    if any(o["metrics"].get(key) is not None for o in items) else None}
                    for key in ("likes", "reposts", "quotes")},
                "reader_replies": None, "reader_replies_status": "author_separation_unverified",
                "strata": [{"slot_hour_kst": k[0], "media": k[1], "employment": k[2],
                            "location": k[3], "count": n} for k, n in sorted(strata.items(), key=lambda x: str(x[0]))],
                "post_ids": [o["post_id"] for o in items]}
    output_groups = {label: {arm: stats(items) for arm, items in arms.items()} for label, arms in groups.items()}
    matched = defaultdict(lambda: {"A": [], "B": []})
    for arm, items in groups["24h"].items():
        for item in items:
            context = item["metadata"]
            if context.get("comparison_group") and context.get("comparison_group_evidence"):
                matched[str(context["comparison_group"])][arm].append(item)
    matched = {group: arms for group, arms in matched.items() if arms["A"] and arms["B"]}
    matched_counts = {arm: sum(len(arms[arm]) for arms in matched.values()) for arm in ("A", "B")}
    target_met = all(matched_counts[arm] >= 8 for arm in ("A", "B"))
    checkpoints = []
    for day in (7, 14):
        due = start + timedelta(days=day) if start else None
        checkpoints.append({"day": day, "due_at": due.isoformat() if due else None,
                            "status": "due" if due and now >= due else "pending" if due else "not_started"})
    plan = measurement_plan(history, state, now, include_history=True)
    return {
        "v5_performance": performance_summary(history, state, now),
        "v5_observation_windows": ["24h", "72h"],
        "v5_comparison_status": "separate_cohort_not_legacy_AB; human_review_until_sufficient_verified_samples",
        "schema_version": 1, "policy_id": POLICY_ID, "as_of": now.isoformat(),
        "requested_window_start": (now - timedelta(days=28)).isoformat(),
        "observed_first_publication": min((m["published_at"] for m in metadata.values()), default=None),
        "observed_last_publication": max((m["published_at"] for m in metadata.values()), default=None),
        "normal_main_publications": len(records),
        "confirmed_detail_replies": sum(m["detail_reply_status"] == "confirmed" and bool(m["detail_reply_id"]) for m in metadata.values()),
        "experiment_start": start.isoformat() if start else None, "groups": output_groups,
        "matched_24h_groups": {group: {arm: stats(items) for arm, items in arms.items()}
                               for group, arms in matched.items()},
        "matched_24h_counts": matched_counts,
        "initial_8_per_arm_target_met": target_met, "statistical_significance_claim": False,
        "checkpoints": checkpoints,
        "seven_day_pending_posts": len({p["post_id"] for p in plan["items"] if p["window"] == "7d" and p["status"] == "pending"}),
        "collection_statuses": dict(Counter(o.get("status", "unknown") for o in state.get("observations", []))),
        "excluded_observations": dict(reasons), "excluded_history": exclusions,
        "unmeasured": ["author-separated reader replies", "post-attributed profile clicks", "completed applications"],
        "decision": "review_comparable_groups" if target_met else "extend_until_comparable_samples_available",
        "interpretation": "Descriptive only. Review institution interest, audience, unit count, job, employment, region and deadline; slot and writer format are coupled. No automatic winner or causal inference.",
        "publication_metadata": list(metadata.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", default="threads_posted.json")
    parser.add_argument("--state", required=True, help="Local copy of conditionally saved measurement state")
    parser.add_argument("--output", required=True, help="Local result JSON; remote CAS is the caller's responsibility")
    parser.add_argument("--mode", choices=("plan", "collect", "summarize"), default="plan")
    parser.add_argument("--include-history", action="store_true", help="Read-only historical baseline, never retroactive A/B")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"schema_version": 1, "observations": []}
    now = datetime.now(timezone.utc)
    if args.mode == "collect":
        state, result = collect_due(history, state, now, include_history=args.include_history, limit=args.limit)
        output = {"state": state, "collection_result": result, "summary": summarize(history, state, now)}
    elif args.mode == "summarize":
        output = summarize(history, state, now)
    else:
        output = measurement_plan(history, state, now, include_history=args.include_history)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Read-only performance result saved; no publication or schedule change")


if __name__ == "__main__":
    main()
