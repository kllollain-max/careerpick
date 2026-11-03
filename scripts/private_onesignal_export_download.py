"""Bounded private OneSignal CSV export download; never logs or stores URLs/IDs.

Caller must obtain the temporary export URL through an authorized private
OneSignal API request. This module does not initiate exports or send pushes.
"""
import gzip
import io
import os
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from scripts.private_subscription_export_parser import MAX_BYTES, parse_subscription_ids

MAX_COMPRESSED_BYTES = 2_000_000
ALLOWED_HOSTS = frozenset(("files.onesignal.com", "exports.onesignal.com"))


def export_host_category(host):
    """Coarse diagnosis only; never expose a signed URL or bucket name."""
    if host.endswith(".amazonaws.com"):
        return "aws-s3"
    if host.endswith(".cloudfront.net"):
        return "cloudfront"
    if host.endswith(".onesignal.com"):
        return "onesignal"
    if host.endswith(".onesignalcdn.com"):
        return "onesignal-cdn"
    return "other"


def validate_export_url(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("Invalid private export URL")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    extra_host = os.environ.get("CP_PRIVATE_EXPORT_HOST", "").strip().lower()
    if extra_host and (not extra_host.isascii() or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in extra_host)):
        raise ValueError("Invalid configured private export host")
    if (parts.scheme != "https" or not host or parts.username or parts.password
            or parts.port not in (None, 443) or not (host in (ALLOWED_HOSTS | ({extra_host} if extra_host else set()))
                    or host.endswith(".onesignal.com"))):
        raise ValueError("Private export URL host not allowed (provider category: %s); configure the exact verified host privately" % export_host_category(host))
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Private export redirect blocked")


def private_open(request, timeout=15):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


def read_export_ids(url, *, opener=private_open, sleeper=time.sleep, attempts=4):
    validate_export_url(url)
    request = Request(url, headers={"Accept": "application/gzip, text/csv"})
    # The default opener refuses redirects to prevent private URL exfiltration.
    if not isinstance(attempts, int) or not 1 <= attempts <= 4:
        raise ValueError("Invalid private export retry limit")
    for attempt in range(attempts):
        try:
            with opener(request, timeout=15) as response:
                if getattr(response, "status", 200) in (301, 302, 303, 307, 308):
                    raise ValueError("Export redirects are not permitted")
                blob = response.read(MAX_COMPRESSED_BYTES + 1)
            break
        except HTTPError as error:
            if error.code != 404:
                raise RuntimeError("Private export download rejected (HTTP %d)" % error.code) from None
            if attempt + 1 == attempts:
                raise RuntimeError("Private export not ready after bounded checks (HTTP 404)") from None
            sleeper(3 * (attempt + 1))
    if len(blob) > MAX_COMPRESSED_BYTES:
        raise ValueError("Private export exceeds compressed size cap")
    if blob[:2] == bytes((31, 139)):
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
            csv_bytes = stream.read(MAX_BYTES + 1)
    else:
        csv_bytes = blob
    if len(csv_bytes) > MAX_BYTES:
        raise ValueError("Private export exceeds decompressed size cap")
    return parse_subscription_ids(csv_bytes)
