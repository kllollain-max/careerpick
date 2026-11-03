"""Bounded, read-only GOJOBS contract verification; no repository data writes."""
from datetime import date
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SERVICE_ID = "data_go_kr_15156780"
SOURCE_URL = "https://www.data.go.kr/data/15156780/openapi.do"
BASE_URL = "https://apis.data.go.kr/1760000/PblJobService"
TIMEOUT = 25
MAX_BYTES = 2_000_000
PAGE_SIZE = 5
DETAIL_LIMIT = 3
SUCCESS_CODES = {"00", "0", "200"}
SAFE_CODES = {"01", "02", "03", "04", "05", "10", "12", "20", "22", "23", "29", "30", "31", "99"}


class APIError(Exception):
    """Errors deliberately omit request URLs, credentials, and response bodies."""
    def __init__(self, safe_code):
        self.safe_code = safe_code
        super().__init__(safe_code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise APIError("redirect_blocked")


def _integer(value, *, positive=False):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,12}", value):
        raise APIError("invalid_integer")
    result = int(value)
    if positive and result == 0:
        raise APIError("invalid_identifier")
    return result


def _text(node, name, *, required=False, limit=2000):
    entries = node.findall(name)
    if len(entries) > 1:
        raise APIError("duplicate_xml_field")
    value = (entries[0].text or "").strip() if entries else ""
    if (required and not value) or len(value) > limit:
        raise APIError("invalid_" + name)
    return value


def _date(value):
    if not value:
        return None
    compact = value.replace("-", "")
    if not re.fullmatch(r"[0-9]{8}", compact):
        raise APIError("invalid_date")
    try:
        return date(int(compact[:4]), int(compact[4:6]), int(compact[6:])).isoformat()
    except ValueError:
        raise APIError("invalid_date") from None


def _public_link(value):
    if not value:
        return None
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        raise APIError("invalid_source_link") from None
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or len(value) > 2048
            or any(ord(c) < 32 for c in value)):
        raise APIError("invalid_source_link")
    # The API supplies source links; do not invent or follow them in this check.
    return value


