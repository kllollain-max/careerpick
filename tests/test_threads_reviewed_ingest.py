"""Reviewed staging intake: real official byte identity + publisher gate, no POST."""
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts.threads_reviewed_ingest import (
    official_url_allowed, verify_official_receipt, plan,
)


class ReviewedIngestTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, 11, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        self.slot = "2026-11-16T12:00:00+09:00"
        self.entry = {
            "notice_id": "a123", "scheduled_at": self.slot,
            "writer": {"status": "ready", "review": {"source_refs": [
                {"url": "https://www.alio.go.kr/download/example.hwp", "sha256": "a" * 64}
            ]}},
        }
        self.queue = {"schema_version": 1, "entries": []}
        self.staged = {"schema_version": 1, "entries": []}
        self.bundle = {"schema_version": 1, "entries": [self.entry]}
        self.history = {"records": [], "posted_ids": []}
        self.verify = patch("scripts.threads_reviewed_ingest.verify_entry").start()
        self.addCleanup(patch.stopall)

    def call(self, bundle=None, fetch_digest=None, claimed_slots=()):
        return plan(self.queue, self.staged, bundle or self.bundle, self.history,
                    {}, {}, {}, self.now, fetch_digest=fetch_digest or (lambda url: "a" * 64),
                    claimed_slots=claimed_slots)

    def test_real_digest_and_existing_validator_are_both_required(self):
        staged, accepted, refused = self.call()
        self.assertEqual(len(accepted), 1)
        self.assertFalse(refused)
        self.assertEqual(len(staged["entries"]), 1)
        self.assertEqual(len(self.staged["entries"]), 0)
        self.assertEqual(accepted[0]["official_receipt"]["sha256"], "a" * 64)
        self.verify.assert_called_once()

    def test_changed_official_document_never_reaches_validator(self):
        staged, accepted, refused = self.call(fetch_digest=lambda url: "b" * 64)
        self.assertEqual(len(staged["entries"]), 0)
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "OFFICIAL_SOURCE_BYTES_CHANGED")
        self.verify.assert_not_called()

    def test_reviewed_validator_failure_blocks_staging(self):
        self.verify.side_effect = ValueError("V5_REVIEW_REQUIRED")
        staged, accepted, refused = self.call()
        self.assertEqual(len(staged["entries"]), 0)
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "V5_REVIEW_REQUIRED")

    def test_unreviewed_flag_is_never_inferred_from_prose(self):
        entry = {**self.entry, "writer": {**self.entry["writer"], "status": "unreviewed"}}
        _, accepted, refused = self.call(bundle={"schema_version": 1, "entries": [entry]})
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "NOT_A_REVIEWED_ENTRY")
        self.verify.assert_not_called()

    def test_duplicate_notice_and_claimed_slot_blocked(self):
        self.queue["entries"].append({**self.entry, "scheduled_at": "2026-11-16T16:00:00+09:00"})
        _, accepted, refused = self.call()
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "NOTICE_ALREADY_USED_OR_INVALID")
        self.queue["entries"].clear()
        _, accepted, refused = self.call(claimed_slots={self.slot})
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "SLOT_ALREADY_OCCUPIED_OR_CLAIMED")

    def test_submission_can_never_reuse_same_slot(self):
        other = {**self.entry, "notice_id": "a456"}
        staged, accepted, refused = self.call(
            bundle={"schema_version": 1, "entries": [self.entry, other]})
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(staged["entries"]), 1)
        self.assertEqual(refused[0]["reason"], "SLOT_ALREADY_OCCUPIED_OR_CLAIMED")

    def test_no_untrusted_or_localhost_official_urls(self):
        for url in ("http://www.alio.go.kr/test", "https://localhost/x",
                    "https://127.0.0.1/x", "https://alio.go.kr.evil.com/x",
                    "https://user@www.alio.go.kr/a", "https://evil.com/a"):
            with self.subTest(url=url):
                self.assertFalse(official_url_allowed(url))
        self.assertTrue(official_url_allowed("https://www.alio.go.kr/download/a.hwp"))
        self.assertTrue(official_url_allowed("https://yscwf.or.kr/bbs/file.hwp"))

    def test_missing_official_digest_is_hard_block(self):
        entry = {**self.entry, "writer": {"status": "ready", "review": {
            "source_refs": [{"url": "https://yscwf.or.kr/doc.pdf", "excerpt": "claim"}]}}}
        with self.assertRaisesRegex(ValueError, "OFFICIAL_SOURCE_RECEIPT_REQUIRED"):
            verify_official_receipt(entry, fetch_digest=lambda _: "a" * 64)

    def test_future_slot_and_posted_history_are_hard_blocks(self):
        entry = {**self.entry, "scheduled_at": "2026-11-15T12:00:00+09:00"}
        _, accepted, refused = self.call(
            bundle={"schema_version": 1, "entries": [entry]})
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "SLOT_NOT_FUTURE")
        self.history["records"].append({"job_id": "a123", "status": "published"})
        _, accepted, refused = self.call()
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "NOTICE_ALREADY_USED_OR_INVALID")


if __name__ == "__main__":
    unittest.main()
