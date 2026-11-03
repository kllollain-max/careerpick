"""Validate a OneSignal View User response without exporting private subscriber data.

Caller obtains the response through an authenticated, private API request.
No network access, credentials, or live sending in this module.
"""


def verified_subscriber(response, subscription_id):
    if not isinstance(response, dict) or not isinstance(subscription_id, str) or not subscription_id:
        return None
    subscriptions = response.get("subscriptions")
    if isinstance(subscriptions, dict):
        subscriptions = subscriptions.get("data")
    if not isinstance(subscriptions, list):
        return None
    matching = [item for item in subscriptions
                if isinstance(item, dict) and item.get("id") == subscription_id]
    if len(matching) != 1:
        return None
    subscription = matching[0]
    if subscription.get("enabled") is not True:
        return None
    kind = str(subscription.get("type", "")).lower()
    if kind not in ("chromepush", "firefoxpush", "safaripush", "edgepush"):
        return None
    properties = response.get("properties")
    tags = properties.get("tags") if isinstance(properties, dict) else None
    if not isinstance(tags, dict) or tags.get("cp_optin") != "yes":
        return None
    return {"subscription_id": subscription_id, "opted_in": True, "tags": tags}
