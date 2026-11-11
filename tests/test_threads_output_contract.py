"""Actual post verification must remain read-only and distinguish zero from unknown."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
import urllib.error

from scripts import threads_auto as publisher


class ActualOutputContractTests(unittest.TestCase):
    def setUp(self):
        self.record = {"threads_post_id": "123", "text": "검증된 공고 본문\n\n자세한 사항은 프로필링크 확인",
            "content_type": "master_job", "publication_style": "single_main_v5", "image_url": "",
            "writer_review": {"v5": {"contract_version": 2}}, "reply_text": "", "engagement_text": "",
            "code_commit": "a" * 40}
        self.actual = {"id": "123", "text": self.record["text"], "is_reply": False,
            "username": "hid_119", "media_type": "TEXT_POST", "permalink": "https://www.threads.net/@hid_119/post/example"}
        self.now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)

    def evidence(self, payloads):
        with patch.object(publisher, "api", side_effect=payloads) as api:
            result = publisher.single_post_output_evidence(self.record, [self.actual], "not-a-real-token", now=self.now)
        self.assertTrue(all(call.args[0] == "GET" for call in api.call_args_list))
        return result, api

    def test_verified_text_main_exactly_matches_id_account_body_and_media(self):
        before = deepcopy(self.record)
        with patch.object(publisher, "api", return_value=self.actual) as api:
            objects = publisher.verify_published_record(self.record, "not-a-real-token")
        self.assertEqual(objects, [self.actual])
        api.assert_called_once()
        self.assertEqual(api.call_args.args[:2], ("GET", "/123"))
        self.assertIn("username", api.call_args.args[3]["fields"])
        self.assertEqual(self.record, before)

    def test_wrong_text_id_account_main_type_or_media_never_verifies(self):
        for field, value in (("text", "다른 본문"), ("id", "999"), ("username", "hid_1004"),
                             ("is_reply", True), ("is_reply", None), ("media_type", "IMAGE")):
            with self.subTest(field=field, value=value):
                bad = dict(self.actual, **{field: value})
                with patch.object(publisher, "api", return_value=bad) as api:
                    with self.assertRaises(RuntimeError):
                        publisher.verify_published_record(self.record, "not-a-real-token")
                self.assertEqual(api.call_count, 1)
                self.assertEqual(api.call_args.args[0], "GET")

    def test_image_main_requires_actual_image_url_and_does_not_claim_matching_bytes(self):
        self.record.update(image_url="https://example.invalid/intended.jpg", image_sha256="b" * 64)
        self.actual.update(media_type="IMAGE", media_url="https://example.invalid/actual.jpg")
        with patch.object(publisher, "api", return_value=self.actual):
            objects = publisher.verify_published_record(self.record, "not-a-real-token")
        self.assertEqual(objects[0]["media_url"], self.actual["media_url"])
        self.actual.pop("media_url")
        with patch.object(publisher, "api", return_value=self.actual):
            with self.assertRaisesRegex(RuntimeError, "media mismatch"):
                publisher.verify_published_record(self.record, "not-a-real-token")

    def test_zero_own_replies_requires_complete_successful_scan(self):
        before = deepcopy(self.record)
        proof, api = self.evidence([{"data": [{"id": "456", "username": "reader", "is_reply": True}]}])
        self.assertEqual(proof["status"], "verified")
        self.assertEqual(proof["automatic_reply_count"], 0)
        self.assertEqual(proof["own_replies"], 0)
        self.assertEqual(proof["own_replies_status"], "verified")
        self.assertEqual(proof["reply_scan_scope"], "top_level_all_pages")
        self.assertEqual(proof["body_chars"], len(self.record["text"]))
        self.assertEqual(api.call_args.args[1], "/123/replies")
        self.assertEqual(self.record, before)

    def test_own_replies_separate_from_reader_replies_and_paginate_using_cursors_only(self):
        first = {"data": [{"id": "456", "username": "reader", "is_reply": True}],
                 "paging": {"next": "https://irrelevant.invalid/not-followed", "cursors": {"after": "cursor-a"}}}
        second = {"data": [{"id": "457", "username": "HID_119", "is_reply": True}]}
        proof, api = self.evidence([first, second])
        self.assertEqual(proof["own_replies"], 1)
        self.assertEqual(proof["own_reply_ids"], ["457"])
        self.assertEqual(proof["status"], "unexpected_own_reply_requires_review")
        self.assertEqual(api.call_args_list[1].args[1], "/123/replies")
        self.assertEqual(api.call_args_list[1].args[3]["after"], "cursor-a")

    def test_permission_error_keeps_main_verified_and_own_replies_unknown(self):
        error = urllib.error.HTTPError("redacted", 403, "no permission", {}, None)
        proof, api = self.evidence([error])
        self.assertEqual(proof["status"], "main_verified")
        self.assertIsNone(proof["own_replies"])
        self.assertEqual(proof["own_replies_status"], "access_or_response_unavailable")
        self.assertEqual(proof["automatic_reply_count"], 0)
        self.assertEqual(api.call_count, 1)

    def test_incomplete_paging_cannot_be_zero(self):
        bad_pages = [{"data": [], "paging": {"next": "next"}},
                     {"data": [], "paging": {"next": "next", "cursors": {"after": ""}}}]
        for page in bad_pages:
            with self.subTest(page=page):
                proof, _ = self.evidence([page])
                self.assertIsNone(proof["own_replies"])
                self.assertEqual(proof["own_replies_status"], "access_or_response_unavailable")

    def test_repeated_cursor_and_duplicate_id_never_complete_scan(self):
        first = {"data": [{"id": "456", "username": "reader", "is_reply": True}],
                 "paging": {"next": "next", "cursors": {"after": "cursor-a"}}}
        for second in ({"data": [], "paging": {"next": "next", "cursors": {"after": "cursor-a"}}},
                       {"data": [{"id": "456", "username": "reader", "is_reply": True}]},
                       {"data": [{"id": 456, "username": "reader", "is_reply": True}]}):
            with self.subTest(second=second):
                proof, _ = self.evidence([first, second])
                self.assertIsNone(proof["own_replies"])
                self.assertEqual(proof["own_replies_status"], "access_or_response_unavailable")

    def test_scan_limit_marks_incomplete_instead_of_zero(self):
        pages = [{"data": [], "paging": {"next": "next", "cursors": {"after": "cursor-" + str(i)}}}
                 for i in range(10)]
        proof, api = self.evidence(pages)
        self.assertEqual(api.call_count, 10)
        self.assertEqual(proof["own_replies_status"], "pagination_incomplete")
        self.assertIsNone(proof["own_replies"])

    def test_malformed_reply_objects_do_not_prove_zero(self):
        for row in ({"id": "456", "username": "reader"},
                    {"id": "456", "username": "reader", "is_reply": False},
                    {"id": "not-an-id", "username": "reader", "is_reply": True},
                    {"id": "456", "is_reply": True}):
            with self.subTest(row=row):
                proof, _ = self.evidence([{"data": [row]}])
                self.assertIsNone(proof["own_replies"])
                self.assertEqual(proof["own_replies_status"], "access_or_response_unavailable")

    def test_existing_auto_reply_receipt_cannot_report_contract_success(self):
        self.record["reply_post_id"] = "999"
        proof, _ = self.evidence([{"data": []}])
        self.assertIsNone(proof["automatic_reply_count"])
        self.assertEqual(proof["status"], "unexpected_own_reply_requires_review")


if __name__ == "__main__":
    unittest.main()
