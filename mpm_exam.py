"""Read-only check of the pinned 2026 MPM examination calendar API.

Official contract: https://infuser.odcloud.kr/oas/docs?namespace=3033611/v1
No repository data is read, written, merged, or published by this module.
"""

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date


SERVICE_ID = "mpm_exam_3033611"
DATASET_YEAR = 2026
DATASET_NAME = "인사혁신처_국가공무원 시험일정_20260216"
ENDPOINT = "https://api.odcloud.kr/api/3033611/v1/uddi:99fb67de-ddf5-4a3e-8cfb-d3193c7156c5"
SOURCE_URL = "https://www.data.go.kr/data/3033611/fileData.do"
CONTRACT_URL = "https://infuser.odcloud.kr/oas/docs?namespace=3033611/v1"
PER_PAGE = 50
MAX_PAGES = 2
MAX_RESPONSE_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 20
FIELDS = (
    "시험명", "선발예정인원", "원서접수기간", "시험단계구분",
    "시험장소공고일", "시험일", "합격자발표일",
)
DATE_FIELDS = ("원서접수기간", "시험장소공고일", "시험일", "합격자발표일")
ENVELOPE_FIELDS = {"page", "perPage", "totalCount", "currentCount", "matchCount", "data"}
UNSCHEDULED = {"", "-", "―", "—", "미정", "추후공고", "별도공고", "해당없음"}