class Client:
    def __init__(self, key):
        if not isinstance(key, str) or not key.strip():
            raise APIError("missing_key")
        original = key.strip()
        key = urllib.parse.unquote(original)
        if len(key) > 4096 or any(ord(c) < 33 for c in key):
            raise APIError("invalid_key_format")
        self._key = key
        variants = {original, key, urllib.parse.unquote(key)}
        variants.update(urllib.parse.quote(x, safe="") for x in tuple(variants))
        variants.update(urllib.parse.quote_plus(x, safe="") for x in tuple(variants))
        self._credential_forms = tuple(x.casefold() for x in variants if x)
        self.request_counts = {"list": 0, "detail": 0}
        self.success_counts = {"list": 0, "detail": 0}
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _reject_credential_echo(self, value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        for _ in range(3):
            folded = text.casefold()
            if any(secret in folded for secret in self._credential_forms):
                raise APIError("credential_echo_rejected")
            decoded = urllib.parse.unquote(text)
            if decoded == text:
                break
            text = decoded

    def _parse(self, payload):
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise APIError("invalid_response_encoding") from None
        self._reject_credential_echo(text)
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
            raise APIError("unsafe_xml_declaration")
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            raise APIError("invalid_xml") from None
        for node in root.iter():
            node.tag = node.tag.rsplit("}", 1)[-1]
            self._reject_credential_echo((node.text or "") + (node.tail or ""))
        if root.tag == "OpenAPI_ServiceResponse":
            code = root.findtext("cmmMsgHeader/returnReasonCode", "").strip()
            raise APIError("gateway_" + code if code in SAFE_CODES else "gateway_error")
        if root.tag != "response" or len(root.findall("header")) != 1:
            raise APIError("invalid_envelope")
        code = _text(root.find("header"), "resultCode", required=True, limit=10)
        if code not in SUCCESS_CODES:
            raise APIError("api_result_" + code if code in SAFE_CODES else "api_response_error")
        if len(root.findall("body")) != 1:
            raise APIError("invalid_body")
        return root.find("body")

    def _request(self, operation, params):
        paths = {"list": "getList", "detail": "getItem"}
        if operation not in paths:
            raise APIError("unsupported_operation")
        url = BASE_URL + "/" + paths[operation]
        query = urllib.parse.urlencode({"serviceKey": self._key, **params})
        request = urllib.request.Request(url + "?" + query,
                                         headers={"Accept": "application/xml"}, method="GET")
        self.request_counts[operation] += 1
        try:
            with self._opener.open(request, timeout=TIMEOUT) as response:
                if response.status != 200:
                    raise APIError("unexpected_http_status")
                final = urllib.parse.urlsplit(response.geturl())
                expected = urllib.parse.urlsplit(url)
                if (final.scheme, final.netloc, final.path) != (expected.scheme, expected.netloc, expected.path):
                    raise APIError("redirect_blocked")
                raw = response.read(MAX_BYTES + 1)
        except APIError:
            raise
        except urllib.error.HTTPError as error:
            # Only a bounded, allowlisted gateway code may leave the error response.
            try:
                raw = error.read(MAX_BYTES + 1)
                if len(raw) <= MAX_BYTES:
                    self._parse(raw)
            except APIError as parsed:
                if parsed.safe_code.startswith(("gateway_", "api_result_")) or parsed.safe_code == "credential_echo_rejected":
                    raise parsed from None
            except Exception:
                pass
            finally:
                error.close()
            raise APIError("http_" + str(error.code) if 100 <= error.code <= 599 else "http_error") from None
        except Exception:
            raise APIError("transport_error") from None
        if len(raw) > MAX_BYTES:
            raise APIError("response_too_large")
        return self._parse(raw)

    def list_sample(self, notice_type):
        if notice_type not in {"e01", "e02"}:
            raise APIError("unsupported_filter")
        body = self._request("list", {"pageNo": 1, "numOfRows": PAGE_SIZE,
                                      "Pblanc_ty": notice_type, "Instt_se": "g02", "Sort_order": "1"})
        total = _integer(_text(body, "totalCount", required=True))
        if _integer(_text(body, "pageNo", required=True)) != 1:
            raise APIError("page_mismatch")
        per_page = _integer(_text(body, "numOfRows", required=True), positive=True)
        if per_page != PAGE_SIZE or len(body.findall("items")) > 1:
            raise APIError("pagination_mismatch")
        rows = body.findall("items/item")
        if len(rows) > PAGE_SIZE or len(rows) != min(PAGE_SIZE, total):
            raise APIError("sample_count_mismatch")
        records, seen = [], set()
        for row in rows:
            identity = str(_integer(_text(row, "idx", required=True), positive=True))
            if identity in seen:
                raise APIError("duplicate_identifier")
            seen.add(identity)
            institution_type = _text(row, "type01", required=True, limit=10)
            recruitment_type = _text(row, "type02", required=True, limit=10)
            if institution_type != "g02" or recruitment_type != notice_type:
                raise APIError("filter_mismatch")
            records.append({"id": identity, "title": _text(row, "title", required=True),
                            "org": _text(row, "insttname", required=True),
                            "institution_type": institution_type, "recruitment_type": recruitment_type,
                            "deadline": _date(_text(row, "enddate", limit=20)),
                            "registered_date": _date(_text(row, "regdate", limit=20)),
                            "modified_date": _date(_text(row, "moddate", limit=20))})
        self._reject_credential_echo(records)
        self.success_counts["list"] += 1
        return total, records

    def detail(self, identity):
        identity = str(_integer(str(identity), positive=True))
        body = self._request("detail", {"idx": identity})
        rows = body.findall("item")
        if len(rows) != 1:
            raise APIError("invalid_detail_shape")
        row = rows[0]
        actual_id = str(_integer(_text(row, "idx", required=True), positive=True))
        if actual_id != identity:
            raise APIError("detail_identity_mismatch")
        record = {"id": actual_id, "title": _text(row, "title", required=True),
                  "institution_type": _text(row, "type01", required=True, limit=10),
                  "recruitment_type": _text(row, "type02", required=True, limit=10),
                  "source_links": [link for name in ("link01", "link02", "link03")
                                   if (link := _public_link(_text(row, name, limit=2048)))],
                  "content_present": bool(_text(row, "contents", limit=MAX_BYTES))}
        self._reject_credential_echo(record)
        self.success_counts["detail"] += 1
        return record

    def verify(self):
        totals, records = {}, []
        for category in ("e01", "e02"):
            totals[category], sample = self.list_sample(category)
            records.extend(sample)
        if len({record["id"] for record in records}) != len(records):
            raise APIError("duplicate_identifier_across_filters")
        # Verify both recruitment types when available, then fill the remaining slot.
        selected = []
        for category in ("e01", "e02"):
            first = next((record for record in records if record["recruitment_type"] == category), None)
            if first:
                selected.append(first)
        selected_ids = {record["id"] for record in selected}
        selected.extend(record for record in records if record["id"] not in selected_ids)
        details = []
        for record in selected[:DETAIL_LIMIT]:
            detail = self.detail(record["id"])
            if (detail["title"] != record["title"]
                    or detail["institution_type"] != record["institution_type"]
                    or detail["recruitment_type"] != record["recruitment_type"]):
                raise APIError("detail_list_mismatch")
            details.append(detail)
        summary = {"service": SERVICE_ID, "source_url": SOURCE_URL,
                   "endpoint_base": BASE_URL, "list_endpoint": BASE_URL + "/getList",
                   "detail_endpoint": BASE_URL + "/getItem", "list_verified": True,
                   "authentication_verified": True, "empty_list": not records,
                   "detail_status": "verified_sample" if details else "unverified_empty_list",
                   "detail_verified": bool(details), "detail_verified_count": len(details),
                   "list_count_returned": len(records), "total_count_by_filter": totals,
                   "sample_scope": "first_page_of_local_public_and_career_recruitment_only",
                   "full_collection": False, "active_status_verified": False,
                   "filters": {"Instt_se": "g02", "Pblanc_ty": ["e01", "e02"], "pageNo": 1,
                               "numOfRows": PAGE_SIZE, "Sort_order": "1"},
                   "samples": records, "detail_samples": details,
                   "unverified_scope": ["attachment_files", "all_notices", "official_closure",
                                        "all_exam_schedules", "source_link_contents"],
                   "requests": dict(self.request_counts), "successful_responses": dict(self.success_counts)}
        self._reject_credential_echo(summary)
        return summary
