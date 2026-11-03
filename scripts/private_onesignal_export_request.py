"""Private OneSignal subscription export request helper.

Not called by any scheduled workflow. Never logs tokens, export URLs,
subscription IDs, or response bodies. Exports are read-only and asynchronous.
"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.private_onesignal_export_download import validate_export_url

ENDPOINT = "https://api.onesignal.com/players/csv_export"


def request_export(app_id, api_key, *, opener=urlopen):
    if not isinstance(app_id, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", app_id
    ):
        raise ValueError("Invalid OneSignal app ID")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("Missing private API key")
    request = Request(
        ENDPOINT + "?" + urlencode({"app_id": app_id}),
        data=b"{}",
        headers={"Authorization": "Key " + api_key,
                 "Content-Type": "application/json",
                 "Accept": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=15) as response:
            body = response.read(8193)
    except HTTPError as error:
        raise RuntimeError("OneSignal export request rejected (HTTP %d)" % error.code) from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("OneSignal export request network failure") from None
    if len(body) > 8192:
        raise ValueError("Oversized export response")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Invalid export response") from None
    if not isinstance(payload, dict):
        raise ValueError("Invalid export response")
    url = payload.get("csv_file_url")
    if not isinstance(url, str) or not url:
        raise ValueError("Export URL not ready; retry in a separate controlled check")
    return validate_export_url(url)
