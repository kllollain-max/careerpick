import io
import json
import unittest
import urllib.error
import urllib.parse
from unittest.mock import patch

import mpm_exam


KEY = "MPM-TEST-KEY-abc+/="


def row(title="국가공무원 9급", stage="필기시험", **changes):
    value = {
        "시험명": title, "선발예정인원": "100", "원서접수기간": "2026-02-02~2026-02-06",
        "시험단계구분": stage, "시험장소공고일": "2026-03-27", "시험일": "2026-04-04",
        "합격자발표일": "2026-05-08",
    }
    value.update(changes)
    return value


def envelope(rows, **changes):
    value = {"page": 1, "perPage": 50, "totalCount": len(rows), "currentCount": len(rows), "matchCount": len(rows), "data": rows}
    value.update(changes)
    return value


class Response(io.BytesIO):
    status = 200

    def geturl(self):
        return mpm_exam.ENDPOINT


class FakeOpener:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.requests = []

    def open(self, request, **kwargs):
        self.requests.append(request)
        payload = next(self.payloads)
        if isinstance(payload, Exception):
            raise payload
        if isinstance(payload, bytes):
            return Response(payload)
        return Response(json.dumps(payload, ensure_ascii=False).encode())


class MPMExamTests(unittest.TestCase):
    def client(self, payloads, key=KEY):
        client = mpm_exam.Client(key)
        client._opener = FakeOpener(payloads)
        return client

    def assert_code(self, code, fn):
        with self.assertRaises(mpm_exam.APIError) as caught:
            fn()
        self.assertEqual(caught.exception.safe_code, code)
        self.assertNotIn(KEY, str(caught.exception))

    def test_complete_official_rows_keep_stage_and_exam_counts_distinct(self):
        rows = [row(), row(stage="면접시험", 시험일="2026-05-28~2026-06-02")]
        client = self.client([envelope(rows)])
        result = client.verify()
        self.assertTrue(result["authentication_verified"])
        self.assertEqual(result["received_rows"], 2)
        self.assertEqual(result["distinct_exam_names"], 1)
        self.assertEqual(client.success_counts, {"list": 1})
        self.assertEqual(result["date_cells_verified"], 8)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(client._opener.requests[0].full_url).query)
        self.assertEqual(query["serviceKey"], [KEY])

    def test_encoded_input_key_is_encoded_exactly_once(self):
        client = self.client([envelope([row()])], key=urllib.parse.quote(KEY, safe=""))
        client.verify()
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(client._opener.requests[0].full_url).query)
        self.assertEqual(query["serviceKey"], [KEY])

    def test_no_key_or_failed_auth_is_not_verified(self):
        self.assert_code("missing_key", lambda: mpm_exam.Client(""))
        error = urllib.error.HTTPError("https://example.invalid/?serviceKey=" + KEY, 401, KEY, {}, None)
        client = self.client([error])
        self.assert_code("http_401", client.verify)
        self.assertEqual(client.success_counts["list"], 0)

    def test_error_payload_and_wrong_columns_are_rejected(self):
        self.assert_code("invalid_envelope", self.client([{"code": -4, "msg": "Access denied"}]).verify)
        malformed = row()
        del malformed["합격자발표일"]
        self.assert_code("invalid_columns", self.client([envelope([malformed])]).verify)

    def test_runtime_type_diagnostic_is_values_free_and_does_not_relax_schema(self):
        client = self.client([envelope([
            row(선발예정인원=123456, 시험장소공고일=None),
            row(title="PRIVATE SOURCE VALUE", stage="면접시험"),
        ])])
        self.assert_code("invalid_field_type", client.verify)
        diagnostic = client.last_response_diagnostic
        self.assertEqual(diagnostic["field_types"]["선발예정인원"], ["int", "str"])
        self.assertEqual(diagnostic["field_types"]["시험장소공고일"], ["NoneType", "str"])
        self.assertEqual(set(diagnostic["field_types"]), set(mpm_exam.FIELDS))
        self.assertNotIn("123456", json.dumps(diagnostic))
        self.assertNotIn("PRIVATE SOURCE VALUE", json.dumps(diagnostic))
        self.assertNotIn(KEY, json.dumps(diagnostic))
        self.assertEqual(client.success_counts["list"], 0)

    def test_echo_is_rejected_before_any_response_diagnostic(self):
        client = self.client([envelope([row(시험명=KEY)])])
        self.assert_code("credential_echo", client.verify)
        self.assertIsNone(client.last_response_diagnostic)

    def test_counts_must_match_real_rows_and_requested_page(self):
        self.assert_code("invalid_counts", self.client([envelope([row()], currentCount=2)]).verify)
        self.assert_code("invalid_counts", self.client([envelope([row()], totalCount=True)]).verify)
        self.assert_code("pagination_mismatch", self.client([envelope([row()], page=2)]).verify)
        self.assert_code("total_count_mismatch", self.client([envelope([row()], matchCount=2)]).verify)

    def test_incomplete_or_oversized_collection_never_succeeds(self):
        self.assert_code("incomplete_dataset", self.client([envelope([row()], totalCount=2, matchCount=2)]).verify)
        self.assert_code("dataset_over_limit", self.client([envelope([row()], totalCount=101, matchCount=101)]).verify)

    def test_duplicate_rows_cannot_fill_missing_rows(self):
        self.assert_code("duplicate_rows", self.client([envelope([row(), row()])]).verify)

    def test_dates_validate_year_day_and_range_but_preserve_blanks(self):
        self.assert_code("unexpected_dataset_year", self.client([envelope([row(시험일="2025-04-04")])]).verify)
        self.assert_code("invalid_calendar_date", self.client([envelope([row(시험일="2026-02-30")])]).verify)
        self.assert_code("invalid_date_range", self.client([envelope([row(시험일="2026-06-02~2026-05-28")])]).verify)
        result = self.client([envelope([row(시험장소공고일="", 시험일="-")])]).verify()
        self.assertEqual(result["unscheduled_or_blank_date_cells"], 2)

    def test_month_day_dates_report_year_inference(self):
        result = self.client([envelope([row(시험일="4.4.")])]).verify()
        self.assertEqual(result["date_cells_with_year_from_dataset_title"], 1)
        self.assert_code("unverified_date_format", self.client([envelope([row(시험일="2026-04-04~99")])]).verify)

    def test_secret_echo_raw_encoded_and_json_escaped_is_blocked(self):
        for value in (KEY, urllib.parse.quote(KEY, safe=""), urllib.parse.quote(KEY, safe="").lower().replace("mpm-test-key-abc", "MPM-TEST-KEY-abc")):
            with self.subTest(value=value):
                self.assert_code("credential_echo", self.client([envelope([row(시험명=value)])]).verify)
        payload = json.dumps(envelope([row(시험명=KEY)])).replace("MPM", "\\u004dPM").encode()
        self.assert_code("credential_echo", self.client([payload]).verify)

    def test_redirect_handler_never_sends_key_to_another_host(self):
        handler = mpm_exam._NoRedirect()
        self.assert_code("redirect_blocked", lambda: handler.redirect_request(None, None, 302, "", {}, "https://evil.invalid/"))

    def test_bounded_size_and_safe_transport_errors(self):
        self.assert_code("response_too_large", self.client([b"x" * (mpm_exam.MAX_RESPONSE_BYTES + 1)]).verify)
        self.assert_code("request_failed", self.client([RuntimeError(KEY)]).verify)


if __name__ == "__main__":
    unittest.main()
