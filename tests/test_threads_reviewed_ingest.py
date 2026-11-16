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
            ], "fact_evidence": [
                {"field": field, "source_ref": "https://www.alio.go.kr/download/example.hwp"}
                for field in ("title", "count", "employment")
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

    def test_official_receipt_fetch_retries_only_transient_reads(self):
        import hashlib
        import urllib.error
        from unittest.mock import Mock
        from scripts.threads_reviewed_ingest import fetch_official_digest
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'official attachment'
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError('https://www.alio.go.kr/a', 503, '', {}, None), response]
        with patch('scripts.threads_reviewed_ingest.urllib.request.build_opener', return_value=opener), patch('scripts.threads_http.time.sleep') as sleeper:
            digest = fetch_official_digest('https://www.alio.go.kr/a')
        self.assertEqual(digest, hashlib.sha256(b'official attachment').hexdigest())
        self.assertEqual(opener.open.call_count, 2)
        sleeper.assert_called_once_with(2)

    def test_real_digest_and_existing_validator_are_both_required(self):
        staged, accepted, refused = self.call()
        self.assertEqual(len(accepted), 1)
        self.assertFalse(refused)
        self.assertEqual(len(staged["entries"]), 1)
        self.assertEqual(len(self.staged["entries"]), 0)
        self.assertEqual(accepted[0]["official_receipt"]["sha256"], "a" * 64)
        self.verify.assert_called_once()

    def test_live_v5_reviewed_document_digest_is_accepted(self):
        # Production reviewed entries use document_sha256, not sha256.
        self.entry["writer"]["review"]["source_refs"] = [{
            "url": "https://yscwf.or.kr/nc_client/file/download.jsp?_file_l=notice.hwp",
            "document_sha256": "a" * 64,
            "excerpt": "official notice",
        }]
        for fact in self.entry["writer"]["review"]["fact_evidence"]:
            fact["source_ref"] = "https://yscwf.or.kr/nc_client/file/download.jsp?_file_l=notice.hwp"
        staged, accepted, refused = self.call()
        self.assertFalse(refused)
        self.assertEqual(len(staged["entries"]), 1)
        self.assertEqual(accepted[0]["official_receipt"]["sha256"], "a" * 64)
        self.verify.assert_called_once()

    def test_every_cited_fact_document_must_match_current_bytes(self):
        second = "https://www.alio.go.kr/download/attachment2.hwp"
        review = self.entry["writer"]["review"]
        review["source_refs"].append({"url": second, "sha256": "b" * 64})
        review["fact_evidence"][1]["source_ref"] = second
        seen = []
        def fetch(url):
            seen.append(url)
            return "b" * 64 if url == second else "a" * 64
        _, accepted, refused = self.call(fetch_digest=fetch)
        self.assertEqual(len(accepted), 1)
        self.assertFalse(refused)
        self.assertEqual(len(seen), 2)

        # A changed headcount attachment cannot be masked by an unchanged
        # official homepage or another still-valid recruiting document.
        self.verify.reset_mock()
        _, accepted, refused = self.call(fetch_digest=lambda _: "a" * 64)
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "OFFICIAL_SOURCE_BYTES_CHANGED")
        self.verify.assert_not_called()

    def test_uncited_landing_page_cannot_replace_fact_document(self):
        review = self.entry["writer"]["review"]
        review["source_refs"].append({"url": "https://www.alio.go.kr/", "sha256": "a" * 64})
        review["fact_evidence"][0]["source_ref"] = "https://www.alio.go.kr/unlisted.pdf"
        _, accepted, refused = self.call()
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "OFFICIAL_FACT_SOURCE_REQUIRED")
        self.verify.assert_not_called()

    def test_missing_fact_citations_are_not_official_review(self):
        self.entry["writer"]["review"].pop("fact_evidence")
        _, accepted, refused = self.call()
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "OFFICIAL_FACT_SOURCE_REQUIRED")
        self.verify.assert_not_called()

    def test_conflicting_review_digests_fail_closed(self):
        self.entry["writer"]["review"]["source_refs"][0]["document_sha256"] = "b" * 64
        staged, accepted, refused = self.call()
        self.assertFalse(staged["entries"])
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "OFFICIAL_SOURCE_DIGEST_CONFLICT")
        self.verify.assert_not_called()

    def test_malformed_review_digest_fails_closed(self):
        self.entry["writer"]["review"]["source_refs"] = [{
            "url": "https://yscwf.or.kr/doc.hwp", "document_sha256": "not-a-sha"
        }]
        staged, accepted, refused = self.call()
        self.assertFalse(accepted)
        self.assertEqual(refused[0]["reason"], "OFFICIAL_SOURCE_RECEIPT_REQUIRED")
        self.verify.assert_not_called()

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


    def test_only_exact_checked_smrtg_notice_is_allowed(self):
        canonical = "https://www.smrtg.co.kr/employment/stffPbanInfo.do?stffPbanNo=2026-0155"
        self.assertTrue(official_url_allowed(canonical))
        self.assertTrue(official_url_allowed(canonical.replace("www.", "")))
        for url in [
            "https://www.smrtg.co.kr/",
            "https://www.smrtg.co.kr/employment/stffPbanInfo.do?stffPbanNo=2026-0156",
            "https://www.smrtg.co.kr/employment/stffPbanList.do",
            "https://other.smrtg.co.kr/employment/stffPbanInfo.do?stffPbanNo=2026-0155",
            "http://www.smrtg.co.kr/employment/stffPbanInfo.do?stffPbanNo=2026-0155",
        ]:
            with self.subTest(url=url):
                self.assertFalse(official_url_allowed(url))



if __name__ == "__main__":
    unittest.main()
