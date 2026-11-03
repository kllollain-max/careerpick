"""Read-only OneSignal subscription readiness check. Never sends notifications."""
import json
import os
from pathlib import Path

from scripts.onesignal_known_subscriber import lookup
from scripts.alert_preference_matcher import packed_preferences


def main():
    config = Path("push-config.js").read_text(encoding="utf-8")
    app_id = os.environ.get("CP_ONESIGNAL_APP_ID", "").strip()
    subscription_id = os.environ.get("CP_TEST_SUBSCRIPTION_ID", "").strip()
    if not app_id or app_id not in config:
        raise SystemExit("Public OneSignal app ID does not match configured app")
    if not os.environ.get("CP_ONESIGNAL_REST_API_KEY"):
        raise SystemExit("Missing private OneSignal API key")
    if not subscription_id:
        raise SystemExit("Missing test subscription ID")
    verified = lookup(subscription_id)
    if not verified:
        raise SystemExit("Test subscription not verified as opted in; no send attempted")
    if packed_preferences(verified["tags"]) is None:
        raise SystemExit("Test subscription lacks valid v4 preference tags")
    print(json.dumps({"subscription_verified": True, "preference_schema": 4, "sent": False}))


if __name__ == "__main__":
    main()
