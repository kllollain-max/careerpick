"""Bounded retries for read-only requests; mutation requests are never retried."""
import email.utils
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def retry_delay(error, attempt):
    """Respect Retry-After; defer long waits to the next maintenance run."""
    if isinstance(error, urllib.error.HTTPError):
        if error.code not in (408, 429, 500, 502, 503, 504):
            return None
        value = error.headers.get('Retry-After') if error.headers else None
        if value:
            try:
                delay = max(0, int(value))
            except ValueError:
                try:
                    target = email.utils.parsedate_to_datetime(value)
                    delay = max(0, (target - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    return None
            return delay if delay <= 30 else None
    elif not isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return None
    return (2, 5)[min(attempt, 1)]


def read_response(request, timeout=20, *, opener=None, sleeper=None):
    if request.get_method() not in ('GET', 'HEAD'):
        raise ValueError('Only read-only requests may use bounded retries')
    opener = opener or urllib.request.urlopen
    sleeper = sleeper or time.sleep
    for attempt in range(3):
        try:
            return opener(request, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            delay = retry_delay(error, attempt)
            if attempt == 2 or delay is None:
                raise
            print('Read-only request temporarily unavailable; retry', attempt + 1, 'of 2')
            sleeper(delay)
