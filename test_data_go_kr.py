import io
import json
import unittest
import urllib.error
import urllib.parse
from unittest.mock import Mock, patch

from data_go_kr import APIError, BASE_URL, Client, _NoRedirect


def notice(identity):
    return {"recrutPblntSn": identity, "recrutPbancTtl": "공고", "files": [], "steps": []}


def listing(total, rows, code=0):
    return {"resultCode": code, "resultMsg": "정상", "totalCount": total, "result": rows}


class DataGoKrTest(unittest.TestCase):
    def client(self, responses=(), key="private+key/value="):
        opener = Mock()
        def reply(*args, **kwargs):
            response = next(iterator)
            if isinstance(response, Exception):
                raise response
            body = response if isinstance(response, bytes) else json.dumps(response).encode()
            return io.BytesIO(body)
        iterator = iter(responses)
        opener.open.side_effect = reply
        with patch("data_go_kr.urllib.request.build_opener", return_value=opener):
            client = Client(key)
        return client, opener

    def assert_code(self, code, action):
        with self.assertRaises(APIError) as caught:
            action()
        self.assertEqual(str(caught.exception), code)
        return caught.exception

    def test_fixed_get_routes_encoding_and_detail_preservation(self):
        full_detail = {**notice(123), "files": [{"fileNm": "안내.pdf", "fileUrl": "https://example.org/a.pdf"}],
                       "steps": [{"stepNm": "서류전형"}]}
        for key in ("private+key/value=", "private%2Bkey%2Fvalue%3D"):
            with self.subTest(key_format="encoded" if "%" in key else "decoded"):
                client, opener = self.client([listing(1, [notice(123)], code=200),
                    {"resultCode": "0", "result": full_detail}], key)
                self.assertEqual(client.list_page(1)["result"], [notice(123)])
                self.assertEqual(client.detail("123"), full_detail)
                for call in opener.open.call_args_list:
                    request = call.args[0]
                    parsed = urllib.parse.urlsplit(request.full_url)
                    query = urllib.parse.parse_qs(parsed.query)
                    self.assertEqual(request.method, "GET")
                    self.assertIsNone(request.data)
                    self.assertEqual(query["serviceKey"], ["private+key/value="])
                    self.assertEqual(query["resultType"], ["json"])
                    self.assertEqual(call.kwargs["timeout"], 30)
                    self.assertTrue(request.full_url.startswith(BASE_URL + "/"))
                first = urllib.parse.parse_qs(urllib.parse.urlsplit(opener.open.call_args_list[0].args[0].full_url).query)
                last = urllib.parse.parse_qs(urllib.parse.urlsplit(opener.open.call_args_list[1].args[0].full_url).query)
                self.assertEqual(first["ongoingYn"], ["Y"])
                self.assertEqual(first["numOfRows"], ["100"])
                self.assertEqual(last["sn"], ["123"])
                self.assertEqual(client.request_counts, {"list": 1, "detail": 1})
                self.assertEqual(client.success_counts, {"list": 1, "detail": 1})

    def test_official_item_wrappers_are_normalized(self):
        for result in ([{"item": notice(123)}], {"item": [notice(123)]}, {"item": notice(123)}):
            with self.subTest(shape=type(result).__name__):
                client, _ = self.client([listing("1", result), {"resultCode": 200, "result": {"item": notice(123)}}])
                self.assertEqual(client.list_page(1)["result"], [notice(123)])
                self.assertEqual(client.detail(123), notice(123))

    def test_bad_input_makes_no_request(self):
        for key, expected in (("", "missing_key"), ("  ", "missing_key"), (None, "invalid_key")):
            self.assert_code(expected, lambda key=key: Client(key))
        client, opener = self.client([])
        for page in (0, 11, -1, True, "1"):
            self.assert_code("invalid_page", lambda page=page: client.list_page(page))
        for identity in (None, True, 0, -1, 1.5, "123?serviceKey=other", "١٢٣"):
            self.assert_code("invalid_notice_id", lambda identity=identity: client.detail(identity))
        opener.open.assert_not_called()

    def test_http_transport_and_response_errors_do_not_reveal_key(self):
        secret = "THIS_IS_PRIVATE"
        failures = [
            (urllib.error.HTTPError(BASE_URL + "/list?serviceKey=" + secret, 401, secret, {}, io.BytesIO(secret.encode())), "http_status_401"),
            (urllib.error.URLError(secret), "transport_failed"),
            (TimeoutError(secret), "transport_failed"),
            (("<html>" + secret + "</html>").encode(), "invalid_json"),
            ({"resultCode": secret, "result": []}, "api_response_error"),
        ]
        for failure, expected in failures:
            with self.subTest(error=expected):
                client, opener = self.client([failure], key=secret)
                error = self.assert_code(expected, lambda: client.list_page(1))
                self.assertNotIn(secret, str(error))
                self.assertNotIn(secret, repr(error))
                self.assertEqual(opener.open.call_count, 1)
                self.assertEqual(client.request_counts["list"], 1)
                self.assertEqual(client.success_counts["list"], 0)

    def test_redirects_are_rejected_without_followup(self):
        self.assert_code("redirect_rejected", lambda: _NoRedirect().redirect_request(
            None, None, 302, "redirect", {}, "https://other.example/?serviceKey=PRIVATE"))
        error = urllib.error.HTTPError(BASE_URL + "/list", 302, "redirect", {}, None)
        client, opener = self.client([error])
        self.assert_code("redirect_rejected", lambda: client.list_page(1))
        self.assertEqual(opener.open.call_count, 1)

    def test_http_gateway_diagnostics_allow_only_official_tokens(self):
        secret = "DO_NOT_LOG_THIS_CREDENTIAL"
        body = ("<OpenAPI_ServiceResponse><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
                "</returnAuthMsg><request>" + secret + "</request></OpenAPI_ServiceResponse>").encode()
        failure = urllib.error.HTTPError(BASE_URL + "/list?serviceKey=" + secret, 403,
                                         secret, {}, io.BytesIO(body))
        client, _ = self.client([failure], key=secret)
        self.assert_code("gateway_SERVICE_KEY_IS_NOT_REGISTERED_ERROR", lambda: client.list_page(1))
        self.assertEqual(client.last_http_error["http_status"], 403)
        self.assertEqual(client.last_http_error["gateway_code"], "30")
        self.assertNotIn(secret, json.dumps(client.last_http_error))

    def test_official_no_data_error_may_include_extra_diagnostics(self):
        client, _ = self.client([{"resultCode": 3, "result": None, "error": "PRIVATE"}])
        self.assert_code("api_result_3", lambda: client.detail(123))
        self.assertEqual(client.last_response_diagnostic["result_code"], "3")
        self.assertNotIn("PRIVATE", json.dumps(client.last_response_diagnostic))

    def test_malformed_envelopes_and_rows_fail_closed(self):
        samples = [
            ([], "invalid_envelope"),
            ({"result": []}, "invalid_envelope"),
            ({"resultCode": 0, "result": []}, "invalid_total_count"),
            (listing(-1, []), "invalid_total_count"),
            (listing(True, []), "invalid_total_count"),
            (listing(1.5, []), "invalid_total_count"),
            (listing(1, None), "invalid_list_shape"),
            (listing(1, ["invalid"]), "invalid_list_shape"),
            (listing(1, [{"title": "missing ID"}]), "invalid_notice_id"),
            (listing(1, {"item": [notice(1)], "unexpected": []}), "invalid_item_wrapper"),
            ({**listing(1, [notice(1)]), "unexpected": "PRIVATE"}, "unexpected_envelope_fields"),
            (listing(0, [notice(1)]), "excess_records"),
            (listing(2, [notice(1), notice("01")]), "duplicate_notice_id"),
            (listing(101, [notice(i) for i in range(1, 102)]), "too_many_page_rows"),
            ({"resultCode": 7, "resultMsg": "PRIVATE", "result": []}, "api_result_7"),
        ]
        for payload, expected in samples:
            with self.subTest(expected=expected):
                client, _ = self.client([payload])
                self.assert_code(expected, lambda: client.list_page(1))
                self.assertEqual(client.success_counts["list"], 0)

    def test_detail_identity_and_shape_are_required(self):
        samples = [
            ([notice(123)], "invalid_detail_shape"),
            (notice(124), "detail_identity_mismatch"),
            ({"files": []}, "invalid_notice_id"),
            ({"item": notice(123), "unexpected": True}, "invalid_item_wrapper"),
        ]
        for result, expected in samples:
            with self.subTest(expected=expected):
                client, _ = self.client([{"resultCode": 0, "result": result}])
                self.assert_code(expected, lambda: client.detail(123))
                self.assertEqual(client.request_counts["detail"], 1)
                self.assertEqual(client.success_counts["detail"], 0)

    def test_complete_pagination_has_exact_ids_and_counts(self):
        first = [notice(i) for i in range(1, 101)]
        client, opener = self.client([listing(101, first), listing(101, [notice(101)])])
        result = client.collect_list()
        self.assertEqual([row["recrutPblntSn"] for row in result], list(range(1, 102)))
        self.assertEqual(client.request_counts, {"list": 2, "detail": 0})
        self.assertEqual(client.success_counts, {"list": 2, "detail": 0})
        self.assertEqual(opener.open.call_count, 2)

    def test_duplicate_changed_truncated_and_extra_pages_fail(self):
        first = [notice(i) for i in range(1, 101)]
        samples = [
            (listing(101, [notice(1)]), "duplicate_notice_id"),
            (listing(102, [notice(101), notice(102)]), "count_changed"),
            (listing(101, []), "incomplete_page"),
            (listing(101, [notice(101), notice(102)]), "excess_records"),
        ]
        for second, expected in samples:
            with self.subTest(expected=expected):
                client, opener = self.client([listing(101, first), second])
                self.assert_code(expected, client.collect_list)
                self.assertEqual(opener.open.call_count, 2)

    def test_empty_short_and_over_cap_lists_stop_immediately(self):
        samples = [
            (listing(0, []), "empty_list"),
            (listing(101, [notice(i) for i in range(1, 100)]), "incomplete_page"),
            (listing(1001, [notice(i) for i in range(1, 101)]), "page_limit_exceeded"),
        ]
        for payload, expected in samples:
            with self.subTest(expected=expected):
                client, opener = self.client([payload])
                self.assert_code(expected, client.collect_list)
                self.assertEqual(opener.open.call_count, 1)
        client, _ = self.client([listing(0, [])])
        self.assertEqual(client.list_page(1), {"totalCount": 0, "result": []})


if __name__ == "__main__":
    unittest.main()
