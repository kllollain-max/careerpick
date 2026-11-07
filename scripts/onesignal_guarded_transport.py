"""Guarded OneSignal transport for an already validated per-subscriber plan.

This module never discovers subscribers or matches preferences. Callers must
supply an opted-in, server-verified subscription and a validated job.
Sending is disabled unless CP_ENABLE_LIVE_PUSH=1 and credentials exist.
"""
import json
import os
import re
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_URL = "https://api.onesignal.com/notifications"


def build_payload(job, subscription_id, app_id, *, test=False):
    if not isinstance(job, dict) or not str(job.get("id") or "").strip():
        raise ValueError("Job id is required")
    if not str(job.get("title") or "").strip():
        raise ValueError("Job title is required")
    if not isinstance(subscription_id, str) or not subscription_id.strip():
        raise ValueError("Subscription id is required")
    if not isinstance(app_id, str) or not app_id.strip():
        raise ValueError("OneSignal app id is required")
    # Link only canonical source IDs to first-party pages or supported anchors.
    # Never trust a user-controlled URL supplied in job data.
    job_id = str(job["id"]).strip()
    target = "https://kllollain-max.github.io/careerpick/"
    if re.fullmatch(r"a[0-9]+", job_id):
        target += "jobs/" + job_id + ".html"
    elif re.fullmatch(r"cleaneye-[0-9]+", job_id):
        target += "#job=" + job_id
    # One logical job/subscriber delivery keeps its UUID across process retries.
    # OneSignal accepts RFC 9562 UUIDs and retains notification keys for 30 days:
    # https://documentation.onesignal.com/reference/idempotent-notification-requests
    # The permanent private ledger and uncertain-send protections still apply.
    operation = json.dumps(["careerpick:push:v1", app_id, job_id, subscription_id, bool(test)],
                           ensure_ascii=False, separators=(",", ":"))
    idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_URL, operation))
    from scripts.detect_new_job_alerts import parse_due
    due = parse_due(job.get("due"))
    # Never invent a closing time for a date-only official deadline.
    # The collector may normalize date-only deadlines to 23:59 internally.
    # Display the closing DATE only, never that synthesized closing time.
    deadline = due.strftime("%Y-%m-%d") if due else "원문 확인"
    suffix = " · 마감 " + deadline
    message = (str(job.get("org") or "공공기관") + " · " + str(job["title"]))[:160-len(suffix)] + suffix
    return {
        "app_id": app_id,
        "target_channel": "push",
        "include_subscription_ids": [subscription_id],
        "idempotency_key": idempotency_key,
        "headings": {"en": "커리어픽 채용 알림 테스트" if test else "커리어픽 신규 채용공고",
                     "ko": "커리어픽 채용 알림 테스트" if test else "커리어픽 신규 채용공고"},
        "contents": {"en": message, "ko": message},
        "url": target,
    }


def send(job, subscription_id, *, verified_opt_in=False, live=False, timeout=15, test=False):
    """Send only after the caller verified current consent and matching tags.

    Returns a non-sensitive response; never logs API keys or subscription ids.
    Does not write the delivery ledger: caller must record only confirmed sends.
    """
    if verified_opt_in is not True:
        raise ValueError("Verified current opt-in is required")
    app_id = os.environ.get("CP_ONESIGNAL_APP_ID", "")
    payload = build_payload(job, subscription_id, app_id, test=test)
    if not live or os.environ.get("CP_ENABLE_LIVE_PUSH") != "1":
        return {"sent": False, "reason": "live sending disabled"}
    key = os.environ.get("CP_ONESIGNAL_REST_API_KEY", "")
    if not key:
        raise ValueError("Missing private OneSignal REST API key")
    request = Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Key " + key, "Content-Type": "application/json"},
        method="POST",
    )
    from scripts.onesignal_safe_retry import post, RejectedRequest
    try:
        result = post(request, opener=urlopen, timeout=timeout)
    except HTTPError as error:
        fields = []
        try:
            body = json.loads(error.read(8192).decode("utf-8"))
            if isinstance(body, dict):
                details = body.get("errors")
                if isinstance(details, list):
                    for item in details:
                        if isinstance(item, dict):
                            fields.extend(k for k in item if k in
                                          {"include_subscription_ids", "target_channel", "app_id",
                                           "contents", "headings", "url"})
                fields.extend(k for k in body if k in
                              {"include_subscription_ids", "target_channel", "app_id",
                               "contents", "headings", "url"})
        except (ValueError, UnicodeDecodeError, OSError):
            pass
        detail = ", ".join(sorted(set(fields))) if fields else "validation details withheld"
        raise RejectedRequest(
            "OneSignal push API rejected request (HTTP %d; fields: %s); "
            "delivery reservation may remain pending" % (error.code, detail),
            reason="http_%d" % error.code
        ) from None
    # A notification id is not proof of device receipt. Zero reported
    # recipients must not be recorded as a successful send in the ledger.
    recipients = result.get("recipients")
    accepted = (
        bool(result.get("id"))
        and not result.get("errors")
        and not (type(recipients) is int and recipients == 0)
    )
    return {"sent": accepted,
            "notification_id": result.get("id") if accepted else None,
            "provider_message_id": result.get("id"),
            "outcome": "accepted" if accepted else (
                "failed" if type(recipients) is int and recipients == 0 else "uncertain"),
            "reason": "api_accepted" if accepted else (
                "zero_recipients" if type(recipients) is int and recipients == 0 else "unconfirmed_response")}


if __name__ == "__main__":
    raise SystemExit("Use from a validated alert worker; no standalone broadcasting.")
