"""Read one known OneSignal subscription with a private API key.

Never enumerates users or writes personal data. Not wired to scheduled sending.
"""
import json
import os
import uuid
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from scripts.onesignal_subscriber_validation import verified_subscriber


def lookup(subscription_id, *, opener=urlopen, timeout=12):
    if not isinstance(subscription_id, str) or not subscription_id:
        raise ValueError("Subscription id required")
    try:
        subscription_id = str(uuid.UUID(subscription_id))
    except (ValueError, AttributeError):
        raise ValueError("Invalid subscription id") from None
    app_id = os.environ.get("CP_ONESIGNAL_APP_ID", "")
    api_key = os.environ.get("CP_ONESIGNAL_REST_API_KEY", "")
    if not app_id or not api_key:
        raise ValueError("Missing OneSignal credentials")
    path = "/apps/" + quote(app_id, safe="") + "/subscriptions/" + quote(subscription_id, safe="") + "/user/identity"
    request = Request("https://api.onesignal.com" + path,
                      headers={"Authorization": "Key " + api_key,
                               "Accept": "application/json"}, method="GET")
    try:
        with opener(request, timeout=timeout) as response:
            result = json.loads(response.read(262144).decode("utf-8"))
    except HTTPError as error:
        if error.code == 404:
            return None  # Missing subscription/user: fail closed without logging identifiers.
        if error.code in (401, 403):
            raise RuntimeError("OneSignal authentication or permissions rejected") from None
        raise RuntimeError("OneSignal subscriber lookup HTTP error " + str(error.code)) from None
    except (URLError, OSError, TimeoutError):
        raise RuntimeError("OneSignal subscriber lookup network error") from None
    identity = result.get("identity", {}) if isinstance(result, dict) else {}
    user_id = identity.get("onesignal_id") if isinstance(identity, dict) else None
    if not isinstance(user_id, str) or not user_id:
        return None
    user_path = "/apps/" + quote(app_id, safe="") + "/users/by/onesignal_id/" + quote(user_id, safe="")
    user_request = Request("https://api.onesignal.com" + user_path,
                           headers={"Authorization": "Key " + api_key,
                                    "Accept": "application/json"}, method="GET")
    try:
        with opener(user_request, timeout=timeout) as response:
            user = json.loads(response.read(262144).decode("utf-8"))
    except HTTPError as error:
        if error.code == 404:
            return None
        if error.code in (401, 403):
            raise RuntimeError("OneSignal authentication or permissions rejected") from None
        raise RuntimeError("OneSignal user lookup HTTP error " + str(error.code)) from None
    except (URLError, OSError, TimeoutError):
        raise RuntimeError("OneSignal user lookup network error") from None
    return verified_subscriber(user, subscription_id)
