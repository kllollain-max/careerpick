"""Read-only adapter for data.go.kr dataset 15125273.

The caller supplies this service's credential; this module never reads an
environment variable, logs a key/response, follows redirects, or writes files.
Raw notice fields (including detail files/steps) are retained after validation.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://apis.data.go.kr/1051000/recruitment"
PER_PAGE = 100
MAX_PAGES = 10
TIMEOUT = 30
MAX_RESPONSE_BYTES = 16 * 1024 * 1024

_SAFE_CODES = {
    "missing_key", "invalid_key", "invalid_page", "invalid_notice_id",
    "redirect_rejected", "transport_failed", "response_too_large",
    "invalid_json", "invalid_envelope", "unexpected_envelope_fields",
    "api_response_error", "invalid_total_count", "invalid_list_shape",
    "invalid_detail_shape", "invalid_item_wrapper", "detail_identity_mismatch",
    "too_many_page_rows", "duplicate_notice_id", "empty_list",
    "count_changed", "incomplete_page", "incomplete_collection",
    "excess_records", "page_limit_exceeded", "internal_error",
}
_SAFE_CODES.update("api_result_" + str(code) for code in (1, 2, 3, 5, 6, 7, 8, 10, 11))
_SAFE_CODES.update("http_status_" + str(code) for code in range(400, 600))
_ENVELOPE_FIELDS = {"resultCode", "resultMsg", "totalCount", "result", "pageNo", "numOfRows"}
_GATEWAY_TOKENS = {
    "APPLICATION_ERROR": "01", "HTTP_ERROR": "04", "SERVICETIMEOUT_ERROR": "05",
    "INVALID_REQUEST_PARAMETER_ERROR": "10", "NO_OPENAPI_SERVICE_ERROR": "12",
    "SERVICE_KEY_IS_NULL": "20", "PERMISSION_DENIED": "20",
    "SERVICE_ACCESS_DENIED_ERROR": "20",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "22",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR": "23",
    "BLACKLIST_IP_ACCESS_ERROR": "29", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "30",
    "DEADLINE_HAS_EXPIRED_ERROR": "31",
}
_SAFE_CODES.update("gateway_" + token for token in _GATEWAY_TOKENS)


class APIError(RuntimeError):
    """Only fixed, non-sensitive diagnostic codes may escape the adapter."""

    def __init__(self, safe_code):
        self.safe_code = safe_code if safe_code in _SAFE_CODES else "internal_error"
        super().__init__(self.safe_code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise APIError("redirect_rejected") from None


def _notice_id(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise APIError("invalid_notice_id")
    text = str(value)
    if not re.fullmatch(r"[0-9]+", text) or int(text) <= 0:
        raise APIError("invalid_notice_id")
    return str(int(text))


def _count(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise APIError("invalid_total_count")
    if not re.fullmatch(r"[0-9]+", str(value)):
        raise APIError("invalid_total_count")
    return int(value)


def _item(value):
    """Accept the item wrappers shown by the official JSON/XML schema."""
    if isinstance(value, dict) and "item" in value:
        if set(value) != {"item"}:
            raise APIError("invalid_item_wrapper")
        return value["item"]
    return value


class Client:
    def __init__(self, key):
        if not isinstance(key, str):
            raise APIError("invalid_key")
        if not key.strip():
            raise APIError("missing_key")
        try:
            # unquote_plus would corrupt a literal '+' in a decoded key.
            self._key = urllib.parse.unquote(key.strip(), errors="strict")
        except (ValueError, UnicodeError):
            raise APIError("invalid_key") from None
        self.request_counts = {"list": 0, "detail": 0}
        self.success_counts = {"list": 0, "detail": 0}
        self.last_http_error = None
        self.last_response_diagnostic = None
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _request(self, operation, params):
        query = urllib.parse.urlencode({
            "serviceKey": self._key, "resultType": "json", **params,
        })
        request = urllib.request.Request(
            BASE_URL + "/" + operation + "?" + query,
            method="GET", headers={"User-Agent": "CareerPick", "Accept": "application/json"},
        )
        self.request_counts[operation] += 1
        try:
            with self._opener.open(request, timeout=TIMEOUT) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except APIError:
            raise
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                raise APIError("redirect_rejected") from None
            diagnostic = {"http_status": error.code, "gateway_token": None, "gateway_code": None}
            token = None
            try:
                body = error.read(16 * 1024)
                message = body.decode("utf-8", errors="replace")
                # Only exact tokens listed in the portal's official error guide can escape.
                token = next((t for t in _GATEWAY_TOKENS
                              if re.search(r"(?<![A-Z_])" + re.escape(t) + r"(?![A-Z_])", message)), None)
                diagnostic["body_bytes_read"] = len(body)
                diagnostic["body_format"] = (
                    "json" if message.lstrip().startswith(("{", "[")) else
                    "markup" if message.lstrip().startswith("<") else "text")
                if token:
                    diagnostic.update(gateway_token=token, gateway_code=_GATEWAY_TOKENS[token])
            except Exception:
                diagnostic["body_unavailable"] = True
            self.last_http_error = diagnostic
            if token:
                raise APIError("gateway_" + token) from None
            raise APIError("http_status_" + str(error.code)) from None
        except Exception:
            # Transport exceptions often contain the full credential-bearing URL.
            raise APIError("transport_failed") from None
        if len(body) > MAX_RESPONSE_BYTES:
            raise APIError("response_too_large")
        try:
            payload = json.loads(body.decode("utf-8-sig"))
        except (ValueError, UnicodeError, AttributeError):
            raise APIError("invalid_json") from None
        if not isinstance(payload, dict) or "resultCode" not in payload:
            raise APIError("invalid_envelope")
        code = payload["resultCode"]
        self.last_response_diagnostic = {
            "operation": operation,
            "fields": sorted(k for k in payload if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,39}", k))[:40],
            "result_code": str(code) if re.fullmatch(r"[0-9]{1,3}", str(code)) else "unknown",
            "result_type": type(payload.get("result")).__name__,
        }
        if isinstance(code, bool) or not isinstance(code, (int, str)) or str(code) not in {"0", "200"}:
            diagnostic = "api_result_" + str(code) if isinstance(code, (int, str)) else ""
            raise APIError(diagnostic if diagnostic in _SAFE_CODES else "api_response_error")
        if set(payload) - _ENVELOPE_FIELDS:
            raise APIError("unexpected_envelope_fields")
        return payload

    def list_page(self, page):
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= MAX_PAGES:
            raise APIError("invalid_page")
        payload = self._request("list", {
            "pageNo": page, "numOfRows": PER_PAGE, "ongoingYn": "Y",
        })
        if "totalCount" not in payload:
            raise APIError("invalid_total_count")
        total = _count(payload["totalCount"])
        raw_result = payload.get("result")
        rows = _item(raw_result)
        if isinstance(raw_result, dict) and set(raw_result) == {"item"} and isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise APIError("invalid_list_shape")
        if len(rows) > PER_PAGE:
            raise APIError("too_many_page_rows")
        if len(rows) > total:
            raise APIError("excess_records")
        records, seen = [], set()
        for raw_record in rows:
            record = _item(raw_record)
            if not isinstance(record, dict) or not record:
                raise APIError("invalid_list_shape")
            identity = _notice_id(record.get("recrutPblntSn"))
            if identity in seen:
                raise APIError("duplicate_notice_id")
            seen.add(identity)
            records.append(record)
        self.success_counts["list"] += 1
        return {"totalCount": total, "result": records}

    def detail(self, sn):
        identity = _notice_id(sn)
        payload = self._request("detail", {"sn": identity})
        detail = _item(payload.get("result"))
        if not isinstance(detail, dict) or not detail:
            raise APIError("invalid_detail_shape")
        if _notice_id(detail.get("recrutPblntSn")) != identity:
            raise APIError("detail_identity_mismatch")
        self.success_counts["detail"] += 1
        return detail

    def collect_list(self):
        records, seen, expected = [], set(), None
        for page in range(1, MAX_PAGES + 1):
            payload = self.list_page(page)
            if expected is None:
                expected = payload["totalCount"]
                if expected == 0:
                    raise APIError("empty_list")
                if expected > PER_PAGE * MAX_PAGES:
                    raise APIError("page_limit_exceeded")
            elif payload["totalCount"] != expected:
                raise APIError("count_changed")
            rows = payload["result"]
            if len(records) + len(rows) > expected:
                raise APIError("excess_records")
            for record in rows:
                identity = _notice_id(record["recrutPblntSn"])
                if identity in seen:
                    raise APIError("duplicate_notice_id")
                seen.add(identity)
                records.append(record)
            if len(records) == expected:
                return records
            if len(rows) < PER_PAGE:
                raise APIError("incomplete_page")
        raise APIError("incomplete_collection")
