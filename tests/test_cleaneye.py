"""Synthetic fixtures follow published 15159757 XML fields, not live evidence."""

import io
import json
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
from xml.sax.saxutils import escape

import cleaneye


KEY = "CLEANEYE-fixture-credential+/=="


def row(identity="source-1", **fields):
    values = {
        "NO": identity, "ENT_NAME": "테스트 공공기관", "ENT_TITLE": "테스트 채용",
        "SIDO_CD": "확인되지 않은 원문 지역", "JOB_TYPE": "원문 고용형태",
        "STATUS": "원문 상태", "PUB_DATE": "2026-11-01", "PUB_END_DATE": "2026-11-30",
        "FILE_NAME1": "공고문.hwp", **fields,
    }
    return "<item>" + "".join(
        f"<{name}>{escape(value)}</{name}>" for name, value in values.items()
    ) + "</item>"


def xml(*rows, total=None, code="0", layout="standard"):
    total = len(rows) if total is None else total
    head, body = ("header", "body") if layout == "standard" else (
        "openXmlEmployInfo-header", "openXmlEmployInfo-body")
    return (
        f"<response><{head}><resultCode>{escape(str(code))}</resultCode>"
        f"<resultMsg>정상</resultMsg></{head}><{body}><totalCount>{total}</totalCount>"
        "<items>" + "".join(rows) + f"</items></{body}></response>"
    ).encode()


def no_data_xml(body=None, layout="documented"):
    head, body_tag = ("header", "body") if layout == "standard" else (
        "openXmlEmployInfo-header", "openXmlEmployInfo-body")
    body_xml = "" if body is None else f"<{body_tag}>{body}</{body_tag}>"
    return (
        f"<response><{head}><resultCode>3</resultCode>"
        f"<resultMsg>NONOTEXISTDATA_ERROR</resultMsg></{head}>{body_xml}</response>"
    ).encode()


def region_row(code, name="테스트 지역", number="1"):
    return ("<item><No>" + escape(number) + "</No><SIDO_CD>" + escape(code)
            + "</SIDO_CD><SIDO_NAME>" + escape(name) + "</SIDO_NAME></item>")


def regions_xml(*rows, total=None, page=1, page_size=None):
    total = len(rows) if total is None else total
    page_size = cleaneye.REGION_PAGE_SIZE if page_size is None else page_size
    return (
        "<response><openXmlSidoCd-header><resultCode>0</resultCode>"
        "<resultMsg>정상</resultMsg></openXmlSidoCd-header><openXmlSidoCd-body>"
        f"<totalCount>{total}</totalCount><numOfRows>{page_size}</numOfRows>"
        f"<pageNo>{page}</pageNo><items>" + "".join(rows)
        + "</items></openXmlSidoCd-body></response>"
    ).encode()


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, url):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.final_url = None

    def open(self, request, timeout):
        self.requests.append(request)
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return Response(value, self.final_url or request.full_url)