class APIError(Exception):
    """Only a fixed diagnostic code is safe to display."""

    def __init__(self, safe_code):
        self.safe_code = safe_code
        super().__init__(safe_code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise APIError("redirect_blocked")


def _int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise APIError("invalid_counts")
    return value


def _key_forms(key):
    forms = {key, urllib.parse.unquote(key)}
    for value in tuple(forms):
        forms.update({urllib.parse.quote(value, safe=""), urllib.parse.quote_plus(value), html.escape(value)})
    return {value for value in forms if value}


def _date_tokens(value):
    """Validate source dates without inventing dates for blank/unscheduled cells.

    ISO, dotted and Korean full dates are supported; a month/day date gets its
    year from the pinned official dataset title, and that inference is reported.
    """
    compact = re.sub(r"\s+", "", value)
    if compact in UNSCHEDULED:
        return [], False
    # A weekday or an explicitly supplied clock does not change the date.
    cleaned = re.sub(r"\([월화수목금토일](?:요일)?\)", "", value)
    cleaned = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", "", cleaned)
    full = r"(?<!\d)(20\d{2})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})(?:\s*[.일])?(?!\d)"
    matches = list(re.finditer(full, cleaned))
    inferred = False
    if matches:
        parts = [(int(m[1]), int(m[2]), int(m[3])) for m in matches]
        remainder = re.sub(full, "", cleaned)
    else:
        short = r"(?<!\d)(\d{1,2})\s*[./월]\s*(\d{1,2})(?:\s*[.일])?(?!\d)"
        matches = list(re.finditer(short, cleaned))
        parts = [(DATASET_YEAR, int(m[1]), int(m[2])) for m in matches]
        remainder = re.sub(short, "", cleaned)
        inferred = bool(matches)
    # Reject numbers or prose that could hide an unparsed date/range endpoint.
    if not parts or re.sub(r"[\s~∼～–—\-,/]+", "", remainder):
        raise APIError("unverified_date_format")
    values = []
    for year, month, day in parts:
        if year != DATASET_YEAR:
            raise APIError("unexpected_dataset_year")
        try:
            values.append(date(year, month, day).isoformat())
        except ValueError:
            raise APIError("invalid_calendar_date") from None
    if values != sorted(values):
        raise APIError("invalid_date_range")
    return values, inferred


class Client:
    def __init__(self, key):
        if not isinstance(key, str) or not key.strip():
            raise APIError("missing_key")
        self._key = urllib.parse.unquote(key.strip())
        if len(self._key) > 2048 or any(ord(c) < 32 for c in self._key):
            raise APIError("invalid_key_format")
        self._key_forms = _key_forms(key.strip()) | _key_forms(self._key)
        self._opener = urllib.request.build_opener(_NoRedirect())
        self.request_counts = {"list": 0}
        self.success_counts = {"list": 0}
        self.last_response_diagnostic = None
        self._null_place_announcement_cells = 0

    def _reject_echo(self, text):
        # Normalize percent-encoding and HTML entities before checking. Do not
        # include a response, URL, credential, or original exception in errors.
        variants = (text, urllib.parse.unquote(text), html.unescape(text))
        if any(secret in candidate for candidate in variants for secret in self._key_forms):
            raise APIError("credential_echo")

    def _page(self, page):
        self.last_response_diagnostic = None
        query = urllib.parse.urlencode({
            "page": page, "perPage": PER_PAGE, "returnType": "JSON", "serviceKey": self._key,
        })
        request = urllib.request.Request(ENDPOINT + "?" + query, headers={"Accept": "application/json"})
        self.request_counts["list"] += 1
        try:
            with self._opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                status = response.status
                if status != 200:
                    raise APIError("http_" + str(status) if status in {400, 401, 403, 404, 429, 500, 502, 503, 504} else "http_error")
                target = urllib.parse.urlsplit(response.geturl())
                expected = urllib.parse.urlsplit(ENDPOINT)
                if (target.scheme, target.netloc, target.path) != (expected.scheme, expected.netloc, expected.path):
                    raise APIError("redirect_blocked")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except APIError:
            raise
        except urllib.error.HTTPError as error:
            code = error.code
            raise APIError("http_" + str(code) if code in {400, 401, 403, 404, 429, 500, 502, 503, 504} else "http_error") from None
        except Exception:
            raise APIError("request_failed") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise APIError("response_too_large")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            raise APIError("invalid_encoding") from None
        self._reject_echo(text)
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            raise APIError("invalid_json") from None
        self._reject_echo(json.dumps(payload, ensure_ascii=False))
        if not isinstance(payload, dict) or set(payload) != ENVELOPE_FIELDS:
            raise APIError("invalid_envelope")
        for name in ENVELOPE_FIELDS - {"data"}:
            _int(payload[name])
        rows = payload["data"]
        if not isinstance(rows, list) or len(rows) > PER_PAGE or payload["currentCount"] != len(rows):
            raise APIError("invalid_counts")
        if payload["page"] != page or payload["perPage"] != PER_PAGE:
            raise APIError("pagination_mismatch")
        if payload["totalCount"] != payload["matchCount"]:
            raise APIError("total_count_mismatch")
        # Fixed schema names and JSON type names only. No source values, extra
        # keys, response body, URLs, or credentials enter this diagnostic.
        self.last_response_diagnostic = {
            "field_types": {
                name: sorted({
                    type(row[name]).__name__ if isinstance(row, dict) and name in row else "missing"
                    for row in rows
                })
                for name in FIELDS
            }
        }
        normalized_rows, null_place_cells = [], 0
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(FIELDS):
                raise APIError("invalid_columns")
            # The official listing allows blank place-announcement dates for
            # document-screening stages. A live response confirmed JSON null
            # only in this field; do not infer a date or loosen other fields.
            if row["시험장소공고일"] is None:
                row = {**row, "시험장소공고일": ""}
                null_place_cells += 1
            if any(not isinstance(row[name], str) or len(row[name]) > 2048 for name in FIELDS):
                raise APIError("invalid_field_type")
            if not row["시험명"].strip() or not row["시험단계구분"].strip():
                raise APIError("missing_exam_identity")
            normalized_rows.append(row)
        payload["data"] = normalized_rows
        self._null_place_announcement_cells += null_place_cells
        self.success_counts["list"] += 1
        return payload

    def verify(self):
        self._null_place_announcement_cells = 0
        rows, total = [], None
        for page in range(1, MAX_PAGES + 1):
            payload = self._page(page)
            if total is None:
                total = payload["totalCount"]
                if total == 0:
                    raise APIError("empty_dataset")
                if total > MAX_PAGES * PER_PAGE:
                    raise APIError("dataset_over_limit")
            elif total != payload["totalCount"]:
                raise APIError("total_count_changed")
            rows.extend(payload["data"])
            if len(rows) > total:
                raise APIError("excess_rows")
            if len(rows) == total:
                break
            if payload["currentCount"] < PER_PAGE:
                raise APIError("incomplete_dataset")
        if len(rows) != total:
            raise APIError("incomplete_dataset")
        fingerprints = {json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows}
        if len(fingerprints) != len(rows):
            raise APIError("duplicate_rows")
        date_cells, unscheduled_cells, inferred_cells = 0, 0, 0
        for row in rows:
            for name in DATE_FIELDS:
                dates, inferred = _date_tokens(row[name])
                if dates:
                    date_cells += 1
                    inferred_cells += bool(inferred)
                else:
                    unscheduled_cells += 1
        if date_cells == 0:
            raise APIError("no_verified_dates")
        samples, names = [], set()
        for row in rows:
            name = row["시험명"].strip()
            if name not in names and len(samples) < 3:
                samples.append(dict(row))
            names.add(name)
        return {
            "service": SERVICE_ID,
            "endpoint": ENDPOINT,
            "source_url": SOURCE_URL,
            "contract_url": CONTRACT_URL,
            "dataset_name": DATASET_NAME,
            "dataset_year": DATASET_YEAR,
            "dataset_year_source": "pinned_official_swagger_title_and_validated_dates",
            "list_verified": True,
            "authentication_verified": True,
            "columns_verified": list(FIELDS),
            "received_rows": len(rows),
            "total_rows": total,
            "distinct_exam_names": len(names),
            "row_scope": "exam_stage_rows_not_independent_recruitment_notices",
            "date_cells_verified": date_cells,
            "unscheduled_or_blank_date_cells": unscheduled_cells,
            "null_place_announcement_cells": self._null_place_announcement_cells,
            "date_cells_with_year_from_dataset_title": inferred_cells,
            "date_verification_scope": "calendar_validity_and_2026_year_not_independent_official_change_notice_review",
            "update_frequency": "annual_file_dataset",
            "next_year_verified": False,
            "samples": samples,
        }
