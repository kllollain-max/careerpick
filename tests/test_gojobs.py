import io
import unittest
import urllib.error
import urllib.parse
from xml.sax.saxutils import escape

import gojobs

KEY = "FIXTURE-KEY-never-export+/#=="


def row(identity, category="e01", **fields):
    values = {"idx": str(identity), "title": "지방공무원 채용", "insttname": "강원특별자치도",
              "type01": "g02", "type02": category, "enddate": "20261130",
              "regdate": "20261103", "moddate": "20261103", **fields}
    return "<item>" + "".join(f"<{name}>{escape(value)}</{name}>" for name, value in values.items()) + "</item>"


def list_xml(*rows, total=None, code="00"):
    total = len(rows) if total is None else total
    return (f"<response><header><resultCode>{code}</resultCode></header><body>"
            f"<totalCount>{total}</totalCount><numOfRows>5</numOfRows><pageNo>1</pageNo>"
            "<items>" + "".join(rows) + "</items></body></response>").encode()


def detail_xml(identity, category="e01", **fields):
    values = {"contents": "공고 본문", "link01": "https://www.gojobs.go.kr/apmView.do?menuNo=401&idx=" + str(identity), **fields}
    return ("<response><header><resultCode>00</resultCode></header><body>"
            + row(identity, category, **values)
            + "</body></response>").encode()


class Response(io.BytesIO):
    status = 200
    def __init__(self, data, url):
        super().__init__(data)
        self.url = url
    def geturl(self):
        return self.url


class Opener:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.requests = []
    def open(self, request, timeout):
        self.requests.append(request)
        value = next(self.payloads)
        if isinstance(value, Exception):
            raise value
        return Response(value, request.full_url)


