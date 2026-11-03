"""Safe OneSignal POST retry policy.

HTTP 429 is a documented rejection and is retried within a bounded budget.
5xx and response loss are *uncertain*, potentially accepted: quarantine rather
than replaying and risking duplicate notifications.
"""
import json
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

MAX_RETRIES = 3


class RejectedRequest(RuntimeError):
    """Definitive API rejection; no automatic task replay."""
    def __init__(self, message, reason="api_rejected"):
        super().__init__(message)
        self.reason = reason



def delay(headers, attempt, jitter=random.uniform):
    value = headers.get("Retry-After") if headers else None
    seconds = None
    if value:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            try:
                seconds = (parsedate_to_datetime(value).astimezone(timezone.utc)
                           - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                pass
    if seconds is None:
        seconds = min(30, 2 ** attempt)
    if seconds > 60:
        raise RejectedRequest("OneSignal Retry-After exceeds bounded wait budget", "rate_limited")
    return min(60.0, max(0.0, seconds) + jitter(0, 0.25))


def post(request, *, opener=urlopen, sleeper=time.sleep, retries=MAX_RETRIES, timeout=15):
    if type(retries) is not int or not 0 <= retries <= MAX_RETRIES:
        raise ValueError("Invalid retry budget")
    for attempt in range(retries + 1):
        try:
            with opener(request, timeout=timeout) as response:
                payload = json.loads(response.read(65536).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Invalid response; acceptance uncertain")
                return payload
        except HTTPError as error:
            if error.code == 429:
                if attempt < retries:
                    sleeper(delay(error.headers, attempt))
                    continue
                raise RejectedRequest("OneSignal HTTP 429 retry exhausted; keep reservation", "rate_limited") from None
            if error.code >= 500 or error.code == 408:
                raise RuntimeError("OneSignal server outcome uncertain; no blind retry (HTTP %d)" % error.code) from None
            raise
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("OneSignal network outcome uncertain; no blind retry") from None
    raise RuntimeError("OneSignal retry limit reached")
