"""Read-only client for the official Cleaneye employment API (15159757).

Contract source: https://www.data.go.kr/data/15159757/openapi.do, the embedded
Swagger 2.0 document inspected on 2026-11-07.  Its only query parameters are
serviceKey, sidoCd and type.  There is no documented pagination or date filter:
each caller-supplied region must return its entire declared totalCount.

Records keep the official uppercase field names and string values.  In
particular, this client does not guess employment/status codes, date formats,
attachment URLs or publication dates.  It never reads credentials from the
environment, follows notice URLs, prints response bodies, or writes files.
"""

import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


SERVICE_ID = "data_go_kr_15159757"
SOURCE_URL = "https://www.data.go.kr/data/15159757/openapi.do"
BASE_URL = "https://apis.data.go.kr/B551982/openApiEmployInfo"
OPERATION = "openXmlEmployInfo"
REGION_SOURCE_URL = "https://www.data.go.kr/data/15061217/openapi.do"
REGION_BASE_URL = "https://apis.data.go.kr/B551982/openApiSidoCd3"
REGION_OPERATION = "openXmlSidoCd2"
# 300 is the example page size in this service's official Swagger reqList.
REGION_PAGE_SIZE = 300
MAX_REGION_PAGES = 32
MAX_REGION_CODE_CHARS = 128
TIMEOUT = 25
# At most three attempts for one idempotent GET; no HTTP/API error retries.
TRANSPORT_RETRY_DELAYS = (1, 2)
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_REGIONS = 32
MAX_REGION_RECORDS = 20_000
MAX_TOTAL_RECORDS = 100_000
MAX_COLLECTION_TEXT_CHARS = 64 * 1024 * 1024
MAX_FIELD_CHARS = 256 * 1024

FIELDS = frozenset({
    "FILE_NAME2", "ENT_NAME", "ENT_TITLE", "ENT_GB", "ENT_KIND", "SIDO_CD",
    "STATUS", "EMPYEAR", "ENT_RECRUIT", "EMPLOY_NUM", "EMPLOY_GB", "JOB_TYPE",
    "RE_MAN_YN", "POSITION", "YEARINCOME", "OFFICE_HOURS", "WORK_PLACE",
    "DUTY_DETAIL", "RETIREMENT", "JUDGE_METHOD", "LOCAL_YN", "LOCAL_NAME",
    "LOCAL_REASON", "ENT_LICENSE1", "ENT_LICENSE2", "ENT_LICENSE3",
    "ENT_LICENSE4", "SPECIAL_ITEM", "PUB_DATE", "PUB_END_DATE", "ACCUSATION",
    "REFERENCE", "EXHIBIT", "JOB_SEEK_ETC", "FILE_NAME1", "FILE_NAME3", "URL",
    "ADDRESS", "NO", "UPD_DATE",
})
_REQUIRED_FIELDS = {"NO", "ENT_NAME", "ENT_TITLE"}
_FIELD_LIMITS = {
    # The existing stored-record identifier limit is 128 including "cleaneye-".
    "NO": 119, "ENT_NAME": 2_000, "ENT_TITLE": 4_000, "SIDO_CD": 128,
    "STATUS": 128, "JOB_TYPE": 256, "EMPYEAR": 32, "PUB_DATE": 128,
    "PUB_END_DATE": 128, "UPD_DATE": 128, "URL": 8_192,
    "FILE_NAME1": 4_096, "FILE_NAME2": 4_096, "FILE_NAME3": 4_096,
}
SUCCESS_CODES = {"0", "00", "200"}
_RESULT_CODES = {
    "1", "2", "3", "4", "5", "6", "7", "8", "01", "02", "03", "04",
    "05", "06", "07", "08", "10", "11", "12", "20", "21", "22", "23",
    "29", "30", "31", "32", "33", "99",
}
_GATEWAY_TOKENS = {
    "APPLICATION_ERROR", "HTTP_ERROR", "SERVICETIMEOUT_ERROR",
    "INVALID_REQUEST_PARAMETER_ERROR", "NO_OPENAPI_SERVICE_ERROR",
    "SERVICE_KEY_IS_NULL", "PERMISSION_DENIED", "SERVICE_ACCESS_DENIED_ERROR",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR",
    "BLACKLIST_IP_ACCESS_ERROR", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
    "DEADLINE_HAS_EXPIRED_ERROR",
}
_SAFE_CODES = {
    "missing_key", "invalid_key", "invalid_region", "missing_regions",
    "duplicate_region", "region_limit_exceeded", "redirect_rejected",
    "transport_failed", "unexpected_http_status", "http_error",
    "response_too_large", "invalid_response_encoding", "credential_echo_rejected",
    "unsafe_xml_declaration", "invalid_xml", "invalid_envelope", "invalid_header",
    "invalid_body", "invalid_no_data_response", "duplicate_xml_field", "invalid_xml_field",
    "api_response_error", "gateway_error", "unexpected_body_field",
    "invalid_total_count", "region_record_limit_exceeded", "invalid_items",
    "invalid_record", "unexpected_record_field", "record_field_too_large",
    "duplicate_notice_id", "duplicate_notice_id_across_regions",
    "incomplete_collection", "excess_records", "empty_list",
    "record_limit_exceeded", "collection_too_large", "internal_error",
    "unsupported_operation", "invalid_reference_year", "invalid_region_page",
    "invalid_region_pagination", "invalid_region_record", "duplicate_region_code",
    "duplicate_region_code_across_pages", "region_count_changed",
    "empty_region_codes", "incomplete_region_page", "incomplete_region_codes",
    "region_page_limit_exceeded",
}
_SAFE_CODES.update("http_status_" + str(code) for code in range(400, 600))
_SAFE_CODES.update("api_result_" + code for code in _RESULT_CODES)
_SAFE_CODES.update("gateway_" + code for code in _RESULT_CODES)
_SAFE_CODES.update("gateway_" + token for token in _GATEWAY_TOKENS)