class GOJOBSContractTests(unittest.TestCase):
    def client(self, *responses, key=KEY):
        client = gojobs.Client(key)
        client._opener = Opener(responses)
        return client

    def assert_code(self, code, callback):
        with self.assertRaises(gojobs.APIError) as context:
            callback()
        self.assertEqual(context.exception.safe_code, code)
        self.assertEqual(str(context.exception), code)
        self.assertNotIn(KEY, str(context.exception))

    def test_real_contract_queries_and_sample_only_summary(self):
        client = self.client(list_xml(row(1)), list_xml(row(2, "e02")), detail_xml(1), detail_xml(2, "e02"))
        result = client.verify()
        self.assertEqual(result["list_count_returned"], 2)
        self.assertEqual(result["detail_verified_count"], 2)
        self.assertFalse(result["full_collection"])
        self.assertEqual(result["requests"], {"list": 2, "detail": 2})
        self.assertEqual(result["successful_responses"], {"list": 2, "detail": 2})
        self.assertEqual(result["samples"][0]["deadline"], "2026-11-30")
        self.assertNotIn(KEY, str(result))
        for request in client._opener.requests:
            self.assertTrue(request.full_url.startswith(gojobs.BASE_URL + "/"))
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
            self.assertEqual(query["serviceKey"], [KEY])
        list_query = urllib.parse.parse_qs(urllib.parse.urlsplit(client._opener.requests[0].full_url).query)
        self.assertEqual(list_query["Pblanc_ty"], ["e01"])
        self.assertEqual(list_query["Instt_se"], ["g02"])

    def test_detail_limit_is_three_even_for_ten_list_rows(self):
        client = self.client(list_xml(*(row(i) for i in range(1, 6)), total=100),
                             list_xml(*(row(i, "e02") for i in range(6, 11)), total=200),
                             detail_xml(1), detail_xml(6, "e02"), detail_xml(2))
        result = client.verify()
        self.assertEqual(result["detail_verified_count"], 3)
        self.assertEqual(result["requests"], {"list": 2, "detail": 3})
        self.assertEqual([item["recruitment_type"] for item in result["detail_samples"]], ["e01", "e02", "e01"])
        self.assertEqual(result["total_count_by_filter"], {"e01": 100, "e02": 200})

    def test_empty_authentic_list_does_not_claim_details_verified(self):
        result = self.client(list_xml(), list_xml()).verify()
        self.assertTrue(result["list_verified"])
        self.assertFalse(result["detail_verified"])
        self.assertEqual(result["detail_verified_count"], 0)
        self.assertTrue(result["empty_list"])
        self.assertEqual(result["detail_status"], "unverified_empty_list")

    def test_auth_failure_is_not_http_success(self):
        client = self.client(list_xml(code="02"))
        self.assert_code("api_result_02", lambda: client.list_sample("e01"))
        self.assertEqual(client.success_counts, {"list": 0, "detail": 0})

    def test_gateway_http_error_preserves_only_safe_code(self):
        payload = b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
        error = urllib.error.HTTPError(gojobs.BASE_URL + "?serviceKey=" + KEY, 403, KEY, {}, io.BytesIO(payload))
        self.assert_code("gateway_30", lambda: self.client(error).list_sample("e01"))

    def test_credential_echo_raw_encoded_and_xml_entities_rejected(self):
        variants = (KEY, urllib.parse.quote(KEY, safe=""), urllib.parse.quote(urllib.parse.quote(KEY, safe=""), safe=""))
        for variant in variants:
            with self.subTest(variant_type=len(variant)):
                self.assert_code("credential_echo_rejected", lambda: self.client(list_xml(row(1, title=variant))).list_sample("e01"))
        encoded = "".join("&#" + str(ord(character)) + ";" for character in KEY)
        raw = list_xml(row(1)).replace("지방공무원 채용".encode(), encoded.encode())
        self.assert_code("credential_echo_rejected", lambda: self.client(raw).list_sample("e01"))

    def test_encoded_input_key_is_encoded_exactly_once(self):
        client = self.client(list_xml(row(1)), key=urllib.parse.quote(KEY, safe=""))
        client.list_sample("e01")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(client._opener.requests[0].full_url).query)
        self.assertEqual(query["serviceKey"], [KEY])

    def test_redirect_handler_blocks_without_contacting_redirect_target(self):
        self.assert_code("redirect_blocked", lambda: gojobs._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example/"))

    def test_wrong_detail_identity_is_rejected(self):
        self.assert_code("detail_identity_mismatch", lambda: self.client(detail_xml(2)).detail("1"))

    def test_mismatched_filters_duplicate_ids_and_partial_page_fail(self):
        samples = [(list_xml(row(1, type01="g01")), "filter_mismatch"),
                   (list_xml(row(1), row(1)), "duplicate_identifier"),
                   (list_xml(row(1), total=10), "sample_count_mismatch"),
                   (list_xml(row(1, enddate="20260230")), "invalid_date")]
        for payload, code in samples:
            with self.subTest(code=code):
                self.assert_code(code, lambda: self.client(payload).list_sample("e01"))

    def test_observed_reversed_fields_are_normalized_and_crosschecked(self):
        client = self.client(list_xml(row(1, type01="e01", type02="g02")),
                             list_xml(row(2, "e02", type01="e02", type02="g02")),
                             detail_xml(1, type01="e01", type02="g02"),
                             detail_xml(2, "e02", type01="e02", type02="g02"))
        result = client.verify()
        self.assertEqual(result["detail_verified_count"], 2)
        self.assertEqual(result["observed_field_layouts"], {
            "list": ["observed_type01_recruitment"],
            "detail": ["observed_type01_recruitment"]})
        self.assertEqual([item["recruitment_type"] for item in result["samples"]], ["e01", "e02"])
        self.assertTrue(all(item["institution_type"] == "g02" for item in result["detail_samples"]))

    def test_semantically_equal_different_list_detail_layouts_are_allowed(self):
        client = self.client(list_xml(row(1, type01="e01", type02="g02")),
                             list_xml(), detail_xml(1))
        result = client.verify()
        self.assertEqual(result["observed_field_layouts"], {
            "list": ["observed_type01_recruitment"],
            "detail": ["documented_type01_institution"]})

    def test_filter_diagnostic_is_allowlisted_without_relaxing_validation(self):
        client = self.client(list_xml(row(1, type01="e01", type02="g01")))
        self.assert_code("filter_mismatch", lambda: client.list_sample("e01"))
        self.assertEqual(client.last_response_diagnostic, {"observed_filters": {
            "requested": {"Pblanc_ty": "e01", "Instt_se": "g02"},
            "type01": "e01", "type02": "g01"}})
        for first, second in (("RAW_TEXT", "g02"), ("e01", "e02"), ("g01", "g02")):
            with self.subTest(first=first, second=second):
                client = self.client(list_xml(row(1, type01=first, type02=second)))
                self.assert_code("invalid_classification_pair", lambda: client.list_sample("e01"))
                self.assertNotIn("RAW_TEXT", str(client.last_response_diagnostic))
                self.assertEqual(client.success_counts["list"], 0)

    def test_normalized_detail_still_must_match_requested_list_category(self):
        client = self.client(list_xml(row(1, type01="e01", type02="g02")), list_xml(),
                             detail_xml(1, type01="e02", type02="g02"))
        self.assert_code("detail_list_mismatch", client.verify)

    def test_dtd_and_large_responses_rejected(self):
        self.assert_code("unsafe_xml_declaration", lambda: self.client(b'<!DOCTYPE response [<!ENTITY x "bad">]>' + list_xml()).list_sample("e01"))
        self.assert_code("response_too_large", lambda: self.client(b"x" * (gojobs.MAX_BYTES + 1)).list_sample("e01"))

    def test_optional_unusable_links_do_not_hide_valid_detail(self):
        client = self.client(list_xml(row(1)), list_xml(),
                             detail_xml(1, link01="/RAW_PRIVATE_REFERENCE", link02="javascript:RAW_PRIVATE_REFERENCE",
                                        link03="https://agency.go.kr/recruit/123"))
        result = client.verify()
        self.assertTrue(result["detail_verified"])
        self.assertEqual(result["detail_verified_count"], 1)
        self.assertEqual(result["source_link_counts"], {"validated": 1, "not_provided": 0, "unverified": 2})
        self.assertFalse(result["source_links_all_validated"])
        detail = result["detail_samples"][0]
        self.assertEqual(detail["source_links"], ["https://agency.go.kr/recruit/123"])
        self.assertEqual(detail["source_link_status"], {
            "link01": "relative_reference", "link02": "unsupported_scheme", "link03": "validated_http_url"})
        self.assertNotIn("RAW_PRIVATE_REFERENCE", str(result))
        self.assertTrue(detail["content_present"])

    def test_unusable_link_classifications_never_return_raw_values(self):
        samples = [("", "not_provided"), ("bad-reference", "schemeless_reference"),
                   ("https://", "invalid_url"), ("https://name:pass@agency.go.kr", "credential_component_rejected"),
                   ("https://agency.go.kr:BAD", "invalid_url"), ("https://agency.go.kr/a\nb", "invalid_url")]
        for value, status in samples:
            with self.subTest(status=status):
                self.assertEqual(gojobs._public_link(value), (None, status))

    def test_optional_link_policy_does_not_weaken_essential_detail_or_key_checks(self):
        self.assert_code("detail_identity_mismatch", lambda: self.client(detail_xml(2, link01="/bad")).detail("1"))
        self.assert_code("invalid_title", lambda: self.client(detail_xml(1, title="", link01="/bad")).detail("1"))
        self.assert_code("credential_echo_rejected", lambda: self.client(detail_xml(1, link01="/" + KEY)).detail("1"))

    def test_transport_exception_never_includes_credential(self):
        self.assert_code("transport_error", lambda: self.client(RuntimeError(KEY)).list_sample("e01"))


if __name__ == "__main__":
    unittest.main()
