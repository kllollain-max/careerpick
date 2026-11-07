"""Synthetic source records verify staging safety; these are not live API data."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta
from urllib.parse import quote

import cleaneye
from scripts.collect_cleaneye import CollectionError, merge, normalize, run

NOW = datetime.fromisoformat("2026-11-07T14:00:00+09:00")
KEY = "collector-fixture-credential+/=="
CODES = ("001", "002")  # Deliberately synthetic, not a production region list.


def row(identity="00017", **changes):
    return {
        "NO": identity, "ENT_NAME": "테스트 지방공공기관", "ENT_TITLE": "신입 직원 채용",
        "STATUS": "접수중", "JOB_TYPE": "비정규직", "EMPLOY_NUM": "2",
        "PUB_DATE": "2026-11-01", "PUB_END_DATE": "2026-11-20",
        "UPD_DATE": "2026-11-07", "WORK_PLACE": "부산광역시", "SIDO_CD": "서울특별시",
        "URL": "https://job.cleaneye.go.kr/synthetic-fixture?NO=" + identity,
        "FILE_NAME1": "채용공고.hwp", "DUTY_DETAIL": "안내 및 시설 운영", **changes,
    }


def staged(previous=None, records=None, now=NOW, **changes):
    records = [row()] if records is None else records
    options = {"sido_codes": CODES, "region_counts": {CODES[0]: len(records), CODES[1]: 0},
               "complete_collection": True, **changes}
    return merge({"posts": []} if previous is None else previous, records, now, **options)


class FakeClient:
    def __init__(self, records, *, complete=True, counts=None, error=None, mutate=None,
                 region_codes=None, region_error=None, region_metadata=None):
        self.records = records
        self.complete = complete
        self.counts = counts
        self.error = error
        self.mutate = mutate
        self.region_codes = {code: "테스트 지역 " + str(i) for i, code in enumerate(CODES)} if region_codes is None else region_codes
        self.region_error = region_error
        self.metadata = region_metadata
        self.region_code_metadata = {"complete": False}
        self.collection_complete = False
        self.region_counts = {}
        self.request_counts = {"region_codes": 0, "list": 0}
        self.success_counts = {"region_codes": 0, "list": 0}
        self.called_codes = None
        self.code_lookup_year = None

    def collect_region_codes(self, *, ac_year):
        self.request_counts["region_codes"] += 1
        self.code_lookup_year = ac_year
        if self.region_error:
            raise self.region_error
        self.region_code_metadata = self.metadata if self.metadata is not None else {
            "reference_year": ac_year, "total_count": len(self.region_codes), "pages": 1, "complete": True}
        self.success_counts["region_codes"] += 1
        return self.region_codes

    def collect_list(self, *, sido_codes):
        self.called_codes = sido_codes
        self.request_counts["list"] = len(sido_codes)
        if self.mutate:
            self.mutate()
        if self.error:
            raise self.error
        self.success_counts["list"] = len(sido_codes)
        self.collection_complete = self.complete
        self.region_counts = self.counts if self.counts is not None else {
            code: len(self.records) if i == 0 else 0 for i, code in enumerate(sido_codes)}
        return copy.deepcopy(self.records)


class CleaneyeNormalizationTests(unittest.TestCase):
    def test_source_identity_and_dates_have_their_actual_meanings(self):
        post = normalize(row(), NOW)
        self.assertEqual(post["id"], "cleaneye-00017")
        self.assertEqual(post["source"], "클린아이 잡플러스")
        self.assertTrue(post["cleaneye"])
        self.assertEqual(post["type"], "j")
        self.assertEqual(post["cat"], "지방공공기관 채용")
        self.assertIsNone(post["pub"])
        self.assertEqual(post["start"], "2026-11-01")
        self.assertEqual(post["due"], "2026-11-20T23:59:59+09:00")
        self.assertFalse(post["dueHasTime"])
        self.assertEqual(post["region"], "부산광역시")
        self.assertEqual(post["sourceRegion"], "서울특별시")
        self.assertEqual(post["n"], 2)
        self.assertEqual(post["receptionState"], "verified_open")
        self.assertEqual(post["cleaneyeDetail"]["수정날짜 원문"], "2026-11-07")
        self.assertNotIn("alio", post)
        self.assertNotIn("gojobs", post)

    def test_employment_is_exact_source_text_not_a_substring_or_title_guess(self):
        self.assertEqual(normalize(row(JOB_TYPE="비정규직"), NOW)["emp"], ["비정규직"])
        self.assertEqual(normalize(row(JOB_TYPE="정규직 / 무기계약직"), NOW)["emp"], ["정규직", "무기계약직"])
        for source in ("1", "", "비정규직 전환 검토", "미정"):
            with self.subTest(source=source):
                post = normalize(row(JOB_TYPE=source, ENT_TITLE="정규직 직원 채용"), NOW)
                self.assertEqual(post["emp"], [])
                self.assertEqual(post["edu"], [])
        post = normalize(row(EMPLOY_NUM="2명(예비 3명)"), NOW)
        self.assertEqual(post["n"], "2명(예비 3명)")
        self.assertEqual(post["cleaneyeDetail"]["채용인원"], "2명(예비 3명)")

    def test_observed_employment_labels_are_preserved_without_contract_inference(self):
        for label in ("기간제", "무기계약직", "비상임", "인턴", "일반계약직", "일반정규직", "전문계약직"):
            with self.subTest(label=label):
                source = row(JOB_TYPE=label)
                before = copy.deepcopy(source)
                post = normalize(source, NOW)
                self.assertEqual(post["emp"], [label])
                self.assertEqual(post["cleaneyeDetail"]["고용형태 원문"], label)
                self.assertEqual(source, before)
        raw = "일반정규직 / 일반계약직 / 전문계약직 / 비상임 / 일반계약직"
        post = normalize(row(JOB_TYPE=raw), NOW)
        self.assertEqual(post["emp"], ["일반정규직", "일반계약직", "전문계약직", "비상임"])
        self.assertEqual(post["cleaneyeDetail"]["고용형태 원문"], raw)

    def test_literal_null_optional_fields_remain_unknown_and_never_fill_workplace_from_institution(self):
        source = row(WORK_PLACE="null", OFFICE_HOURS="null", SPECIAL_ITEM="null",
                     EMPLOY_NUM="null", ADDRESS="null")
        before = copy.deepcopy(source)
        post = normalize(source, NOW)
        self.assertEqual(post["region"], "")
        self.assertEqual(post["sourceRegion"], "서울특별시")
        self.assertIsNone(post["n"])
        for label in ("근무지", "근무시간", "우대사항", "채용인원", "기관주소"):
            self.assertNotIn(label, post["cleaneyeDetail"])
        self.assertNotIn("null", post["text"])
        self.assertEqual(post["start"], "2026-11-01")
        self.assertEqual(post["due"], "2026-11-20T23:59:59+09:00")
        self.assertEqual(post["cleaneyeDetail"]["접수개시일 원문"], source["PUB_DATE"])
        self.assertEqual(post["cleaneyeDetail"]["접수마감일 원문"], source["PUB_END_DATE"])
        self.assertEqual(post["cleaneyeDetail"]["수정날짜 원문"], source["UPD_DATE"])
        self.assertEqual(source, before)
        text = "null 값을 점검하는 업무"
        self.assertIn(text, normalize(row(DUTY_DETAIL=text), NOW)["text"])
        self.assertEqual(normalize(row(EMPLOY_NUM="0"), NOW)["n"], 0)

    def test_literal_null_cannot_masquerade_as_a_required_identity_title_or_institution(self):
        for name in ("NO", "ENT_TITLE", "ENT_NAME"):
            with self.subTest(name=name), self.assertRaises(CollectionError):
                normalize(row(**{name: "null"}), NOW)

    def test_far_future_source_dates_remain_unchanged_but_need_review(self):
        for due in ("2050-09-26", "2054-07-10", "2400-03-19", "2036-01-01"):
            for status, start in (("모집중", "2026-11-01"), ("모집예정", "2026-11-10")):
                with self.subTest(due=due, status=status):
                    post = normalize(row(STATUS=status, PUB_DATE=start, PUB_END_DATE=due), NOW)
                    self.assertEqual(post["receptionState"], "verification_pending")
                    self.assertEqual(post["deadlineReviewReason"], "far_future_source_date")
                    self.assertEqual(post["start"], start)
                    self.assertEqual(post["due"], due + "T23:59:59+09:00")
                    self.assertFalse(post["dueHasTime"])
                    self.assertEqual(post["cleaneyeDetail"]["접수마감일 원문"], due)

    def test_far_future_review_uses_ten_calendar_years_and_keeps_explicit_closed_status(self):
        for due, now in (("2027-11-20", NOW), ("2035-12-31", NOW),
                         ("2036-01-01", NOW.replace(year=2027))):
            with self.subTest(due=due, now=now):
                post = normalize(row(STATUS="모집중", PUB_END_DATE=due), now)
                self.assertEqual(post["receptionState"], "verified_open")
                self.assertNotIn("deadlineReviewReason", post)
        for status, expected in (("채용마감", "expired"), ("채용취소", "cancelled")):
            with self.subTest(status=status):
                post = normalize(row(STATUS=status, PUB_END_DATE="2054-07-10"), NOW)
                self.assertEqual(post["receptionState"], expected)
                self.assertEqual(post["due"], "2054-07-10T23:59:59+09:00")

    def test_optional_fields_stay_unknown_and_filename_does_not_become_a_url(self):
        raw = {key: row()[key] for key in ("NO", "ENT_TITLE", "ENT_NAME", "URL")}
        post = normalize(raw, NOW)
        for key in ("pub", "start", "due", "n"):
            self.assertIsNone(post[key])
        self.assertEqual(post["region"], "")
        self.assertEqual(post["emp"], [])
        self.assertEqual(post["receptionState"], "verification_pending")
        detailed = normalize(row(), NOW)
        self.assertEqual(detailed["cleaneyeDetail"]["첨부파일명1"], "채용공고.hwp")
        self.assertNotIn("files", detailed)
        self.assertNotIn("attachments", detailed)

    def test_date_only_deadline_day_is_uncertain_and_exact_time_is_respected(self):
        pending = normalize(row(PUB_END_DATE="2026.11.07"), NOW)
        self.assertEqual(pending["receptionState"], "verification_pending")
        self.assertFalse(pending["dueHasTime"])
        exact = normalize(row(PUB_END_DATE="2026-11-07 18:00"), NOW)
        self.assertTrue(exact["dueHasTime"])
        self.assertEqual(exact["due"], "2026-11-07T18:00:00+09:00")
        self.assertEqual(exact["receptionState"], "verified_open")
        self.assertEqual(normalize(row(PUB_END_DATE="2026-11-07 13:59:59"), NOW)["receptionState"], "expired")
        self.assertEqual(normalize(row(PUB_END_DATE="2026-11-07T09:00:00Z"), NOW)["due"], exact["due"])

    def test_valid_compact_dates_and_invalid_calendar_dates_do_not_get_guessed(self):
        compact = normalize(row(PUB_DATE="20261101", PUB_END_DATE="20261107180000"), NOW)
        self.assertEqual(compact["start"], "2026-11-01")
        self.assertTrue(compact["dueHasTime"])
        for value in ("2026-02-30", "2026-13-01", "11/20/2026", "채용시까지", "2026-11-20 이후"):
            with self.subTest(value=value):
                post = normalize(row(PUB_END_DATE=value), NOW)
                self.assertIsNone(post["due"])
                self.assertFalse(post["dueHasTime"])
                self.assertEqual(post["receptionState"], "invalid_date")
                self.assertEqual(post["cleaneyeDetail"]["접수마감일 원문"], value)
        self.assertEqual(normalize(row(PUB_DATE="2026-11-25"), NOW)["receptionState"], "invalid_date")

    def test_unknown_status_codes_never_become_open_and_closures_are_explicit(self):
        for value in ("1", "2", "", "결과발표"):
            self.assertEqual(normalize(row(STATUS=value), NOW)["receptionState"], "verification_pending")
        self.assertEqual(normalize(row(STATUS="채용취소"), NOW)["receptionState"], "cancelled")
        self.assertEqual(normalize(row(STATUS="접수마감"), NOW)["receptionState"], "expired")
        self.assertEqual(normalize(row(PUB_DATE="2026-11-10"), NOW)["receptionState"], "upcoming")
        self.assertEqual(normalize(row(PUB_DATE="2026-10-01", PUB_END_DATE="2026-10-31"), NOW)["receptionState"], "expired")

    def test_plain_search_text_is_inert_but_original_details_are_preserved(self):
        raw = "<p>안내 &amp; 운영</p><script>alert('secret')</script><style>body{display:none}</style><p>접수</p>"
        post = normalize(row(DUTY_DETAIL=raw, ENT_TITLE="<b>직원</b> 채용"), NOW)
        self.assertEqual(post["title"], "직원 채용")
        self.assertIn("안내 & 운영", post["text"])
        self.assertNotIn("<p>", post["text"])
        self.assertNotIn("alert", post["text"])
        self.assertNotIn("display:none", post["text"])
        self.assertEqual(post["cleaneyeDetail"]["직무세부내용"], raw)

    def test_invalid_identity_title_org_or_official_link_rejects_the_entire_candidate(self):
        cases = [
            {"NO": "../17"}, {"NO": ""}, {"ENT_TITLE": "<script>hidden</script>"},
            {"ENT_NAME": " "}, {"URL": ""}, {"URL": "http://job.cleaneye.go.kr/notice"},
            {"URL": "https://job.cleaneye.go.kr.evil.example/notice"},
            {"URL": "https://user:pass@job.cleaneye.go.kr/notice"},
            {"URL": "https://job.cleaneye.go.kr:444/notice"},
            {"URL": "https://job.cleaneye.go.kr/"}, {"URL": "javascript:alert(1)"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(CollectionError):
                    staged(records=[row(), row("second", **changes)])
        url = "https://www.job.cleaneye.go.kr/synthetic-fixture?NO=17&amp;part=1"
        self.assertEqual(normalize(row(URL=url), NOW)["url"], url.replace("&amp;", "&"))

    def test_namespaced_id_fits_the_existing_saved_record_contract(self):
        self.assertEqual(len(normalize(row(identity="a" * 119), NOW)["id"]), 128)
        with self.assertRaisesRegex(CollectionError, "invalid_notice_id"):
            normalize(row(identity="a" * 120), NOW)


class CleaneyeMergeTests(unittest.TestCase):
    def test_far_future_source_date_counts_remain_separate_from_active_and_upcoming(self):
        feed, _, counts = staged(records=[
            row("far-open", PUB_END_DATE="2054-07-10"),
            row("far-upcoming", PUB_DATE="2026-11-10", PUB_END_DATE="2400-03-19"),
            row("next-year", PUB_END_DATE="2027-11-20"),
        ])
        self.assertEqual(counts["far_future_source_date"], 2)
        self.assertEqual(counts["active"], 1)
        self.assertEqual(counts["upcoming"], 0)
        self.assertEqual(counts["status_uncertain"], 2)
        self.assertEqual(counts["received"], 3)
        self.assertEqual(len(feed["posts"]), 3)

    def test_repeat_collection_has_no_content_or_timestamp_churn(self):
        feed, changed, counts = staged()
        self.assertTrue(changed)
        self.assertEqual(counts["new"], 1)
        repeated, changed, counts = staged(feed, now=NOW + timedelta(hours=2))
        self.assertIs(repeated, feed)
        self.assertFalse(changed)
        self.assertEqual(counts["changed"], 0)
        self.assertEqual(counts["deleted"], 0)
        self.assertEqual(feed["collectionStatus"], "verified")
        self.assertEqual(feed["regionCodes"], list(CODES))

    def test_missing_source_record_is_retained_and_becomes_uncertain(self):
        feed, _, _ = staged()
        candidate, changed, counts = staged(feed, [row("new")])
        self.assertTrue(changed)
        self.assertEqual({p["id"] for p in candidate["posts"]}, {"cleaneye-00017", "cleaneye-new"})
        retained = next(p for p in candidate["posts"] if p["id"] == "cleaneye-00017")
        self.assertEqual(retained["receptionState"], "verification_pending")
        self.assertTrue(retained["sourceMissing"])
        self.assertEqual(retained["cleaneyeDetail"], feed["posts"][0]["cleaneyeDetail"])
        self.assertEqual(counts["retained"], 1)
        self.assertEqual(counts["deleted"], 0)
        self.assertFalse(staged(candidate, [row("new")])[1])
        returned, _, _ = staged(candidate, [row(), row("new")])
        self.assertFalse(returned["posts"][0]["sourceMissing"])

    def test_partial_duplicate_empty_and_abrupt_count_decrease_preserve_baseline(self):
        feed, _, _ = staged()
        before = copy.deepcopy(feed)
        for options in (
            {"complete_collection": False}, {"region_counts": {"001": 1}},
            {"region_counts": {"001": 2, "002": 0}}, {"region_counts": {"001": True, "002": 0}},
        ):
            with self.subTest(options=options), self.assertRaises(CollectionError):
                staged(feed, **options)
        for records in ([], [row(), row()]):
            with self.assertRaises(CollectionError):
                staged(feed, records)
        with self.assertRaisesRegex(CollectionError, "unexpected_collection_decrease"):
            staged({**feed, "last_received": 10}, [row(str(i)) for i in range(6)])
        self.assertEqual(feed, before)

    def test_source_scope_cannot_shrink_without_review(self):
        feed, _, _ = staged()
        with self.assertRaisesRegex(CollectionError, "collection_scope_narrowed"):
            staged(feed, sido_codes=["001"], region_counts={"001": 1})
        with self.assertRaises(CollectionError):
            staged({"posts": [{"id": "a17"}]})
        with self.assertRaises(CollectionError):
            staged({"posts": [feed["posts"][0], feed["posts"][0]]})

    def test_no_current_initial_candidate_blocks_but_confirmed_later_closure_is_saved(self):
        for changes in ({"STATUS": "접수마감"}, {"STATUS": "취소"}, {"PUB_END_DATE": ""},
                        {"PUB_DATE": "2026-10-01", "PUB_END_DATE": "2026-10-31"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(CollectionError, "no_current_initial_candidate"):
                staged(records=[row(**changes)])
        feed, _, _ = staged()
        closed, changed, counts = staged(feed, [row(STATUS="접수마감")])
        self.assertTrue(changed)
        self.assertEqual(closed["posts"][0]["receptionState"], "expired")
        self.assertEqual(counts["expired"], 1)
        self.assertEqual(counts["deleted"], 0)
        pending, _, counts = staged(records=[row(STATUS="unconfirmed")])
        self.assertEqual(counts["active"], 0)
        self.assertEqual(pending["posts"][0]["receptionState"], "verification_pending")


class CleaneyeStagingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.originals = {
            "cleaneye.json": b'{"source":"cleaneye", "updated":null,"collectionStatus":"not_collected","posts":[]}\n',
            "alio.json": b'{ "posts": [{"id":"a17"}] }\n',
            "alio-detail.json": b'{ "a17": {"title":"unchanged"} }\n',
            "gojobs.json": b'{"posts":[{"id":"gojobs-17"}]}\n',
            "data/civil-service/2026.json": b'{"records": []}\n',
        }
        for name, content in self.originals.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def collect(self, fake=None, **options):
        fake = fake or FakeClient([row()])
        return run(root=self.root, key=KEY, client_factory=lambda key: fake, now=NOW,
                   **{"sido_codes": CODES, **options})

    def assert_preserved(self):
        for name, content in self.originals.items():
            self.assertEqual((self.root / name).read_bytes(), content)

    def test_success_writes_only_isolated_candidate_and_namespaced_counts(self):
        fake = FakeClient([row()])
        report = self.collect(fake)
        self.assertEqual(report["status"], "changed")
        self.assertTrue(report["originals_preserved"])
        self.assertTrue(report["authentication_verified"])
        self.assertTrue(report["complete_collection"])
        self.assertEqual(fake.called_codes, CODES)
        self.assertEqual(report["counts"]["cleaneye"]["new"], 1)
        self.assertEqual(report["counts"]["cleaneye"]["deleted"], 0)
        self.assertEqual(report["requests"], {"region_codes": 0, "list": 2})
        self.assertEqual(report["region_code_source"], "explicit")
        self.assert_preserved()
        output = self.root / "cleaneye-operation-output"
        candidate = json.loads((output / "cleaneye.json").read_bytes())
        self.assertEqual(candidate["posts"][0]["id"], "cleaneye-00017")
        self.assertEqual(json.loads((output / "report.json").read_bytes()), report)

    def test_failure_never_leaves_partial_candidate_or_raw_exception(self):
        failures = [FakeClient([row()], complete=False),
                    FakeClient([row()], counts={"001": 2, "002": 0}),
                    FakeClient([], error=RuntimeError("https://private.example/?serviceKey=" + KEY)),
                    FakeClient([row(), row("bad", URL="https://external.example/apply")])]
        for i, fake in enumerate(failures):
            with self.subTest(i=i):
                output = self.root / f"failure-{i}"
                report = self.collect(fake, output=output)
                self.assertEqual(report["status"], "failed_preserved")
                self.assertTrue(report["originals_preserved"])
                self.assertFalse((output / "cleaneye.json").exists())
                self.assertNotIn(KEY, (output / "report.json").read_text())
                self.assertNotIn("private.example", (output / "report.json").read_text())
        self.assert_preserved()

    def test_missing_key_makes_no_api_call(self):
        factory = unittest.mock.Mock(side_effect=AssertionError("must not initialize client"))
        with patch.dict("os.environ", {"CLEANEYE_SIDO_CODES": ""}):
            report = run(root=self.root, key="", client_factory=factory, now=NOW)
            self.assertEqual(report["status"], "failed_preserved")
            self.assertEqual(report["requests"], {"region_codes": 0, "list": 0})
            self.assertTrue(report["originals_preserved"])
        factory.assert_not_called()
        self.assert_preserved()

    def test_missing_codes_uses_official_resolver_before_the_same_client_collects(self):
        fake = FakeClient([row()])
        with patch.dict("os.environ", {"CLEANEYE_SIDO_CODES": ""}):
            report = self.collect(fake, sido_codes=None)
        self.assertEqual(report["status"], "changed")
        self.assertEqual(fake.code_lookup_year, 2026)
        self.assertEqual(fake.called_codes, CODES)
        self.assertEqual(report["region_code_source"], "official_api")
        self.assertTrue(report["region_code_lookup_verified"])
        self.assertEqual(report["requests"], {"region_codes": 1, "list": 2})
        self.assertEqual(report["successful_responses"], {"region_codes": 1, "list": 2})
        self.assert_preserved()

    def test_report_preserves_retry_attempts_above_the_region_limit(self):
        class RetriedClient(FakeClient):
            def collect_region_codes(self, *, ac_year):
                mapping = super().collect_region_codes(ac_year=ac_year)
                # Synthetic one-region pages, each recovered on its third try.
                self.region_code_metadata["pages"] = len(mapping)
                self.request_counts["region_codes"] = len(mapping) * 3
                self.success_counts["region_codes"] = len(mapping)
                return mapping

            def collect_list(self, *, sido_codes):
                records = super().collect_list(sido_codes=sido_codes)
                self.request_counts["list"] = len(sido_codes) * 3
                return records

        for regions in (17, 32):
            with self.subTest(regions=regions), patch.dict("os.environ", {"CLEANEYE_SIDO_CODES": ""}):
                mapping = {f"R{i}": f"테스트 지역 {i}" for i in range(regions)}
                fake = RetriedClient([row()], region_codes=mapping)
                report = self.collect(fake, sido_codes=None, output=self.root / f"retry-{regions}")
                self.assertEqual(report["status"], "changed")
                self.assertEqual(report["requests"], {"region_codes": regions * 3, "list": regions * 3})
                self.assertEqual(report["successful_responses"], {"region_codes": regions, "list": regions})
                self.assertTrue(report["complete_collection"])
                self.assertTrue(report["originals_preserved"])
        self.assert_preserved()

    def test_retry_report_keeps_request_and_success_limits_distinct(self):
        class ImpossibleCountsClient(FakeClient):
            def collect_list(self, *, sido_codes):
                records = super().collect_list(sido_codes=sido_codes)
                self.request_counts = {"region_codes": 97, "list": 97}
                self.success_counts = {"region_codes": 33, "list": 33}
                return records

        report = self.collect(ImpossibleCountsClient([row()]))
        self.assertEqual(report["status"], "changed")
        self.assertEqual(report["requests"], {"region_codes": 0, "list": 0})
        self.assertEqual(report["successful_responses"], {"region_codes": 0, "list": 0})
        self.assert_preserved()

    def test_region_service_approval_error_is_separate_and_never_uses_guessed_codes(self):
        fake = FakeClient([row()], region_error=cleaneye.APIError("gateway_30"))
        with patch.dict("os.environ", {"CLEANEYE_SIDO_CODES": ""}):
            report = self.collect(fake, sido_codes=None)
        self.assertEqual(report["status"], "failed_preserved")
        self.assertEqual(report["error_source"], "region_codes")
        self.assertEqual(report["error"], "gateway_30")
        self.assertEqual(report["region_code_source_url"], cleaneye.REGION_SOURCE_URL)
        self.assertEqual(report["requests"], {"region_codes": 1, "list": 0})
        self.assertFalse(report["region_code_lookup_verified"])
        self.assertFalse(report["authentication_verified"])
        self.assertFalse(report["complete_collection"])
        self.assertIsNone(fake.called_codes)
        self.assertNotIn("region_codes", report)
        self.assertTrue(report["originals_preserved"])
        self.assertFalse((self.root / "cleaneye-operation-output/cleaneye.json").exists())
        self.assert_preserved()

    def test_empty_or_invalid_official_codes_prevent_employment_requests(self):
        for i, codes in enumerate(({}, [], {"": "빈 코드"}, {"001": ""}, {"001": "지역", 2: "지역"})):
            fake = FakeClient([row()], region_codes=codes)
            with patch.dict("os.environ", {"CLEANEYE_SIDO_CODES": ""}):
                report = self.collect(fake, sido_codes=None, output=self.root / f"invalid-codes-{i}")
            self.assertEqual(report["status"], "failed_preserved")
            self.assertEqual(report["error_source"], "region_codes")
            self.assertEqual(report["requests"]["list"], 0)
            self.assertFalse(report["region_code_lookup_verified"])
            self.assertIsNone(fake.called_codes)
        self.assert_preserved()

    def test_official_code_format_is_not_assumed_to_be_numeric(self):
        fake = FakeClient([row()], region_codes={"source-code-A": "공식 코드의 원문 지역명"})
        with patch.dict("os.environ", {"CLEANEYE_SIDO_CODES": ""}):
            report = self.collect(fake, sido_codes=None)
        self.assertEqual(report["status"], "changed")
        self.assertEqual(fake.called_codes, ("source-code-A",))
        self.assertEqual(report["region_code_metadata"], {
            "reference_year": 2026, "total_count": 1, "pages": 1, "complete": True})
        self.assert_preserved()

    def test_partial_or_mismatched_region_code_metadata_cannot_collect_jobs(self):
        complete = {"reference_year": 2026, "total_count": 2, "pages": 1, "complete": True}
        for i, changes in enumerate(({"complete": False}, {"total_count": 3}, {"reference_year": 2025}, {"pages": 0})):
            fake = FakeClient([row()], region_metadata={**complete, **changes})
            with patch.dict("os.environ", {"CLEANEYE_SIDO_CODES": ""}):
                report = self.collect(fake, sido_codes=None, output=self.root / f"incomplete-codes-{i}")
            self.assertEqual(report["error"], "incomplete_region_code_list")
            self.assertEqual(report["error_source"], "region_codes")
            self.assertEqual(report["requests"]["list"], 0)
            self.assertIsNone(fake.called_codes)
        self.assert_preserved()

    def test_key_echo_in_response_is_never_written_even_after_url_encoding(self):
        variants = [KEY, quote(KEY, safe=""), quote(quote(KEY, safe=""), safe="")]
        for i, variant in enumerate(variants):
            output = self.root / f"echo-{i}"
            report = self.collect(FakeClient([row(REFERENCE="serviceKey=" + variant)]), output=output)
            self.assertEqual(report["status"], "failed_preserved")
            self.assertEqual(report["error"], "credential_echo_rejected")
            self.assertFalse((output / "cleaneye.json").exists())
            text = (output / "report.json").read_text()
            for secret in variants:
                self.assertNotIn(secret, text)
        self.assert_preserved()

    def test_original_changes_during_collection_prevent_candidate_adoption(self):
        fake = FakeClient([row()], mutate=lambda: (self.root / "alio.json").write_text("external change"))
        report = self.collect(fake)
        self.assertEqual(report["status"], "failed_preserved")
        self.assertEqual(report["error"], "source_changed_during_collection")
        self.assertFalse(report["originals_preserved"])
        self.assertFalse((self.root / "cleaneye-operation-output/cleaneye.json").exists())
        self.assertEqual((self.root / "cleaneye.json").read_bytes(), self.originals["cleaneye.json"])

    def test_stale_candidate_and_source_output_paths_are_rejected(self):
        success = self.collect()
        self.assertEqual(success["status"], "changed")
        before = (self.root / "cleaneye-operation-output/cleaneye.json").read_bytes()
        stale = self.collect(FakeClient([row("second")]))
        self.assertEqual(stale["status"], "failed_preserved")
        self.assertEqual(stale["error"], "existing_candidate_output")
        self.assertEqual((self.root / "cleaneye-operation-output/cleaneye.json").read_bytes(), before)
        unsafe = self.collect(output=self.root)
        self.assertEqual(unsafe["error"], "unsafe_output_directory")
        self.assertFalse((self.root / "report.json").exists())
        self.assert_preserved()

    def test_output_symlink_cannot_redirect_a_candidate_into_the_source_directory(self):
        (self.root / "cleaneye-operation-output").symlink_to(self.root, target_is_directory=True)
        report = self.collect()
        self.assertEqual(report["error"], "unsafe_output_directory")
        self.assertFalse((self.root / "report.json").exists())
        self.assert_preserved()


if __name__ == "__main__":
    unittest.main()