class APIError(RuntimeError):
    """Only fixed diagnostic codes may leave this module as errors."""

    def __init__(self, safe_code):
        self.safe_code = safe_code if safe_code in _SAFE_CODES else "internal_error"
        super().__init__(self.safe_code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise APIError("redirect_rejected") from None


def _retryable_transport_error(error):
    # Inspect exception types only. Exception messages may contain the key URL,
    # and an HTTPError is also a URLError but must never be retried here.
    if isinstance(error, urllib.error.HTTPError):
        return False
    if isinstance(error, urllib.error.URLError):
        error = error.reason
    if isinstance(error, (ssl.SSLError, urllib.error.HTTPError)):
        return False
    return (isinstance(error, (TimeoutError, ConnectionError))
            or isinstance(error, socket.gaierror) and error.errno == socket.EAI_AGAIN)


def _region(value):
    # A region is explicitly supplied by the caller from a verified code list.
    # The official type is string, not a guaranteed numeric identifier.  Preserve
    # the value and let urlencode safely escape punctuation and non-ASCII text.
    if (not isinstance(value, str) or not value.strip()
            or len(value) > MAX_REGION_CODE_CHARS
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise APIError("invalid_region")
    return value


def _reference_year(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise APIError("invalid_reference_year")
    if not re.fullmatch(r"[1-9][0-9]{3}", str(value)):
        raise APIError("invalid_reference_year")
    return int(value)


def _one(parent, name, *, required=True):
    matches = parent.findall(name)
    if len(matches) > 1:
        raise APIError("duplicate_xml_field")
    if not matches:
        if required:
            raise APIError("invalid_xml_field")
        return None
    return matches[0]


def _text(parent, name, *, required=True, limit=MAX_FIELD_CHARS):
    node = _one(parent, name, required=required)
    if node is None:
        return ""
    if len(node):
        raise APIError("invalid_xml_field")
    value = (node.text or "").strip()
    if len(value) > limit or (required and not value):
        raise APIError("invalid_xml_field")
    return value


class Client:
    def __init__(self, key):
        if not isinstance(key, str):
            raise APIError("invalid_key")
        original = key.strip()
        if not original:
            raise APIError("missing_key")
        try:
            # Decode once, preserving a literal '+' in an already-decoded key.
            decoded = urllib.parse.unquote(original, errors="strict")
        except (ValueError, UnicodeError):
            raise APIError("invalid_key") from None
        if len(decoded) > 4_096 or not decoded or any(ord(c) < 33 for c in decoded):
            raise APIError("invalid_key")
        self._key = decoded
        variants = {original, decoded}
        for _ in range(2):
            variants.update(urllib.parse.quote(value, safe="") for value in tuple(variants))
        self._credential_forms = tuple(value.casefold() for value in variants if value)
        self.request_counts = {"list": 0}
        self.success_counts = {"list": 0}
        self.region_counts = {}
        self.region_code_mapping = {}
        self.region_code_metadata = None
        self.collection_complete = False
        self.last_response_diagnostic = None
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _reject_credential_echo(self, value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        for _ in range(4):
            if any(secret in text.casefold() for secret in self._credential_forms):
                raise APIError("credential_echo_rejected")
            decoded = urllib.parse.unquote(text)
            if decoded == text:
                break
            text = decoded

    def _envelope(self, raw, operation="list", *, allow_no_data=False):
        try:
            text = raw.decode("utf-8-sig")
        except (AttributeError, UnicodeDecodeError):
            raise APIError("invalid_response_encoding") from None
        self._reject_credential_echo(text)
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
            raise APIError("unsafe_xml_declaration")
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            raise APIError("invalid_xml") from None
        for node in root.iter():
            self._reject_credential_echo(node.tag)
            self._reject_credential_echo(node.attrib)
            self._reject_credential_echo((node.text or "") + (node.tail or ""))
            node.tag = node.tag.rsplit("}", 1)[-1]
        if root.tag == "OpenAPI_ServiceResponse":
            code = root.findtext("cmmMsgHeader/returnReasonCode", "").strip()
            raise APIError("gateway_" + code if code in _RESULT_CODES else "gateway_error")
        if root.tag != "response":
            raise APIError("invalid_envelope")
        # Swagger names its schema components openXmlEmployInfo-header/body;
        # the standard gateway XML uses header/body.  Never mix the two pairs.
        schema_name = {"list": "openXmlEmployInfo", "region_codes": "openXmlSidoCd"}.get(operation)
        if schema_name is None:
            raise APIError("unsupported_operation")
        layouts = (
            ("header", "body", "standard"),
            (schema_name + "-header", schema_name + "-body", "documented"),
        )
        tags = [node.tag for node in root]
        matching = [layout for layout in layouts
                    if tags.count(layout[0]) == 1 and tags.count(layout[1]) <= 1
                    and set(tags).issubset(set(layout[:2]))]
        if len(matching) != 1:
            raise APIError("invalid_envelope")
        header_name, body_name, layout = matching[0]
        header = _one(root, header_name)
        if any(child.tag not in {"resultCode", "resultMsg"} for child in header):
            raise APIError("invalid_header")
        code = _text(header, "resultCode", limit=32)
        message = _text(header, "resultMsg", required=False, limit=4_096)
        if code not in SUCCESS_CODES:
            if not (allow_no_data and operation == "list" and code == "3"
                    and message == "NONOTEXISTDATA_ERROR"):
                raise APIError("api_result_" + code if code in _RESULT_CODES else "api_response_error")
            # Run 42336052565 observed this exact pair without a body for a
            # verified region.  Do not extend the regional no-data exception to
            # other messages, code lookup, HTTP errors or contradictory data.
            if (root.text or "").strip() or any((node.tail or "").strip() for node in root):
                raise APIError("invalid_no_data_response")
            body = _one(root, body_name, required=False)
            if body is not None:
                if any(child.tag not in {"items", "totalCount"} for child in body):
                    raise APIError("unexpected_body_field")
                if (body.text or "").strip() or any((node.tail or "").strip() for node in body):
                    raise APIError("invalid_no_data_response")
                if _one(body, "totalCount", required=False) is not None:
                    count = _text(body, "totalCount", limit=16)
                    if not re.fullmatch(r"[0-9]{1,12}", count):
                        raise APIError("invalid_total_count")
                    if int(count) != 0:
                        raise APIError("invalid_no_data_response")
                items = _one(body, "items", required=False)
                if items is not None and (len(items) or (items.text or "").strip()):
                    raise APIError("invalid_no_data_response")
            return None, layout
        if tags.count(body_name) != 1:
            raise APIError("invalid_body")
        body = _one(root, body_name)
        return body, layout

    def _parse(self, raw):
        body, layout = self._envelope(raw, "list", allow_no_data=True)
        if body is None:
            self.last_response_diagnostic = {
                "envelope_layout": layout, "result_code": "3", "total_count": 0, "record_count": 0,
            }
            return {"totalCount": 0, "result": []}
        if any(child.tag not in {"items", "totalCount"} for child in body):
            raise APIError("unexpected_body_field")
        count = _text(body, "totalCount", limit=16)
        if not re.fullmatch(r"[0-9]{1,12}", count):
            raise APIError("invalid_total_count")
        total = int(count)
        if total > MAX_REGION_RECORDS:
            raise APIError("region_record_limit_exceeded")
        items = _one(body, "items", required=False)
        if items is None:
            if total:
                raise APIError("invalid_items")
            rows = []
        else:
            if any(child.tag != "item" for child in items) or (items.text or "").strip():
                raise APIError("invalid_items")
            rows = list(items)
        if len(rows) < total:
            raise APIError("incomplete_collection")
        if len(rows) > total:
            raise APIError("excess_records")
        records, seen = [], set()
        for row in rows:
            record = {}
            if (row.text or "").strip():
                raise APIError("invalid_record")
            for field in row:
                name = field.tag
                if name not in FIELDS:
                    raise APIError("unexpected_record_field")
                if name in record:
                    raise APIError("duplicate_xml_field")
                if len(field):
                    raise APIError("invalid_xml_field")
                value = (field.text or "").strip()
                if len(value) > _FIELD_LIMITS.get(name, MAX_FIELD_CHARS):
                    raise APIError("record_field_too_large")
                record[name] = value
            if any(not record.get(name) for name in _REQUIRED_FIELDS):
                raise APIError("invalid_record")
            # Treat source identifiers as opaque strings; do not coerce numbers.
            identity = record["NO"]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,118}", identity):
                raise APIError("invalid_record")
            if identity in seen:
                raise APIError("duplicate_notice_id")
            seen.add(identity)
            records.append(record)
        self._reject_credential_echo(records)
        self.last_response_diagnostic = {
            "envelope_layout": layout, "total_count": total, "record_count": len(records),
        }
        return {"totalCount": total, "result": records}

    def _fetch(self, operation, params):
        self.last_response_diagnostic = None
        endpoints = {
            "list": BASE_URL + "/" + OPERATION,
            "region_codes": REGION_BASE_URL + "/" + REGION_OPERATION,
        }
        if operation not in endpoints:
            raise APIError("unsupported_operation")
        endpoint = endpoints[operation]
        query = urllib.parse.urlencode({"serviceKey": self._key, **params})
        request = urllib.request.Request(
            endpoint + "?" + query, method="GET",
            headers={"Accept": "application/xml", "User-Agent": "CareerPick"},
        )
        self.request_counts.setdefault(operation, 0)
        try:
            for attempt in range(len(TRANSPORT_RETRY_DELAYS) + 1):
                # Count each open attempt, including timeouts and retries;
                # successful regions are counted only after full validation.
                self.request_counts[operation] += 1
                try:
                    with self._opener.open(request, timeout=TIMEOUT) as response:
                        if 300 <= response.status < 400:
                            raise APIError("redirect_rejected")
                        if response.status != 200:
                            raise APIError("unexpected_http_status")
                        actual = urllib.parse.urlsplit(response.geturl())
                        expected = urllib.parse.urlsplit(endpoint)
                        if (actual.scheme, actual.netloc, actual.path) != (
                                expected.scheme, expected.netloc, expected.path):
                            raise APIError("redirect_rejected")
                        raw = response.read(MAX_RESPONSE_BYTES + 1)
                    break
                except (APIError, urllib.error.HTTPError):
                    raise
                except Exception as error:
                    if (attempt == len(TRANSPORT_RETRY_DELAYS)
                            or not _retryable_transport_error(error)):
                        raise
                    time.sleep(TRANSPORT_RETRY_DELAYS[attempt])
        except APIError:
            raise
        except urllib.error.HTTPError as error:
            diagnostic = "http_status_" + str(error.code)
            if 300 <= error.code < 400:
                error.close()
                raise APIError("redirect_rejected") from None
            try:
                raw = error.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) <= MAX_RESPONSE_BYTES:
                    text = raw.decode("utf-8-sig", errors="replace")
                    self._reject_credential_echo(text)
                    try:
                        self._envelope(raw, operation)
                    except APIError as parsed:
                        if (parsed.safe_code.startswith(("gateway_", "api_result_"))
                                or parsed.safe_code == "credential_echo_rejected"):
                            diagnostic = parsed.safe_code
                    if diagnostic.startswith("http_status_"):
                        for token in sorted(_GATEWAY_TOKENS):
                            if re.search(r"(?<![A-Z_])" + re.escape(token) + r"(?![A-Z_])", text):
                                diagnostic = "gateway_" + token
                                break
            except APIError as parsed:
                diagnostic = parsed.safe_code
            except Exception:
                pass
            finally:
                error.close()
                self.last_response_diagnostic = None
            raise APIError(diagnostic if diagnostic in _SAFE_CODES else "http_error") from None
        except Exception:
            # Exceptions can contain the complete credential-bearing URL.
            raise APIError("transport_failed") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise APIError("response_too_large")
        return raw

    def _request(self, sido_code):
        return self._parse(self._fetch("list", {
            "sidoCd": _region(sido_code), "type": "xml",
        }))

    def _region_codes_page(self, *, ac_year, page):
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= MAX_REGION_PAGES:
            raise APIError("invalid_region_page")
        raw = self._fetch("region_codes", {
            "pageNo": page, "numOfRows": REGION_PAGE_SIZE, "type": "xml",
            "ac_year": _reference_year(ac_year),
        })
        body, layout = self._envelope(raw, "region_codes")
        if any(child.tag not in {"items", "totalCount", "numOfRows", "pageNo"} for child in body):
            raise APIError("unexpected_body_field")
        numeric = {}
        for name in ("totalCount", "numOfRows", "pageNo"):
            value = _text(body, name, limit=16)
            if not re.fullmatch(r"[0-9]{1,12}", value):
                raise APIError("invalid_total_count" if name == "totalCount" else "invalid_region_pagination")
            numeric[name] = int(value)
        total, page_size = numeric["totalCount"], numeric["numOfRows"]
        if total > MAX_REGIONS:
            raise APIError("region_limit_exceeded")
        if numeric["pageNo"] != page or not 1 <= page_size <= REGION_PAGE_SIZE:
            raise APIError("invalid_region_pagination")
        items = _one(body, "items", required=False)
        if items is None:
            if total:
                raise APIError("invalid_items")
            rows = []
        else:
            if any(child.tag != "item" for child in items) or (items.text or "").strip():
                raise APIError("invalid_items")
            rows = list(items)
        if len(rows) > page_size or len(rows) > total:
            raise APIError("excess_records")
        result, seen = [], set()
        for row in rows:
            if (row.text or "").strip() or any(
                    child.tag not in {"No", "SIDO_CD", "SIDO_NAME"} for child in row):
                raise APIError("invalid_region_record")
            _text(row, "No", limit=128)
            code_node = _one(row, "SIDO_CD")
            if len(code_node):
                raise APIError("invalid_region_record")
            # Do not decode, trim, cast or rewrite a provider's region code.
            code = _region(code_node.text or "")
            name = _text(row, "SIDO_NAME", limit=256)
            if code in seen:
                raise APIError("duplicate_region_code")
            seen.add(code)
            result.append({"code": code, "name": name})
        self._reject_credential_echo(result)
        self.last_response_diagnostic = {
            "operation": "region_codes", "envelope_layout": layout,
            "total_count": total, "record_count": len(result), "page": page,
        }
        self.success_counts.setdefault("region_codes", 0)
        self.success_counts["region_codes"] += 1
        return {**numeric, "result": result}

    def collect_region_codes(self, ac_year):
        """Return a complete official code-to-name mapping for one reference year.

        This is a read-only request to separately authorized dataset 15061217.
        An unapproved credential raises its safe gateway error (including 30);
        it does not trigger registration, substitute guessed codes, or publish
        a partial mapping.  Metadata records provenance and completion status.
        """
        self.collection_complete = False
        self.region_code_mapping = {}
        self.region_code_metadata = None
        self.last_response_diagnostic = None
        self.request_counts.setdefault("region_codes", 0)
        self.success_counts.setdefault("region_codes", 0)
        year = _reference_year(ac_year)
        self.region_code_metadata = {
            "source_url": REGION_SOURCE_URL, "reference_year": year,
            "total_count": 0, "pages": 0, "complete": False,
        }
        mapping, expected = {}, None
        for page in range(1, MAX_REGION_PAGES + 1):
            payload = self._region_codes_page(ac_year=year, page=page)
            if expected is None:
                expected = payload["totalCount"]
                if expected == 0:
                    raise APIError("empty_region_codes")
                self.region_code_metadata["total_count"] = expected
            elif payload["totalCount"] != expected:
                raise APIError("region_count_changed")
            self.region_code_metadata["pages"] = page
            for record in payload["result"]:
                if record["code"] in mapping:
                    raise APIError("duplicate_region_code_across_pages")
                mapping[record["code"]] = record["name"]
            if len(mapping) > expected:
                raise APIError("excess_records")
            if len(mapping) == expected:
                self._reject_credential_echo(mapping)
                self._reject_credential_echo(self.region_code_metadata)
                self.region_code_mapping = dict(mapping)
                self.region_code_metadata["complete"] = True
                return dict(mapping)
            if len(payload["result"]) < payload["numOfRows"]:
                raise APIError("incomplete_region_page")
        raise APIError("region_page_limit_exceeded")

    def list_region(self, sido_code):
        """Return one complete regional result; a genuine zero total is allowed."""
        sido_code = _region(sido_code)
        payload = self._request(sido_code)
        self.success_counts["list"] += 1
        self.region_counts[sido_code] = payload["totalCount"]
        return payload

    def collect_list(self, *, sido_codes):
        """Collect all explicitly verified regions atomically, or raise APIError.

        There is deliberately no guessed national default.  The caller must
        supply the verified institution-region codes.  Regional zero totals
        are valid, but an entirely empty collection cannot replace stored data.
        Counters are diagnostics only, never a partially publishable result.
        """
        self.collection_complete = False
        self.region_counts = {}
        self.last_response_diagnostic = None
        if not isinstance(sido_codes, (list, tuple)) or not sido_codes:
            raise APIError("missing_regions")
        if len(sido_codes) > MAX_REGIONS:
            raise APIError("region_limit_exceeded")
        codes = tuple(_region(code) for code in sido_codes)
        if len(set(codes)) != len(codes):
            raise APIError("duplicate_region")
        records, seen, expected, text_chars = [], set(), 0, 0
        for code in codes:
            payload = self.list_region(code)
            expected += payload["totalCount"]
            if expected > MAX_TOTAL_RECORDS:
                raise APIError("record_limit_exceeded")
            for record in payload["result"]:
                if record["NO"] in seen:
                    raise APIError("duplicate_notice_id_across_regions")
                seen.add(record["NO"])
                text_chars += sum(len(value) for value in record.values())
                if text_chars > MAX_COLLECTION_TEXT_CHARS:
                    raise APIError("collection_too_large")
                records.append(record)
        if not records:
            raise APIError("empty_list")
        if len(records) != expected:
            raise APIError("incomplete_collection")
        self._reject_credential_echo(records)
        self.collection_complete = True
        return records