class CleaneyeContractTests(unittest.TestCase):
    def client(self, *responses, key=KEY):
        client = cleaneye.Client(key)
        client._opener = Opener(responses)
        return client

    def assert_code(self, expected, operation):
        with self.assertRaises(cleaneye.APIError) as context:
            operation()
        self.assertEqual(context.exception.safe_code, expected)
        self.assertEqual(str(context.exception), expected)
        self.assertNotIn(KEY, str(context.exception))

    def test_exact_documented_request_preserves_plus_and_has_no_guessed_pagination(self):
        for key in (KEY, urllib.parse.quote(KEY, safe="")):
            with self.subTest(encoded=(key != KEY)):
                client = self.client(xml(row()), key=key)
                result = client.list_region("001")
                request = client._opener.requests[0]
                url = urllib.parse.urlsplit(request.full_url)
                self.assertEqual(url.scheme, "https")
                self.assertEqual(url.netloc, "apis.data.go.kr")
                self.assertEqual(url.path, "/B551982/openApiEmployInfo/openXmlEmployInfo")
                self.assertEqual(request.method, "GET")
                self.assertEqual(urllib.parse.parse_qs(url.query), {
                    "serviceKey": [KEY], "sidoCd": ["001"], "type": ["xml"],
                })
                self.assertEqual(result["totalCount"], 1)
                self.assertEqual(result["result"][0]["NO"], "source-1")
                self.assertEqual(result["result"][0]["JOB_TYPE"], "원문 고용형태")
                self.assertEqual(result["result"][0]["FILE_NAME1"], "공고문.hwp")
                self.assertEqual(client.request_counts, {"list": 1})
                self.assertEqual(client.success_counts, {"list": 1})
                self.assertFalse(client.collection_complete)

    def test_both_explicit_envelopes_and_xml_namespaces(self):
        for layout in ("standard", "documented"):
            payload = xml(row(), layout=layout).replace(
                b"<response>", b'<response xmlns="urn:official-test">')
            client = self.client(payload)
            result = client.list_region("001")
            self.assertEqual(len(result["result"]), 1)
            self.assertEqual(client.last_response_diagnostic["envelope_layout"], layout)

    def test_complete_regions_allow_local_zero_and_expose_counts_only(self):
        client = self.client(xml(row("a")), xml(), xml(row("b"), row("c")))
        result = client.collect_list(sido_codes=["001", "002", "003"])
        self.assertEqual([record["NO"] for record in result], ["a", "b", "c"])
        self.assertEqual(client.region_counts, {"001": 1, "002": 0, "003": 2})
        self.assertEqual(client.request_counts, {"list": 3})
        self.assertTrue(client.collection_complete)
        self.assertNotIn(KEY, json.dumps(client.last_response_diagnostic))

    def test_early_or_late_partial_result_never_completes_collection(self):
        for first in (True, False):
            with self.subTest(first=first):
                responses = [xml(row("a"), total=2)] if first else [xml(row("a")), xml(total=1)]
                client = self.client(*responses)
                self.assert_code("incomplete_collection", lambda: client.collect_list(sido_codes=["001", "002"]))
                self.assertFalse(client.collection_complete)
                self.assertEqual(client.success_counts["list"], 0 if first else 1)
                self.assertEqual(client.region_counts, {} if first else {"001": 1})

    def test_count_excess_invalid_count_and_count_limits(self):
        for payload, code in (
            (xml(row(), total=0), "excess_records"),
            (xml(total="-1"), "invalid_total_count"),
            (xml(total="1.5"), "invalid_total_count"),
            (xml(total=cleaneye.MAX_REGION_RECORDS + 1), "region_record_limit_exceeded"),
        ):
            with self.subTest(code=code):
                self.assert_code(code, lambda: self.client(payload).list_region("001"))
        with patch.object(cleaneye, "MAX_TOTAL_RECORDS", 1):
            client = self.client(xml(row("a")), xml(row("b")))
            self.assert_code("record_limit_exceeded", lambda: client.collect_list(sido_codes=["001", "002"]))
            self.assertFalse(client.collection_complete)

    def test_duplicate_source_ids_within_and_across_regions_are_errors(self):
        self.assert_code("duplicate_notice_id", lambda: self.client(xml(row(), row())).list_region("001"))
        client = self.client(xml(row()), xml(row()))
        self.assert_code("duplicate_notice_id_across_regions", lambda: client.collect_list(sido_codes=["001", "002"]))
        self.assertFalse(client.collection_complete)

    def test_empty_national_collection_cannot_replace_saved_data(self):
        client = self.client(xml(), xml())
        self.assert_code("empty_list", lambda: client.collect_list(sido_codes=["001", "002"]))
        self.assertFalse(client.collection_complete)

    def test_bad_region_sets_are_rejected_before_any_network_request(self):
        for values, code in (
            ([], "missing_regions"), (None, "missing_regions"), ("001", "missing_regions"),
            (["001", "001"], "duplicate_region"), (["001", "bad\ncode"], "invalid_region"),
            (["001", ""], "invalid_region"), (["001", "  "], "invalid_region"),
            (["001", "x" * 129], "invalid_region"), (["001", "x\x7f"], "invalid_region"),
            (["001", 2], "invalid_region"), ([str(i) for i in range(33)], "region_limit_exceeded"),
        ):
            with self.subTest(code=code):
                client = self.client()
                with patch.object(client, "_fetch", side_effect=AssertionError("unexpected_request")) as fetch:
                    self.assert_code(code, lambda: client.collect_list(sido_codes=values))
                    fetch.assert_not_called()
                self.assertEqual(client.request_counts, {"list": 0})

    def test_second_collection_clears_previous_success_and_region_counts(self):
        client = self.client(xml(row()))
        client.collect_list(sido_codes=["001"])
        client._opener = Opener([xml(total=1)])
        self.assert_code("incomplete_collection", lambda: client.collect_list(sido_codes=["002"]))
        self.assertFalse(client.collection_complete)
        self.assertEqual(client.region_counts, {})

    def test_transport_errors_and_unknown_error_codes_are_sanitized(self):
        error = urllib.error.URLError("private url?serviceKey=" + KEY)
        self.assert_code("transport_failed", lambda: self.client(error).list_region("001"))
        self.assert_code("internal_error", lambda: (_ for _ in ()).throw(cleaneye.APIError(KEY)))
        self.assert_code("api_response_error", lambda: self.client(xml(code="untrusted-code")).list_region("001"))

    def test_header_only_no_data_is_a_regional_zero_but_success_still_needs_a_body(self):
        # Run 42336052565 observed the header-only code/message for region 007005.
        payload = no_data_xml()
        client = self.client(payload)
        self.assertEqual(client.list_region("001"), {"totalCount": 0, "result": []})
        self.assertEqual(client.success_counts, {"list": 1})
        self.assertEqual(client.region_counts, {"001": 0})
        self.assertFalse(client.collection_complete)
        self.assert_code("invalid_body", lambda: self.client(
            payload.replace(b"<resultCode>3", b"<resultCode>0")
        ).list_region("001"))

    def test_no_data_accepts_only_empty_optional_bodies_in_supported_envelopes(self):
        for layout in ("standard", "documented"):
            for body in (None, "", "<items/>", "<totalCount>0</totalCount>",
                         "<totalCount>0</totalCount><items/>"):
                with self.subTest(layout=layout, body=body):
                    payload = no_data_xml(body, layout).replace(
                        b"<response>", b'<response xmlns="urn:official-test">')
                    client = self.client(payload)
                    self.assertEqual(client.list_region("001"), {"totalCount": 0, "result": []})
                    self.assertEqual(client.last_response_diagnostic["total_count"], 0)

    def test_code_three_requires_the_exact_observed_no_data_message(self):
        payloads = [no_data_xml().replace(
            b"<resultMsg>NONOTEXISTDATA_ERROR</resultMsg>", b"")]
        payloads.extend(no_data_xml().replace(b"NONOTEXISTDATA_ERROR", message.encode())
                        for message in ("", "NOTEXISTDATA_ERROR", "unknown error",
                                        "SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "nonotexistdata_error"))
        for payload in payloads:
            with self.subTest(payload=payload):
                client = self.client(payload)
                self.assert_code("api_result_3", lambda: client.list_region("001"))
                self.assertEqual(client.success_counts, {"list": 0})
                self.assertEqual(client.region_counts, {})
                self.assertIsNone(client.last_response_diagnostic)

    def test_no_data_rejects_nonempty_contradictory_or_malformed_bodies(self):
        for body, code in (
            ("<totalCount>1</totalCount><items/>", "invalid_no_data_response"),
            ("<totalCount>0</totalCount><items>" + row() + "</items>", "invalid_no_data_response"),
            ("<items><item/></items>", "invalid_no_data_response"),
            ("<items>unstructured result</items>", "invalid_no_data_response"),
            ("unexpected result text", "invalid_no_data_response"),
            ("<items/>unexpected result text", "invalid_no_data_response"),
            ("<totalCount>-1</totalCount>", "invalid_total_count"),
            ("<totalCount></totalCount>", "invalid_xml_field"),
            ("<totalCount>0</totalCount><totalCount>0</totalCount>", "duplicate_xml_field"),
            ("<items/><items/>", "duplicate_xml_field"),
            ("<unexpected/>", "unexpected_body_field"),
        ):
            with self.subTest(body=body):
                client = self.client(no_data_xml(body))
                self.assert_code(code, lambda: client.list_region("001"))
                self.assertEqual(client.success_counts, {"list": 0})
                self.assertEqual(client.region_counts, {})
                self.assertIsNone(client.last_response_diagnostic)

    def test_no_data_region_does_not_stop_the_remaining_seventeen_region_collection(self):
        codes = [f"fixture-region-{index}" for index in range(17)]
        responses = [no_data_xml() if index == 4 else xml(row(f"notice-{index}"))
                     for index in range(17)]
        client = self.client(*responses)
        records = client.collect_list(sido_codes=codes)
        self.assertEqual(len(records), 16)
        self.assertEqual(client.region_counts, {code: 0 if index == 4 else 1
                                               for index, code in enumerate(codes)})
        self.assertEqual(sum(client.region_counts.values()), len(records))
        self.assertEqual(client.request_counts, {"list": 17})
        self.assertEqual(client.success_counts, {"list": 17})
        self.assertTrue(client.collection_complete)
        self.assertEqual([urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)["sidoCd"][0]
                          for request in client._opener.requests], codes)

    def test_all_no_data_regions_still_cannot_complete_an_empty_collection(self):
        codes = [f"fixture-region-{index}" for index in range(17)]
        client = self.client(*(no_data_xml() for _ in codes))
        self.assert_code("empty_list", lambda: client.collect_list(sido_codes=codes))
        self.assertEqual(client.region_counts, dict.fromkeys(codes, 0))
        self.assertEqual(client.success_counts, {"list": 17})
        self.assertFalse(client.collection_complete)

    def test_no_data_does_not_mask_a_later_partial_response(self):
        client = self.client(xml(row()), no_data_xml(), xml(total=1))
        self.assert_code("incomplete_collection", lambda: client.collect_list(sido_codes=["001", "002", "003"]))
        self.assertEqual(client.success_counts, {"list": 2})
        self.assertEqual(client.region_counts, {"001": 1, "002": 0})
        self.assertFalse(client.collection_complete)

    def test_no_data_exception_does_not_apply_to_other_errors_or_region_code_lookup(self):
        for code in ("1", "03", "30"):
            with self.subTest(code=code):
                payload = no_data_xml().replace(b"<resultCode>3", ("<resultCode>" + code).encode())
                self.assert_code("api_result_" + code, lambda: self.client(payload).list_region("001"))
        region_payload = regions_xml().replace(b"<resultCode>0", b"<resultCode>3")
        client = self.client(region_payload)
        self.assert_code("api_result_3", lambda: client.collect_region_codes(ac_year=2026))
        self.assertFalse(client.region_code_metadata["complete"])
        self.assertEqual(client.success_counts["region_codes"], 0)
        error = urllib.error.HTTPError("https://apis.data.go.kr", 403, "", {}, io.BytesIO(no_data_xml()))
        self.assert_code("api_result_3", lambda: self.client(error).list_region("001"))

    def test_credential_echo_raw_encoded_and_entity_forms_are_rejected(self):
        variants = [KEY]
        for _ in range(3):
            variants.append(urllib.parse.quote(variants[-1], safe=""))
        for variant in variants:
            with self.subTest(length=len(variant)):
                self.assert_code("credential_echo_rejected", lambda: self.client(xml(row(ENT_TITLE=variant))).list_region("001"))
        encoded = "".join(f"&#{ord(c)};" for c in KEY).encode()
        for payload in (
            xml(row()).replace("테스트 채용".encode(), encoded),
            xml(row()).replace(b"<item>", b'<item note="' + encoded + b'">'),
        ):
            self.assert_code("credential_echo_rejected", lambda: self.client(payload).list_region("001"))

    def test_http_error_diagnostic_allows_only_known_codes_and_no_response_body(self):
        gateway = b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
        for payload, code in (
            (gateway, "gateway_30"),
            (b"SERVICE_ACCESS_DENIED_ERROR", "gateway_SERVICE_ACCESS_DENIED_ERROR"),
            (b"private error detail", "http_status_403"),
            (KEY.encode(), "credential_echo_rejected"),
        ):
            with self.subTest(code=code):
                error = urllib.error.HTTPError("https://apis.data.go.kr/?serviceKey=" + KEY, 403, KEY, {}, io.BytesIO(payload))
                client = self.client(error)
                self.assert_code(code, lambda: client.list_region("001"))
                self.assertIsNone(client.last_response_diagnostic)
                self.assertEqual(client.success_counts, {"list": 0})

    def test_redirect_handler_http_redirect_and_changed_final_url_fail_closed(self):
        self.assert_code("redirect_rejected", lambda: cleaneye._NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))
        redirect = urllib.error.HTTPError("https://apis.data.go.kr", 302, "redirect", {}, io.BytesIO())
        self.assert_code("redirect_rejected", lambda: self.client(redirect).list_region("001"))
        for target in ("https://other.example", "http://apis.data.go.kr/B551982/openApiEmployInfo/openXmlEmployInfo"):
            client = self.client(xml(row()))
            client._opener.final_url = target
            self.assert_code("redirect_rejected", lambda: client.list_region("001"))

    def test_unsafe_xml_and_response_byte_limit(self):
        for payload, code in (
            (b'<!DOCTYPE response [<!ENTITY x "boom">]>' + xml(row()), "unsafe_xml_declaration"),
            (b"\xff", "invalid_response_encoding"),
            (b"not XML", "invalid_xml"),
            (b"<wrong/>", "invalid_envelope"),
        ):
            with self.subTest(code=code):
                self.assert_code(code, lambda: self.client(payload).list_region("001"))
        with patch.object(cleaneye, "MAX_RESPONSE_BYTES", 128):
            self.assert_code("response_too_large", lambda: self.client(b"x" * 129).list_region("001"))

    def test_duplicate_or_unknown_fields_cannot_be_silently_discarded(self):
        for payload, code in (
            (xml(row()).replace(b"</item>", b"<NO>other</NO></item>"), "duplicate_xml_field"),
            (xml(row()).replace(b"</item>", b"<UNKNOWN>untrusted</UNKNOWN></item>"), "unexpected_record_field"),
            (xml(row()).replace(b"</body>", b"<pageNo>1</pageNo></body>"), "unexpected_body_field"),
            (xml(row()).replace(b"</header>", b"</header><header/>"), "invalid_envelope"),
            (xml(row(ENT_NAME="")), "invalid_record"),
            (xml(row()).replace(b"<NO>source-1</NO>", b"<NO><nested/></NO>"), "invalid_xml_field"),
        ):
            with self.subTest(code=code):
                self.assert_code(code, lambda: self.client(payload).list_region("001"))

    def test_oversized_field_and_aggregate_text_are_bounded(self):
        self.assert_code("record_field_too_large", lambda: self.client(xml(row(ENT_TITLE="x" * 4_001))).list_region("001"))
        with patch.object(cleaneye, "MAX_COLLECTION_TEXT_CHARS", 1):
            client = self.client(xml(row()))
            self.assert_code("collection_too_large", lambda: client.collect_list(sido_codes=["001"]))
            self.assertFalse(client.collection_complete)

    def test_source_identifier_fits_existing_backup_id_limit_without_truncation(self):
        record = self.client(xml(row("a" * 119))).list_region("001")["result"][0]
        self.assertEqual(record["NO"], "a" * 119)
        self.assertEqual(len("cleaneye-" + record["NO"]), 128)
        self.assert_code("record_field_too_large", lambda: self.client(
            xml(row("a" * 120))
        ).list_region("001"))

    def test_malformed_keys_never_start_a_request(self):
        for key, code in ((None, "invalid_key"), (" ", "missing_key"), ("a%FF", "invalid_key"), ("a%0Ab", "invalid_key")):
            with self.subTest(code=code):
                self.assert_code(code, lambda: cleaneye.Client(key))

    def test_official_region_mapping_keeps_opaque_codes_and_names_with_provenance(self):
        code = " code+한/ ?&=value%2B "
        client = self.client(regions_xml(region_row(code, "테스트 지역 A")), xml(row()))
        mapping = client.collect_region_codes(ac_year=2026)
        self.assertEqual(mapping, {code: "테스트 지역 A"})
        self.assertEqual(client.region_code_mapping, mapping)
        self.assertEqual(client.region_code_metadata, {
            "source_url": cleaneye.REGION_SOURCE_URL, "reference_year": 2026,
            "total_count": 1, "pages": 1, "complete": True,
        })
        request = client._opener.requests[0]
        url = urllib.parse.urlsplit(request.full_url)
        self.assertEqual((url.scheme, url.netloc, url.path), (
            "https", "apis.data.go.kr", "/B551982/openApiSidoCd3/openXmlSidoCd2"))
        self.assertEqual(urllib.parse.parse_qs(url.query), {
            "serviceKey": [KEY], "pageNo": ["1"], "numOfRows": ["300"],
            "type": ["xml"], "ac_year": ["2026"],
        })
        client.collect_list(sido_codes=list(mapping))
        employment_query = urllib.parse.parse_qs(urllib.parse.urlsplit(
            client._opener.requests[1].full_url).query)
        self.assertEqual(employment_query, {"serviceKey": [KEY], "sidoCd": [code], "type": ["xml"]})
        self.assertTrue(client.collection_complete)
        self.assertEqual(client.request_counts, {"list": 1, "region_codes": 1})
        self.assertEqual(client.success_counts, {"list": 1, "region_codes": 1})

    def test_region_pagination_requires_complete_stable_unique_results(self):
        with patch.object(cleaneye, "REGION_PAGE_SIZE", 2):
            client = self.client(
                regions_xml(region_row("A", "지역 A"), region_row("B", "지역 B", "2"), total=3),
                regions_xml(region_row("C", "지역 C", "3"), total=3, page=2),
            )
            result = client.collect_region_codes(ac_year="2026")
            self.assertEqual(result, {"A": "지역 A", "B": "지역 B", "C": "지역 C"})
            self.assertEqual(client.region_code_metadata["pages"], 2)
            self.assertTrue(client.region_code_metadata["complete"])
            self.assertEqual(client.success_counts["region_codes"], 2)
            self.assertEqual([urllib.parse.parse_qs(urllib.parse.urlsplit(
                request.full_url).query)["pageNo"] for request in client._opener.requests], [["1"], ["2"]])

    def test_incomplete_region_page_cannot_publish_partial_mapping(self):
        with patch.object(cleaneye, "REGION_PAGE_SIZE", 2):
            for responses, code in (
                ([regions_xml(region_row("A"), total=3)], "incomplete_region_page"),
                ([regions_xml(region_row("A"), region_row("B"), total=3),
                  regions_xml(region_row("C"), total=4, page=2)], "region_count_changed"),
                ([regions_xml(region_row("A"), region_row("B"), total=3),
                  regions_xml(region_row("B"), total=3, page=2)], "duplicate_region_code_across_pages"),
            ):
                with self.subTest(code=code):
                    client = self.client(*responses)
                    self.assert_code(code, lambda: client.collect_region_codes(ac_year=2026))
                    self.assertEqual(client.region_code_mapping, {})
                    self.assertFalse(client.region_code_metadata["complete"])

    def test_region_empty_duplicate_invalid_page_and_limit_fail_closed(self):
        for payload, code in (
            (regions_xml(), "empty_region_codes"),
            (regions_xml(region_row("A"), region_row("A")), "duplicate_region_code"),
            (regions_xml(region_row("A"), page=2), "invalid_region_pagination"),
            (regions_xml(region_row("A"), page_size=0), "invalid_region_pagination"),
            (regions_xml(total=cleaneye.MAX_REGIONS + 1), "region_limit_exceeded"),
            (regions_xml(region_row("A\nB")), "invalid_region"),
            (regions_xml(region_row("A" * 129)), "invalid_region"),
        ):
            with self.subTest(code=code):
                client = self.client(payload)
                self.assert_code(code, lambda: client.collect_region_codes(ac_year=2026))
                self.assertEqual(client.region_code_mapping, {})
                self.assertFalse(client.region_code_metadata["complete"])

    def test_region_request_budget_is_bounded(self):
        with patch.object(cleaneye, "REGION_PAGE_SIZE", 1), patch.object(cleaneye, "MAX_REGION_PAGES", 2):
            client = self.client(regions_xml(region_row("A"), total=3),
                                 regions_xml(region_row("B"), total=3, page=2))
            self.assert_code("region_page_limit_exceeded", lambda: client.collect_region_codes(ac_year=2026))
            self.assertEqual(client.request_counts["region_codes"], 2)
            self.assertFalse(client.region_code_metadata["complete"])

    def test_unapproved_code_service_returns_30_and_never_calls_employment(self):
        payload = b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
        error = urllib.error.HTTPError("https://apis.data.go.kr/?serviceKey=" + KEY,
                                       403, KEY, {}, io.BytesIO(payload))
        client = self.client(error)
        self.assert_code("gateway_30", lambda: client.collect_region_codes(ac_year=2026))
        self.assertEqual(client.request_counts, {"list": 0, "region_codes": 1})
        self.assertEqual(client.success_counts, {"list": 0, "region_codes": 0})
        self.assertEqual(client.region_code_mapping, {})
        self.assertEqual(client.region_code_metadata["pages"], 0)
        self.assertFalse(client.region_code_metadata["complete"])
        self.assertNotIn(KEY, json.dumps(client.region_code_metadata))

    def test_region_mapping_failure_clears_previous_completed_mapping(self):
        client = self.client(regions_xml(region_row("A")))
        client.collect_region_codes(ac_year=2026)
        client._opener = Opener([regions_xml()])
        self.assert_code("empty_region_codes", lambda: client.collect_region_codes(ac_year=2027))
        self.assertEqual(client.region_code_mapping, {})
        self.assertEqual(client.region_code_metadata["reference_year"], 2027)
        self.assertFalse(client.region_code_metadata["complete"])

    def test_invalid_reference_year_starts_no_request(self):
        for year in (None, True, 26, "2026&serviceKey=untrusted", " 2026 ", 10000):
            with self.subTest(year_type=type(year).__name__):
                client = self.client()
                self.assert_code("invalid_reference_year", lambda: client.collect_region_codes(ac_year=year))
                self.assertEqual(client.request_counts, {"list": 0, "region_codes": 0})
                self.assertIsNone(client.region_code_metadata)

    def test_region_credential_echo_and_duplicate_fields_are_rejected(self):
        for payload, code in (
            (regions_xml(region_row(KEY)), "credential_echo_rejected"),
            (regions_xml(region_row("A", urllib.parse.quote(KEY, safe=""))), "credential_echo_rejected"),
            (regions_xml(region_row("A")).replace(b"</item>", b"<SIDO_CD>B</SIDO_CD></item>"), "duplicate_xml_field"),
            (regions_xml(region_row("A")).replace(b"</item>", b"<UNDECLARED>x</UNDECLARED></item>"), "invalid_region_record"),
        ):
            with self.subTest(code=code):
                client = self.client(payload)
                self.assert_code(code, lambda: client.collect_region_codes(ac_year=2026))
                self.assertEqual(client.region_code_mapping, {})
                self.assertFalse(client.region_code_metadata["complete"])


if __name__ == "__main__":
    unittest.main()
